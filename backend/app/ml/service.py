from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import shap

from app.ml.features import MODEL_FEATURE_NAMES, extract_url_features


FEATURE_LABELS = {
    "url_length": "URL length",
    "hostname_length": "Hostname length",
    "path_length": "Path length",
    "query_length": "Query length",
    "digit_count": "Number of digits",
    "dot_count": "Number of dots",
    "hyphen_count": "Number of hyphens",
    "at_count": "At-sign usage",
    "percent_count": "Encoded characters",
    "subdomain_count": "Number of subdomains",
    "path_depth": "Path depth",
    "query_parameter_count": "Query parameters",
    "suspicious_keyword_count": "Suspicious keywords",
    "uses_https": "HTTPS usage",
    "has_ip_hostname": "IP address hostname",
    "has_explicit_port": "Explicit network port",
    "has_punycode": "Punycode hostname",
    "uses_known_shortener": "Known URL shortener",
    "url_entropy": "Character randomness",
}


@lru_cache(maxsize=4)
def load_bundle(model_path):
    path = Path(model_path)
    if not path.is_file():
        raise FileNotFoundError(f"Model artifact not found: {path}")
    bundle = joblib.load(path)
    if not {"model", "feature_names"}.issubset(bundle):
        raise ValueError("Invalid model bundle")
    if tuple(bundle["feature_names"]) != MODEL_FEATURE_NAMES:
        raise ValueError("Model feature schema does not match the application")
    return bundle


def phishing_shap_values(model, row):
    values = np.asarray(shap.TreeExplainer(model).shap_values(row))
    if values.ndim == 3:
        return values[0, :, 1]
    if values.ndim == 2 and values.shape[0] == 2:
        return values[1]
    if values.ndim == 2:
        return values[0]
    raise ValueError("Unsupported SHAP output shape")


def predict_url(url, model_path):
    bundle = load_bundle(str(model_path))
    features = extract_url_features(url)
    row = np.asarray([[features[name] for name in MODEL_FEATURE_NAMES]], dtype=float)
    model = bundle["model"]
    probability = float(model.predict_proba(row)[0, 1])
    shap_values = phishing_shap_values(model, row)
    ranked = sorted(
        zip(MODEL_FEATURE_NAMES, shap_values, strict=True),
        key=lambda item: abs(float(item[1])),
        reverse=True,
    )[:5]
    explanations = [
        {
            "feature": feature_name,
            "label": FEATURE_LABELS[feature_name],
            "value": features[feature_name],
            "impact": round(float(impact), 6),
            "direction": "increases risk" if impact > 0 else "decreases risk",
        }
        for feature_name, impact in ranked
    ]
    return {
        "prediction": "phishing" if probability >= 0.5 else "legitimate",
        "phishing_probability": round(probability, 6),
        "confidence": round(max(probability, 1 - probability), 6),
        "top_factors": explanations,
        "features": features,
        "model_type": bundle.get("model_type", type(model).__name__),
    }
