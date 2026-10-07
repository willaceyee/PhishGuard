import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from functools import wraps
from threading import Lock

from cryptography.fernet import Fernet, InvalidToken
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models import Campaign, SendingProfile, User, utc_now


sending_profiles = Blueprint("sending_profiles", __name__, url_prefix="/api/sending-profile")
PROFILE_STATE_LOCK = Lock()


def serialized_profile_change(operation):
    @wraps(operation)
    def serialized(*args, **kwargs):
        with PROFILE_STATE_LOCK:
            # Discard state loaded before another request finished its test.
            db.session.rollback()
            return operation(*args, **kwargs)
    return serialized


@sending_profiles.errorhandler(SQLAlchemyError)
def handle_persistence_error(_error):
    db.session.rollback()
    return jsonify(error="sending_profile_persistence_failed"), 503


def cipher():
    value = current_app.config["SENDING_PROFILE_ENCRYPTION_KEY"]
    if not value:
        raise RuntimeError("Sending-profile encryption is not configured")
    return Fernet(value.encode())


def encrypt_app_password(value: str) -> str:
    normalized = "".join(value.split())
    if not normalized:
        raise ValueError("Google app password is required")
    return cipher().encrypt(normalized.encode()).decode()


def decrypt_app_password(value: str) -> str:
    return cipher().decrypt(value.encode()).decode()


def profile_updates(data, creating=False):
    if not isinstance(data, dict):
        raise ValueError("invalid_profile")
    if "provider" in data and data["provider"] != "gmail":
        raise ValueError("invalid_provider")
    updates = {}
    for field in ("name", "from_name", "from_email", "app_password"):
        if not creating and field not in data:
            continue
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("invalid_profile")
        value = value.strip()
        if (field == "name" and len(value) > 160) or (
            field == "from_name" and len(value) > 120
        ):
            raise ValueError("invalid_profile")
        if field == "from_email":
            value = value.lower()
            local = value.removesuffix("@gmail.com")
            if len(local) > 64 or not re.fullmatch(
                r"[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*@gmail\.com",
                value,
            ):
                raise ValueError("invalid_gmail_address")
        updates[field] = value
    if not creating and "enabled" in data:
        if not isinstance(data["enabled"], bool):
            raise ValueError("invalid_enabled")
        updates["enabled"] = data["enabled"]
    return updates


@sending_profiles.get("")
@jwt_required()
def get_profile():
    profile = db.session.scalar(db.select(SendingProfile))
    return jsonify(profile=profile.to_safe_dict() if profile else None)


@sending_profiles.post("")
@jwt_required()
@serialized_profile_change
def create_profile():
    if db.session.scalar(db.select(SendingProfile)):
        return jsonify(error="sending_profile_exists"), 409
    try:
        updates = profile_updates(request.get_json(silent=True), creating=True)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    try:
        updates["encrypted_app_password"] = encrypt_app_password(updates.pop("app_password"))
    except (RuntimeError, ValueError):
        return jsonify(error="gmail_credentials_unavailable"), 503
    profile = SendingProfile(**updates)
    db.session.add(profile)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="sending_profile_exists"), 409
    return jsonify(profile=profile.to_safe_dict()), 201


@sending_profiles.patch("")
@jwt_required()
@serialized_profile_change
def update_profile():
    profile = db.session.scalar(db.select(SendingProfile))
    if profile is None:
        return jsonify(error="sending_profile_not_found"), 404
    try:
        updates = profile_updates(request.get_json(silent=True))
    except ValueError as error:
        return jsonify(error=str(error)), 400
    credentials_changed = "app_password" in updates or (
        "from_email" in updates and updates["from_email"] != profile.from_email
    )
    if "app_password" in updates:
        try:
            updates["encrypted_app_password"] = encrypt_app_password(updates.pop("app_password"))
        except (RuntimeError, ValueError):
            return jsonify(error="gmail_credentials_unavailable"), 503
    if credentials_changed:
        profile.last_test_succeeded = False
        profile.last_tested_at = None
    for field, value in updates.items():
        setattr(profile, field, value)
    db.session.commit()
    return jsonify(profile=profile.to_safe_dict())


@sending_profiles.delete("")
@jwt_required()
@serialized_profile_change
def delete_profile():
    profile = db.session.scalar(db.select(SendingProfile))
    if profile is not None:
        if db.session.scalar(
            db.select(Campaign.campaign_id)
            .where(Campaign.sending_profile_id == profile.profile_id)
            .limit(1)
        ) is not None:
            return jsonify(error="sending_profile_in_use"), 409
        db.session.delete(profile)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify(error="sending_profile_in_use"), 409
    return "", 204


def test_gmail_profile(profile: SendingProfile) -> None:
    if not profile.encrypted_app_password:
        raise RuntimeError("Gmail credentials are unavailable")
    password = decrypt_app_password(profile.encrypted_app_password)
    message = EmailMessage()
    message["Subject"] = "[SECURITY SIMULATION] PhishGuard connection test"
    message["From"] = formataddr((profile.from_name, profile.from_email))
    message["To"] = profile.from_email
    message["X-PhishGuard-Simulation"] = "authorized-training"
    message.set_content(
        "This is a PhishGuard security simulation connection test sent to your own "
        "approved Gmail address. No action is required."
    )
    context = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as smtp:
        smtp.starttls(context=context)
        smtp.login(profile.from_email, password)
        smtp.send_message(message)


@sending_profiles.post("/test")
@jwt_required()
@serialized_profile_change
def test_profile_connection():
    profile = db.session.scalar(db.select(SendingProfile))
    if profile is None:
        return jsonify(error="sending_profile_not_found"), 404
    profile.last_tested_at = utc_now()
    profile.last_test_succeeded = False
    approved_user = db.session.scalar(
        db.select(User).where(
            User.email == profile.from_email,
            User.simulation_email_approved.is_(True),
        )
    )
    if approved_user is None:
        db.session.commit()
        return jsonify(error="gmail_sender_not_approved"), 403
    error = None
    status = 502
    try:
        test_gmail_profile(profile)
    except smtplib.SMTPAuthenticationError:
        error = "gmail_authentication_failed"
    except smtplib.SMTPException:
        error = "gmail_provider_rejected"
    except OSError:
        error = "gmail_connection_failed"
    except (RuntimeError, ValueError, InvalidToken):
        error = "gmail_credentials_unavailable"
        status = 503
    else:
        profile.last_test_succeeded = True
    db.session.commit()
    if error:
        return jsonify(error=error), status
    return jsonify(profile=profile.to_safe_dict())
