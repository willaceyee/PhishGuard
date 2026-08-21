from flask import Blueprint, jsonify


main = Blueprint("main", __name__)


@main.get("/")
def home():
    return jsonify(message="PhishGuard backend is running")


@main.get("/api/health")
def health():
    return jsonify(message="PhishGuard backend is running", status="healthy")

