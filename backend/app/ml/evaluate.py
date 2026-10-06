import argparse
import csv
import hashlib
import json
import random
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    classification_report,
    confusion_matrix,
    roc_auc_score,
)

from app.ml.features import MODEL_FEATURE_NAMES, extract_url_features
from app.ml.service import load_bundle


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL = PROJECT_ROOT / "ml_model" / "artifacts" / "phishguard_url_model.joblib"
DEFAULT_OUTPUT = PROJECT_ROOT / "ml_model" / "artifacts" / "unseen_evaluation.json"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def valid_feature_row(url, feature_names=MODEL_FEATURE_NAMES):
    try:
        features = extract_url_features(url)
    except ValueError:
        return None
    return [features[name] for name in feature_names]


def load_post_training_phishing(path, cutoff):
    urls = set()
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
            if (
                row["verified"].lower() == "yes"
                and row["online"].lower() == "yes"
                and verified_at > cutoff
                and valid_feature_row(row["url"]) is not None
            ):
                urls.add(row["url"].strip())
    return sorted(urls), rejected


def load_legitimate_urls(zip_path, excluded_urls):
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
                url = row["url"].strip()
                # This dataset defines status 1 as legitimate and 0 as malicious.
                if row["status"].strip() != "1" or url in excluded_urls:
                    continue
                if valid_feature_row(url) is None:
                    rejected += 1
                    continue
                urls.add(url)
    return sorted(urls), rejected


def evaluate(phishing_path, legitimate_zip, model_path, output_path, cutoff, seed=42):
    phishing_urls, phishing_rejected = load_post_training_phishing(phishing_path, cutoff)
    legitimate_urls, legitimate_rejected = load_legitimate_urls(
        legitimate_zip, set(phishing_urls)
    )
    sample_size = min(len(phishing_urls), len(legitimate_urls))
    if sample_size < 100:
        raise ValueError("Evaluation needs at least 100 valid URLs from each class")

    rng = random.Random(seed)
    phishing_sample = rng.sample(phishing_urls, sample_size)
    legitimate_sample = rng.sample(legitimate_urls, sample_size)
    urls = legitimate_sample + phishing_sample
    labels = np.asarray([0] * sample_size + [1] * sample_size)
    bundle = load_bundle(str(model_path))
    model = bundle["model"]
    feature_names = tuple(bundle["feature_names"])
    rows = np.asarray(
        [valid_feature_row(url, feature_names) for url in urls], dtype=float
    )
    probabilities = model.predict_proba(rows)[:, 1]
    predictions = (probabilities >= 0.5).astype(int)
    report = {
        "evaluation_type": "temporally unseen balanced external test",
        "cutoff_utc": cutoff.isoformat(),
        "random_seed": seed,
        "rows": int(len(labels)),
        "legitimate_rows": sample_size,
        "phishing_rows": sample_size,
        "accuracy": round(float(accuracy_score(labels, predictions)), 6),
        "roc_auc": round(float(roc_auc_score(labels, probabilities)), 6),
        "pr_auc": round(float(average_precision_score(labels, probabilities)), 6),
        "confusion_matrix": confusion_matrix(labels, predictions).tolist(),
        "classification_report": classification_report(
            labels, predictions, output_dict=True, zero_division=0
        ),
        "rejected_rows": {
            "phishtank": phishing_rejected,
            "legitimate_dataset": legitimate_rejected,
        },
        "source_sha256": {
            "phishtank": sha256(phishing_path),
            "legitimate_dataset_zip": sha256(legitimate_zip),
        },
        "label_definition": {"0": "legitimate", "1": "phishing"},
        "feature_names": list(feature_names),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "warning": (
            "The legitimate source's status labels are externally supplied and its collection "
            "date is unavailable; results measure cross-source performance, not production safety."
        ),
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description="Evaluate the trained model without retraining.")
    parser.add_argument("--phishing-dataset", type=Path, required=True)
    parser.add_argument("--legitimate-dataset-zip", type=Path, required=True)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cutoff", required=True, help="Training cutoff as an ISO 8601 timestamp")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    cutoff = datetime.fromisoformat(args.cutoff.replace("Z", "+00:00"))
    report = evaluate(
        args.phishing_dataset,
        args.legitimate_dataset_zip,
        args.model,
        args.output,
        cutoff,
        args.seed,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
