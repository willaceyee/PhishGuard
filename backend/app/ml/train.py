import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, roc_auc_score
from sklearn.model_selection import train_test_split

from app.ml.features import FEATURE_NAMES, feature_vector


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET = PROJECT_ROOT / "ml_model" / "data" / "demo_urls.csv"
DEFAULT_MODEL = PROJECT_ROOT / "ml_model" / "artifacts" / "phishguard_url_model.joblib"
DEFAULT_METRICS = PROJECT_ROOT / "ml_model" / "artifacts" / "metrics.json"


def load_dataset(dataset_path):
    rows = []
    labels = []
    with Path(dataset_path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not {"url", "label"}.issubset(reader.fieldnames):
            raise ValueError("Dataset must contain url and label columns")
        for line_number, row in enumerate(reader, start=2):
            try:
                label = int(row["label"])
                if label not in (0, 1):
                    raise ValueError
                rows.append(feature_vector(row["url"]))
                labels.append(label)
            except (TypeError, ValueError) as error:
                raise ValueError(f"Invalid dataset row {line_number}") from error
    if len(rows) < 40 or min(labels.count(0), labels.count(1)) < 20:
        raise ValueError("Dataset needs at least 20 examples from each class")
    return rows, labels


def train_model(dataset_path=DEFAULT_DATASET, model_path=DEFAULT_MODEL, metrics_path=DEFAULT_METRICS):
    rows, labels = load_dataset(dataset_path)
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
        "confusion_matrix": confusion_matrix(y_test, predictions).tolist(),
        "classification_report": classification_report(
            y_test, predictions, output_dict=True, zero_division=0
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "warning": "Synthetic development data; metrics do not represent real-world performance.",
    }
    bundle = {
        "model": model,
        "feature_names": list(FEATURE_NAMES),
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
