from pathlib import Path

import pytest

from app.ml.features import FEATURE_NAMES, extract_url_features, normalize_url
from app.ml.prepare_demo_data import write_demo_dataset
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
