from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required

from app.ml.features import normalize_url
from app.ml.service import predict_url


detection = Blueprint("detection", __name__, url_prefix="/api/detection")


@detection.post("/predict")
@jwt_required()
def predict():
    data = request.get_json(silent=True) or {}
    try:
        normalized_url, _ = normalize_url(data.get("url"))
        result = predict_url(normalized_url, current_app.config["ML_MODEL_PATH"])
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except FileNotFoundError:
        return jsonify(error="Detection model is not available; train it first"), 503
    return jsonify(url=normalized_url, **result)
