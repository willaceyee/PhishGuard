import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    classification_report,
    confusion_matrix,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

from app.ml.features import MODEL_FEATURE_NAMES, PRECOMPUTED_FEATURE_NAMES, feature_vector


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET = PROJECT_ROOT / "ml_model" / "data" / "demo_urls.csv"
DEFAULT_MODEL = PROJECT_ROOT / "ml_model" / "artifacts" / "phishguard_url_model.joblib"
DEFAULT_METRICS = PROJECT_ROOT / "ml_model" / "artifacts" / "metrics.json"

PRECOMPUTED_COLUMNS = {
    "url_length": "UrlLength",
    "hostname_length": "HostnameLength",
    "path_length": "PathLength",
    "query_length": "QueryLength",
    "digit_count": "NumNumericChars",
    "dot_count": "NumDots",
    "hyphen_count": "NumDash",
    "at_count": "AtSymbol",
    "percent_count": "NumPercent",
    "subdomain_count": "SubdomainLevel",
    "path_depth": "PathLevel",
    "query_parameter_count": "NumQueryComponents",
    "suspicious_keyword_count": "NumSensitiveWords",
    "uses_https": "NoHttps",
    "has_ip_hostname": "IpAddress",
}


def load_dataset(dataset_path):
    rows = []
    labels = []
    with Path(dataset_path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or ())
        is_raw = {"url", "label"}.issubset(fields)
        is_precomputed = {"CLASS_LABEL", *PRECOMPUTED_COLUMNS.values()}.issubset(fields)
        if not is_raw and not is_precomputed:
            raise ValueError("Dataset must contain url/label or supported precomputed columns")
        for line_number, row in enumerate(reader, start=2):
            try:
                label = int(row["label"] if is_raw else row["CLASS_LABEL"])
                if label not in (0, 1):
                    raise ValueError
                if is_raw:
                    values = feature_vector(row["url"])
                else:
                    values = []
                    for feature_name in PRECOMPUTED_FEATURE_NAMES:
                        value = float(row[PRECOMPUTED_COLUMNS[feature_name]])
                        # Dataset encodes absence of HTTPS, while the live extractor
                        # encodes its presence.
                        values.append(1.0 - value if feature_name == "uses_https" else value)
                rows.append(values)
                labels.append(label)
            except (TypeError, ValueError) as error:
                raise ValueError(f"Invalid dataset row {line_number}") from error
    if len(rows) < 40 or min(labels.count(0), labels.count(1)) < 20:
        raise ValueError("Dataset needs at least 20 examples from each class")
    feature_names = MODEL_FEATURE_NAMES if is_raw else PRECOMPUTED_FEATURE_NAMES
    return rows, labels, feature_names


def train_model(dataset_path=DEFAULT_DATASET, model_path=DEFAULT_MODEL, metrics_path=DEFAULT_METRICS):
    rows, labels, feature_names = load_dataset(dataset_path)
    dataset_path = Path(dataset_path)
    x_train, x_test, y_train, y_test = train_test_split(
        rows, labels, test_size=0.25, random_state=42, stratify=labels
    )
    model = RandomForestClassifier(
        n_estimators=300,
        max_depth=12,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(x_train, y_train)
    predictions = model.predict(x_test)
    probabilities = model.predict_proba(x_test)[:, 1]
    metrics = {
        "dataset_rows": len(rows),
        "training_rows": len(x_train),
        "test_rows": len(x_test),
        "accuracy": round(float(accuracy_score(y_test, predictions)), 6),
        "roc_auc": round(float(roc_auc_score(y_test, probabilities)), 6),
        "pr_auc": round(float(average_precision_score(y_test, probabilities)), 6),
        "confusion_matrix": confusion_matrix(y_test, predictions).tolist(),
        "classification_report": classification_report(
            y_test, predictions, output_dict=True, zero_division=0
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "feature_names": list(feature_names),
        "label_definition": {"0": "legitimate", "1": "phishing"},
        "warning": (
            "Evaluation uses a random stratified split of precomputed features; "
            "it does not measure temporal generalization to newly emerging attacks."
            if dataset_path.name == "Phishing_Legitimate_full.csv"
            else "Synthetic development data; metrics do not represent real-world performance."
        ),
    }
    bundle = {
        "model": model,
        "feature_names": list(feature_names),
        "model_type": "RandomForestClassifier",
        "trained_at": metrics["generated_at"],
    }
    model_path = Path(model_path)
    metrics_path = Path(metrics_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, model_path)
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return bundle, metrics


def main():
    parser = argparse.ArgumentParser(description="Train the PhishGuard URL classifier.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    args = parser.parse_args()
    _, metrics = train_model(args.dataset, args.model, args.metrics)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
