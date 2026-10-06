import argparse
import csv
import hashlib
import json
import random
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    classification_report,
    confusion_matrix,
    roc_auc_score,
)

from app.ml.features import MODEL_FEATURE_NAMES, extract_url_features


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL = PROJECT_ROOT / "ml_model" / "artifacts" / "phishguard_url_model.joblib"
DEFAULT_METRICS = PROJECT_ROOT / "ml_model" / "artifacts" / "raw_training_metrics.json"


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def usable_url(url):
    try:
        extract_url_features(url)
    except ValueError:
        return None
    return url.strip()


def load_phishtank_splits(path, train_end, diagnostic_start):
    splits = {"train": set(), "validation": set(), "diagnostic": set()}
    rejected = 0
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"url", "verified", "verification_time", "online"}
        if not required.issubset(reader.fieldnames or ()):
            raise ValueError("PhishTank CSV does not contain the required columns")
        for row in reader:
            try:
                verified_at = datetime.fromisoformat(row["verification_time"])
            except (TypeError, ValueError):
                rejected += 1
                continue
            url = usable_url(row["url"])
            if (
                url is None
                or row["verified"].lower() != "yes"
                or row["online"].lower() != "yes"
            ):
                rejected += 1
                continue
            if verified_at < train_end:
                splits["train"].add(url)
            elif verified_at < diagnostic_start:
                splits["validation"].add(url)
            else:
                splits["diagnostic"].add(url)
    return {name: sorted(urls) for name, urls in splits.items()}, rejected


def load_legitimate_pool(zip_path, excluded_urls):
    urls = set()
    rejected = 0
    with zipfile.ZipFile(zip_path) as archive:
        csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(csv_names) != 1:
            raise ValueError("Legitimate archive must contain exactly one CSV")
        with archive.open(csv_names[0]) as raw_handle:
            decoded = (line.decode("utf-8-sig", errors="replace") for line in raw_handle)
            reader = csv.DictReader(decoded)
            if not {"url", "status"}.issubset(reader.fieldnames or ()):
                raise ValueError("Legitimate CSV must contain url and status columns")
            for row in reader:
                if row["status"].strip() != "1":
                    continue
                url = row["url"].strip()
                if url in excluded_urls:
                    continue
                url = usable_url(url)
                if url is None:
                    rejected += 1
                else:
                    urls.add(url)
    return sorted(urls), rejected


def load_tranco_pool(zip_path, excluded_urls):
    urls = []
    seen = set()
    with zipfile.ZipFile(zip_path) as archive:
        csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(csv_names) != 1:
            raise ValueError("Tranco archive must contain exactly one CSV")
        with archive.open(csv_names[0]) as raw_handle:
            decoded = (line.decode("utf-8-sig", errors="replace") for line in raw_handle)
            for index, row in enumerate(csv.reader(decoded)):
                if len(row) < 2:
                    continue
                domain = row[1].strip()
                hostname = domain if index % 2 == 0 else f"www.{domain}"
                url = usable_url(f"https://{hostname}/")
                if url and url not in excluded_urls and url not in seen:
                    seen.add(url)
                    urls.append(url)
    return urls


def feature_matrix(urls):
    rows = []
    for url in urls:
        features = extract_url_features(url)
        rows.append([features[name] for name in MODEL_FEATURE_NAMES])
    return np.asarray(rows, dtype=float)


def score(model, legitimate_urls, phishing_urls, threshold=0.5):
    urls = legitimate_urls + phishing_urls
    labels = np.asarray([0] * len(legitimate_urls) + [1] * len(phishing_urls))
    probabilities = model.predict_proba(feature_matrix(urls))[:, 1]
    predictions = (probabilities >= threshold).astype(int)
    return {
        "rows": int(len(labels)),
        "legitimate_rows": len(legitimate_urls),
        "phishing_rows": len(phishing_urls),
        "accuracy": round(float(accuracy_score(labels, predictions)), 6),
        "roc_auc": round(float(roc_auc_score(labels, probabilities)), 6),
        "pr_auc": round(float(average_precision_score(labels, probabilities)), 6),
        "confusion_matrix": confusion_matrix(labels, predictions).tolist(),
        "classification_report": classification_report(
            labels, predictions, output_dict=True, zero_division=0
        ),
    }


