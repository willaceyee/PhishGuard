import csv
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.ml.features import FEATURE_NAMES, extract_url_features, normalize_url
from app.ml.evaluate import evaluate
from app.ml.prepare_demo_data import write_demo_dataset
from app.ml.retrain_raw import retrain
from app.ml.service import load_bundle
from app.ml.train import train_model


@pytest.fixture(scope="module")
def trained_model(tmp_path_factory):
    directory = tmp_path_factory.mktemp("ml")
    dataset_path = directory / "urls.csv"
    model_path = directory / "model.joblib"
    metrics_path = directory / "metrics.json"
    write_demo_dataset(dataset_path, samples_per_class=30)
    _, metrics = train_model(dataset_path, model_path, metrics_path)
    load_bundle.cache_clear()
    assert metrics["dataset_rows"] == 60
    assert model_path.is_file()
    assert metrics_path.is_file()
    return model_path


def test_feature_extraction_is_offline_and_deterministic():
    features = extract_url_features(
        "http://192.0.2.10:8080/verify-account/login?token=123456&confirm=true"
    )
    assert tuple(features) == FEATURE_NAMES
    assert features["has_ip_hostname"] == 1
    assert features["subdomain_count"] == 0
    assert features["has_explicit_port"] == 1
    assert features["suspicious_keyword_count"] >= 3
    assert features["query_parameter_count"] == 2


@pytest.mark.parametrize(
    "value",
    (None, "", "javascript:alert(1)", "ftp://files.example/document", "https://bad host.example"),
)
def test_invalid_urls_are_rejected(value):
    with pytest.raises(ValueError):
        normalize_url(value)


def test_prediction_api_returns_shap_explanation(client, auth_headers, app, trained_model):
    app.config["ML_MODEL_PATH"] = str(trained_model)
    response = client.post(
        "/api/detection/predict",
        headers=auth_headers,
        json={"url": "http://192.0.2.55:8080/verify-account?token=998877"},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["prediction"] in {"phishing", "legitimate"}
    assert 0 <= body["phishing_probability"] <= 1
    assert body["model_type"] == "RandomForestClassifier"
    assert len(body["features"]) == len(FEATURE_NAMES)
    assert len(body["top_factors"]) == 5
    assert {"feature", "label", "value", "impact", "direction"}.issubset(
        body["top_factors"][0]
    )


def test_prediction_api_requires_auth_and_model(client, auth_headers, app, tmp_path):
    assert (
        client.post("/api/detection/predict", json={"url": "https://docs.example"}).status_code
        == 401
    )
    app.config["ML_MODEL_PATH"] = str(Path(tmp_path) / "missing.joblib")
    response = client.post(
        "/api/detection/predict",
        headers=auth_headers,
        json={"url": "https://docs.example"},
    )
    assert response.status_code == 503


def test_prediction_api_validates_input(client, auth_headers, app, trained_model):
    app.config["ML_MODEL_PATH"] = str(trained_model)
    response = client.post(
        "/api/detection/predict",
        headers=auth_headers,
        json={"url": "file:///etc/passwd"},
    )
    assert response.status_code == 400


def test_external_evaluation_does_not_retrain_model(tmp_path, trained_model):
    phishing_path = tmp_path / "phishtank.csv"
    legitimate_zip = tmp_path / "legitimate.zip"
    output_path = tmp_path / "evaluation.json"
    cutoff = datetime(2026, 8, 22, tzinfo=timezone.utc)

    with phishing_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=("url", "verified", "verification_time", "online")
        )
        writer.writeheader()
        for index in range(100):
            writer.writerow(
                {
                    "url": f"http://verify-{index}.invalid/account/login",
                    "verified": "yes",
                    "verification_time": "2026-08-23T00:00:00+00:00",
                    "online": "yes",
                }
            )

    legitimate_rows = ["url,status"] + [
        f"https://docs-{index}.example.org,1" for index in range(100)
    ]
    with zipfile.ZipFile(legitimate_zip, "w") as archive:
        archive.writestr("urls.csv", "\n".join(legitimate_rows))

    before_hash = trained_model.read_bytes()
    report = evaluate(
        phishing_path,
        legitimate_zip,
        trained_model,
        output_path,
        cutoff,
    )

    assert report["rows"] == 200
    assert report["phishing_rows"] == 100
    assert report["legitimate_rows"] == 100
    assert 0 <= report["accuracy"] <= 1
    assert json.loads(output_path.read_text(encoding="utf-8"))["random_seed"] == 42
    assert trained_model.read_bytes() == before_hash


def test_raw_retraining_uses_date_separated_balanced_splits(tmp_path):
    phishing_path = tmp_path / "phishtank.csv"
    legitimate_zip = tmp_path / "legitimate.zip"
    tranco_zip = tmp_path / "tranco.zip"
    model_path = tmp_path / "model.joblib"
    metrics_path = tmp_path / "raw_metrics.json"
    train_end = datetime(2026, 8, 1, tzinfo=timezone.utc)
    diagnostic_start = datetime(2026, 8, 22, tzinfo=timezone.utc)

    with phishing_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=("url", "verified", "verification_time", "online")
        )
        writer.writeheader()
        periods = ((20, "2026-07-01"), (10, "2026-08-10"), (10, "2026-08-25"))
        offset = 0
        for count, date in periods:
            for index in range(offset, offset + count):
                writer.writerow(
                    {
                        "url": f"http://secure-{index}.invalid/verify/login?id={index}",
                        "verified": "yes",
                        "verification_time": f"{date}T00:00:00+00:00",
                        "online": "yes",
                    }
                )
            offset += count

    legitimate_rows = ["url,status"] + [
        f"https://site-{index}.example.org,1" for index in range(40)
    ]
    with zipfile.ZipFile(legitimate_zip, "w") as archive:
        archive.writestr("urls.csv", "\n".join(legitimate_rows))
    with zipfile.ZipFile(tranco_zip, "w") as archive:
        archive.writestr(
            "top-1m.csv",
            "\n".join(f"{index + 1},popular-{index}.example" for index in range(40)),
        )

    model_path.write_bytes(b"previous artifact")
    _, metrics = retrain(
        phishing_path,
        legitimate_zip,
        tranco_zip,
        model_path,
        metrics_path,
        train_end,
        diagnostic_start,
    )

    assert metrics["training_rows"] == 40
    assert metrics["validation"]["rows"] == 20
    assert metrics["diagnostic"]["rows"] == 20
    assert len(metrics["feature_names"]) == len(FEATURE_NAMES) - 1
    assert model_path.with_name("model_pre_raw.joblib").read_bytes() == b"previous artifact"
    assert json.loads(metrics_path.read_text(encoding="utf-8"))["random_seed"] == 42
