from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required

from app.extensions import db
from app.models import Admin


auth = Blueprint("auth", __name__, url_prefix="/api/auth")


def normalized_email(value):
    return value.strip().lower() if isinstance(value, str) else ""


@auth.post("/bootstrap")
def bootstrap_admin():
    if db.session.execute(db.select(Admin.admin_id).limit(1)).first():
        return jsonify(error="An administrator already exists"), 409

    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    email = normalized_email(data.get("email"))
    password = str(data.get("password", ""))
    if not name or not email or len(password) < 8:
        return jsonify(error="Name, email, and a password of at least 8 characters are required"), 400

    admin = Admin(name=name, email=email)
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    return jsonify(admin=admin.to_dict()), 201


@auth.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    email = normalized_email(data.get("email"))
    password = str(data.get("password", ""))
    admin = db.session.scalar(db.select(Admin).where(Admin.email == email))

    if admin is None or not admin.check_password(password):
        return jsonify(error="Invalid email or password"), 401

    token = create_access_token(identity=str(admin.admin_id))
    return jsonify(access_token=token, admin=admin.to_dict())


@auth.get("/me")
@jwt_required()
def current_admin():
    admin = db.session.get(Admin, int(get_jwt_identity()))
    if admin is None:
        return jsonify(error="Administrator not found"), 404
    return jsonify(admin=admin.to_dict())