def retrain(
    phishing_path,
    legitimate_zip,
    tranco_zip,
    model_path,
    metrics_path,
    train_end,
    diagnostic_start,
    seed=42,
):
    phishing, phishing_rejected = load_phishtank_splits(
        phishing_path, train_end, diagnostic_start
    )
    excluded = set().union(*map(set, phishing.values()))
    legitimate_pool, legitimate_rejected = load_legitimate_pool(legitimate_zip, excluded)
    tranco_pool = load_tranco_pool(tranco_zip, excluded)
    required_by_split = {name: len(urls) for name, urls in phishing.items()}
    legacy_needed = {name: count // 2 for name, count in required_by_split.items()}
    tranco_needed = {
        name: required_by_split[name] - legacy_needed[name]
        for name in required_by_split
    }
    if len(legitimate_pool) < sum(legacy_needed.values()) or len(tranco_pool) < sum(
        tranco_needed.values()
    ):
        raise ValueError("Not enough legitimate URLs to balance every data split")

    rng = random.Random(seed)
    selected_legacy = rng.sample(legitimate_pool, sum(legacy_needed.values()))
    legitimate = {}
    legacy_offset = 0
    tranco_offset = 0
    for name in ("train", "validation", "diagnostic"):
        legacy_end = legacy_offset + legacy_needed[name]
        tranco_end = tranco_offset + tranco_needed[name]
        legitimate[name] = (
            selected_legacy[legacy_offset:legacy_end]
            + tranco_pool[tranco_offset:tranco_end]
        )
        legacy_offset = legacy_end
        tranco_offset = tranco_end

    train_urls = legitimate["train"] + phishing["train"]
    train_labels = np.asarray(
        [0] * len(legitimate["train"]) + [1] * len(phishing["train"])
    )
    model = RandomForestClassifier(
        n_estimators=400,
        max_depth=18,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=seed,
        n_jobs=-1,
    )
    model.fit(feature_matrix(train_urls), train_labels)

    threshold = 0.5
    generated_at = datetime.now(timezone.utc).isoformat()
    metrics = {
        "training_type": "date-separated balanced raw URLs",
        "training_rows": len(train_urls),
        "training_legitimate_rows": len(legitimate["train"]),
        "training_phishing_rows": len(phishing["train"]),
        "training_legitimate_sources": {
            "status_1_dataset": legacy_needed["train"],
            "tranco_https": tranco_needed["train"],
        },
        "train_end_utc": train_end.isoformat(),
        "diagnostic_start_utc": diagnostic_start.isoformat(),
        "threshold": threshold,
        "validation": score(
            model, legitimate["validation"], phishing["validation"], threshold
        ),
        "diagnostic": score(
            model, legitimate["diagnostic"], phishing["diagnostic"], threshold
        ),
        "feature_names": list(MODEL_FEATURE_NAMES),
        "rejected_rows": {
            "phishtank": phishing_rejected,
            "legitimate_dataset": legitimate_rejected,
        },
        "source_sha256": {
            "phishtank": file_sha256(phishing_path),
            "legitimate_dataset_zip": file_sha256(legitimate_zip),
            "tranco_zip": file_sha256(tranco_zip),
        },
        "random_seed": seed,
        "generated_at": generated_at,
        "warning": (
            "The diagnostic period has informed model assessment and must not be reused as "
            "the final untouched test after further tuning."
        ),
    }
    bundle = {
        "model": model,
        "feature_names": list(MODEL_FEATURE_NAMES),
        "model_type": "RandomForestClassifier",
        "threshold": threshold,
        "trained_at": generated_at,
    }

    model_path = Path(model_path)
    metrics_path = Path(metrics_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path = model_path.with_name(f"{model_path.stem}_candidate{model_path.suffix}")
    backup_path = model_path.with_name(f"{model_path.stem}_pre_raw{model_path.suffix}")
    joblib.dump(bundle, candidate_path)
    if model_path.exists():
        shutil.copy2(model_path, backup_path)
    shutil.copy2(candidate_path, model_path)
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return bundle, metrics


def main():
    parser = argparse.ArgumentParser(description="Retrain PhishGuard from dated raw URLs.")
    parser.add_argument("--phishing-dataset", type=Path, required=True)
    parser.add_argument("--legitimate-dataset-zip", type=Path, required=True)
    parser.add_argument("--tranco-zip", type=Path, required=True)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--train-end", required=True)
    parser.add_argument("--diagnostic-start", required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    _, metrics = retrain(
        args.phishing_dataset,
        args.legitimate_dataset_zip,
        args.tranco_zip,
        args.model,
        args.metrics,
        datetime.fromisoformat(args.train_end.replace("Z", "+00:00")),
        datetime.fromisoformat(args.diagnostic_start.replace("Z", "+00:00")),
        args.seed,
    )
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
