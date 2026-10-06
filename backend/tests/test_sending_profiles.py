import smtplib
import ssl
from email.utils import getaddresses

import pytest
from unittest.mock import patch
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    Admin,
    Campaign,
    CampaignRecipient,
    EmailTemplate,
    SendingProfile,
    TrackingEvent,
    User,
    utc_now,
)
from app.sending_profiles import decrypt_app_password, encrypt_app_password


@pytest.fixture()
def profile_payload():
    return {
        "name": " Personal Gmail ",
        "from_name": " Simulation Admin ",
        "from_email": " Owner@GMAIL.COM ",
        "app_password": "abcd efgh ijkl mnop",
    }


@pytest.fixture()
def stored_profile(app):
    profile = SendingProfile(
        name="Personal Gmail",
        from_name="Simulation Admin",
        from_email="owner@gmail.com",
        encrypted_app_password=encrypt_app_password("abcd efgh ijkl mnop"),
    )
    db.session.add(profile)
    db.session.commit()
    return profile


def assert_safe_response(response, profile):
    text_response = response.get_data(as_text=True)
    for secret in (
        "abcd efgh ijkl mnop",
        "abcdefghijklmnop",
        profile.encrypted_app_password,
        "encrypted_app_password",
        '"app_password"',
    ):
        assert secret not in text_response


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/sending-profile"),
        ("post", "/api/sending-profile"),
        ("patch", "/api/sending-profile"),
        ("delete", "/api/sending-profile"),
        ("post", "/api/sending-profile/test"),
    ],
)
def test_profile_endpoints_require_authentication(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_get_absent_profile(client, auth_headers):
    response = client.get("/api/sending-profile", headers=auth_headers)
    assert response.status_code == 200
    assert response.get_json() == {"profile": None}


def test_create_profile_normalizes_and_hides_credentials(
    client, auth_headers, profile_payload, caplog
):
    response = client.post(
        "/api/sending-profile", json=profile_payload, headers=auth_headers
    )
    assert response.status_code == 201
    profile = db.session.scalar(db.select(SendingProfile))
    safe = response.get_json()["profile"]
    assert safe["name"] == "Personal Gmail"
    assert safe["from_name"] == "Simulation Admin"
    assert safe["from_email"] == "owner@gmail.com"
    assert safe["provider"] == "gmail"
    assert safe["enabled"] is False
    assert safe["credential_configured"] is True
    assert decrypt_app_password(profile.encrypted_app_password) == "abcdefghijklmnop"
    assert_safe_response(response, profile)
    assert "abcdefghijklmnop" not in caplog.text
    assert profile.encrypted_app_password not in caplog.text


def test_second_profile_returns_conflict(
    client, auth_headers, profile_payload, stored_profile
):
    response = client.post(
        "/api/sending-profile", json=profile_payload, headers=auth_headers
    )
    assert response.status_code == 409
    assert db.session.query(SendingProfile).count() == 1
    assert_safe_response(response, stored_profile)


def test_get_profile_is_safe(client, auth_headers, stored_profile):
    response = client.get("/api/sending-profile", headers=auth_headers)
    assert response.status_code == 200
    assert response.get_json()["profile"]["from_email"] == "owner@gmail.com"
    assert_safe_response(response, stored_profile)


@pytest.mark.parametrize("field", ["name", "from_name", "from_email", "app_password"])
@pytest.mark.parametrize("value", [None, "", " \t ", 42])
def test_create_rejects_missing_or_invalid_required_fields(
    client, auth_headers, profile_payload, field, value
):
    profile_payload[field] = value
    response = client.post(
        "/api/sending-profile", json=profile_payload, headers=auth_headers
    )
    assert response.status_code == 400
    assert db.session.query(SendingProfile).count() == 0


@pytest.mark.parametrize(
    "email",
    [
        "owner@example.com", "owner@gmail.com.evil", "owner@googlemail.com",
        "@gmail.com", "owner@@gmail.com", "owner name@gmail.com",
        "owner..name@gmail.com", ".owner@gmail.com", "owner.\n@gmail.com",
    ],
)
@pytest.mark.parametrize("method", ["post", "patch"])
def test_profile_rejects_invalid_gmail_addresses(
    client, auth_headers, profile_payload, stored_profile, email, method
):
    if method == "post":
        db.session.delete(stored_profile)
        db.session.commit()
    profile_payload["from_email"] = email
    data = profile_payload if method == "post" else {"from_email": email}
    response = getattr(client, method)(
        "/api/sending-profile", json=data, headers=auth_headers
    )
    assert response.status_code == 400


@pytest.mark.parametrize("method", ["post", "patch"])
def test_profile_rejects_other_providers(
    client, auth_headers, profile_payload, stored_profile, method
):
    if method == "post":
        db.session.delete(stored_profile)
        db.session.commit()
    data = {**profile_payload, "provider": "other"} if method == "post" else {"provider": "other"}
    assert getattr(client, method)(
        "/api/sending-profile", json=data, headers=auth_headers
    ).status_code == 400


def test_metadata_patch_preserves_ciphertext(client, auth_headers, stored_profile):
    ciphertext = stored_profile.encrypted_app_password
    response = client.patch(
        "/api/sending-profile",
        json={"name": " New profile ", "from_name": " New sender ", "from_email": " NEW@GMAIL.COM "},
        headers=auth_headers,
    )
    assert response.status_code == 200
    db.session.expire_all()
    assert stored_profile.name == "New profile"
    assert stored_profile.from_name == "New sender"
    assert stored_profile.from_email == "new@gmail.com"
    assert stored_profile.encrypted_app_password == ciphertext
    assert_safe_response(response, stored_profile)


def test_password_patch_replaces_ciphertext(client, auth_headers, stored_profile):
    ciphertext = stored_profile.encrypted_app_password
    response = client.patch(
        "/api/sending-profile",
        json={"app_password": "qrst uvwx yzab cdef"}, headers=auth_headers,
    )
    assert response.status_code == 200
    db.session.expire_all()
    assert stored_profile.encrypted_app_password != ciphertext
    assert decrypt_app_password(stored_profile.encrypted_app_password) == "qrstuvwxyzabcdef"
    assert "qrstuvwxyzabcdef" not in response.get_data(as_text=True)
    assert_safe_response(response, stored_profile)


@pytest.mark.parametrize("enabled", [True, False])
def test_profile_can_be_enabled_or_disabled(client, auth_headers, stored_profile, enabled):
    stored_profile.enabled = not enabled
    db.session.commit()
    response = client.patch(
        "/api/sending-profile", json={"enabled": enabled}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.get_json()["profile"]["enabled"] is enabled
    db.session.expire_all()
    assert stored_profile.enabled is enabled


@pytest.mark.parametrize(
    "data",
    [{"app_password": ""}, {"app_password": " \t "}, {"app_password": None},
     {"name": ""}, {"from_name": None}, {"enabled": "true"}, {"enabled": 1}],
)
def test_invalid_patch_is_atomic(client, auth_headers, stored_profile, data):
    ciphertext = stored_profile.encrypted_app_password
    response = client.patch(
        "/api/sending-profile", json={"name": "Changed", **data}, headers=auth_headers
    )
    assert response.status_code == 400
    db.session.expire_all()
    assert stored_profile.name == "Personal Gmail"
    assert stored_profile.encrypted_app_password == ciphertext


def test_delete_profile(client, auth_headers, stored_profile):
    response = client.delete("/api/sending-profile", headers=auth_headers)
    assert response.status_code == 204
    assert response.data == b""
    assert db.session.query(SendingProfile).count() == 0


@pytest.mark.parametrize("method,path", [("patch", "/api/sending-profile"), ("post", "/api/sending-profile/test")])
def test_missing_profile_returns_not_found(client, auth_headers, method, path):
    assert getattr(client, method)(path, json={}, headers=auth_headers).status_code == 404


def test_delete_absent_profile_is_idempotent(client, auth_headers):
    assert client.delete("/api/sending-profile", headers=auth_headers).status_code == 204


def test_delete_constraint_failure_is_safe(client, auth_headers, stored_profile, caplog):
    secret = stored_profile.encrypted_app_password
    with patch.object(db.session, "commit", side_effect=IntegrityError("secret SQL", {}, Exception(secret))):
        response = client.delete("/api/sending-profile", headers=auth_headers)
    assert response.status_code == 409
    assert db.session.query(SendingProfile).count() == 1
    assert_safe_response(response, stored_profile)
    assert secret not in caplog.text


def test_create_constraint_failure_is_safe(client, auth_headers, profile_payload, caplog):
    with patch.object(db.session, "commit", side_effect=IntegrityError("secret SQL", {}, Exception("abcdefghijklmnop"))):
        response = client.post("/api/sending-profile", json=profile_payload, headers=auth_headers)
    assert response.status_code == 409
    assert db.session.query(SendingProfile).count() == 0
    assert "abcdefghijklmnop" not in response.get_data(as_text=True)
    assert "abcdefghijklmnop" not in caplog.text


@pytest.fixture()
def approved_sender(app):
    user = User(name="Owner", email="owner@gmail.com", simulation_email_approved=True)
    db.session.add(user)
    db.session.commit()
    return user


def test_gmail_connection_uses_tls_and_sends_only_to_approved_sender(
    client, auth_headers, stored_profile, approved_sender, caplog
):
    with patch("smtplib.SMTP") as smtp_class, patch(
        "ssl.create_default_context", wraps=ssl.create_default_context
    ) as context_factory:
        smtp = smtp_class.return_value.__enter__.return_value
        response = client.post("/api/sending-profile/test", headers=auth_headers)
    assert response.status_code == 200
    smtp_class.assert_called_once_with("smtp.gmail.com", 587, timeout=10)
    context_factory.assert_called_once_with()
    smtp.starttls.assert_called_once()
    context = smtp.starttls.call_args.kwargs["context"]
    assert isinstance(context, ssl.SSLContext)
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
    smtp.login.assert_called_once_with("owner@gmail.com", "abcdefghijklmnop")
    smtp.send_message.assert_called_once()
    message = smtp.send_message.call_args.args[0]
    assert getaddresses(message.get_all("To")) == [("", "owner@gmail.com")]
    assert getaddresses(message.get_all("From")) == [("Simulation Admin", "owner@gmail.com")]
    assert message.get_all("Cc") is None
    assert message.get_all("Bcc") is None
    assert "security simulation" in message["Subject"].lower()
    assert "test" in message["Subject"].lower()
    assert "security simulation" in message.get_content().lower()
    assert "abcdefghijklmnop" not in message.as_string()
    db.session.expire_all()
    assert stored_profile.last_tested_at is not None
    assert stored_profile.last_test_succeeded is True
    assert response.get_json()["profile"]["last_test_succeeded"] is True
    assert_safe_response(response, stored_profile)
    assert "abcdefghijklmnop" not in caplog.text
    assert stored_profile.encrypted_app_password not in caplog.text


@pytest.mark.parametrize(
    "email,approved", [(None, False), ("owner@gmail.com", False),
                       ("different@gmail.com", True), ("Owner@gmail.com", True)],
)
def test_connection_requires_exact_approved_user_before_decryption(
    client, auth_headers, stored_profile, email, approved
):
    if email:
        db.session.add(User(name="Owner", email=email, simulation_email_approved=approved))
        db.session.commit()
    stored_profile.last_test_succeeded = True
    db.session.commit()
    with patch("app.sending_profiles.decrypt_app_password") as decrypt, patch("smtplib.SMTP") as smtp_class:
        response = client.post("/api/sending-profile/test", headers=auth_headers)
    assert response.status_code == 403
    decrypt.assert_not_called()
    smtp_class.assert_not_called()
    db.session.expire_all()
    assert stored_profile.last_tested_at is not None
    assert stored_profile.last_test_succeeded is False
    assert_safe_response(response, stored_profile)


@pytest.mark.parametrize(
    "error,code",
    [
        (smtplib.SMTPAuthenticationError(535, b"abcdefghijklmnop"), "gmail_authentication_failed"),
        (smtplib.SMTPException("abcdefghijklmnop"), "gmail_provider_rejected"),
        (OSError("abcdefghijklmnop"), "gmail_connection_failed"),
    ],
)
@pytest.mark.parametrize("stage", ["connect", "starttls", "login", "send_message"])
def test_connection_errors_are_safe_and_persist_failed_state(
    client, auth_headers, stored_profile, approved_sender, error, code, stage, caplog
):
    previous_test = utc_now()
    stored_profile.last_tested_at = previous_test
    stored_profile.last_test_succeeded = True
    db.session.commit()
    with patch("smtplib.SMTP") as smtp_class:
        if stage == "connect":
            smtp_class.side_effect = error
        else:
            smtp = smtp_class.return_value.__enter__.return_value
            getattr(smtp, stage).side_effect = error
        response = client.post("/api/sending-profile/test", headers=auth_headers)
    assert response.status_code == 502
    assert response.get_json() == {"error": code}
    db.session.expire_all()
    assert stored_profile.last_tested_at.replace(tzinfo=previous_test.tzinfo) >= previous_test
    assert stored_profile.last_test_succeeded is False
    assert_safe_response(response, stored_profile)
    assert "abcdefghijklmnop" not in caplog.text
    assert stored_profile.encrypted_app_password not in caplog.text


@pytest.mark.parametrize("failure", ["missing_key", "invalid_ciphertext", "missing_password"])
def test_unusable_credentials_fail_safely_and_persist_state(
    app, client, auth_headers, stored_profile, approved_sender, failure, caplog
):
    if failure == "missing_key":
        app.config["SENDING_PROFILE_ENCRYPTION_KEY"] = ""
    elif failure == "invalid_ciphertext":
        stored_profile.encrypted_app_password = "invalid-secret-ciphertext"
    else:
        stored_profile.encrypted_app_password = None
    stored_profile.last_test_succeeded = True
    db.session.commit()
    with patch("smtplib.SMTP") as smtp_class:
        response = client.post("/api/sending-profile/test", headers=auth_headers)
    assert response.status_code == 503
    assert response.get_json() == {"error": "gmail_credentials_unavailable"}
    smtp_class.assert_not_called()
    db.session.expire_all()
    assert stored_profile.last_tested_at is not None
    assert stored_profile.last_test_succeeded is False
    assert "invalid-secret-ciphertext" not in response.get_data(as_text=True)
    assert "invalid-secret-ciphertext" not in caplog.text


@pytest.mark.parametrize("method", ["post", "patch"])
def test_credential_update_without_encryption_key_is_safe(
    app, client, auth_headers, profile_payload, stored_profile, method
):
    if method == "post":
        db.session.delete(stored_profile)
        db.session.commit()
    app.config["SENDING_PROFILE_ENCRYPTION_KEY"] = ""
    data = profile_payload if method == "post" else {"name": "Changed", "app_password": "abcdefghijklmnop"}
    response = getattr(client, method)("/api/sending-profile", json=data, headers=auth_headers)
    assert response.status_code == 503
    assert response.get_json() == {"error": "gmail_credentials_unavailable"}
    assert "abcdefghijklmnop" not in response.get_data(as_text=True)
    if method == "patch":
        db.session.expire_all()
        assert stored_profile.name == "Personal Gmail"


def test_profile_stores_ciphertext_and_serializes_without_secrets(app):
    password = "abcd efgh ijkl mnop"
    profile = SendingProfile(
        name="Personal Gmail",
        from_name="Simulation Admin",
        from_email="simulation@gmail.com",
        encrypted_app_password=encrypt_app_password(password),
    )
    db.session.add(profile)
    db.session.commit()

    ciphertext = db.session.execute(
        text("SELECT encrypted_app_password FROM sending_profiles")
    ).scalar_one()
    assert ciphertext != password
    assert ciphertext != "abcdefghijklmnop"
    assert decrypt_app_password(ciphertext) == "abcdefghijklmnop"

    safe = profile.to_safe_dict()
    assert safe["credential_configured"] is True
    assert safe["provider"] == "gmail"
    assert safe["from_email"] == "simulation@gmail.com"
    assert safe["enabled"] is False
    assert safe["last_tested_at"] is None
    assert safe["last_test_succeeded"] is False
    assert safe["created_at"]
    assert safe["updated_at"]
    assert "encrypted_app_password" not in safe
    assert "app_password" not in safe
    assert password not in str(safe)
    assert "abcdefghijklmnop" not in str(safe)
    assert ciphertext not in str(safe)


def test_profile_serialization_handles_missing_credential_and_test_time(app):
    tested_at = utc_now()
    profile = SendingProfile(
        name="Personal Gmail",
        from_name="Simulation Admin",
        from_email="simulation@gmail.com",
        last_tested_at=tested_at,
        last_test_succeeded=True,
    )
    db.session.add(profile)
    db.session.commit()

    safe = profile.to_safe_dict()
    assert safe["credential_configured"] is False
    assert safe["last_tested_at"] == profile.last_tested_at.isoformat()
    assert safe["last_test_succeeded"] is True


@pytest.mark.parametrize("password", ["", " \t\n "])
def test_empty_app_password_is_rejected(app, password):
    with pytest.raises(ValueError, match="Google app password is required"):
        encrypt_app_password(password)


def test_app_password_requires_encryption_configuration(app):
    ciphertext = encrypt_app_password("abcd efgh ijkl mnop")
    app.config["SENDING_PROFILE_ENCRYPTION_KEY"] = ""

    with pytest.raises(RuntimeError, match="Sending-profile encryption is not configured"):
        encrypt_app_password("abcd efgh ijkl mnop")
    with pytest.raises(RuntimeError, match="Sending-profile encryption is not configured"):
        decrypt_app_password(ciphertext)


def test_database_allows_only_one_gmail_profile(app):
    for name in ("First Gmail", "Second Gmail"):
        db.session.add(
            SendingProfile(
                name=name,
                from_name="Simulation Admin",
                from_email="simulation@gmail.com",
            )
        )
        if name == "First Gmail":
            db.session.commit()

    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
    assert db.session.query(SendingProfile).count() == 1


def test_database_rejects_other_profile_providers(app):
    db.session.add(
        SendingProfile(
            name="Other provider",
            provider="other",
            from_name="Simulation Admin",
            from_email="simulation@example.com",
        )
    )
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_campaign_profile_and_event_channel_are_optional(app):
    admin = Admin(name="Admin", email="admin@example.com", password_hash="unused")
    template = EmailTemplate(template_name="Notice", subject="Notice", body="Notice")
    user = User(name="Employee", email="employee@example.com")
    campaign = Campaign(campaign_name="Simulation", admin=admin, template=template)
    recipient = CampaignRecipient(campaign=campaign, user=user, tracking_token="token")
    event = TrackingEvent(recipient=recipient, event_type="sent")
    db.session.add(event)
    db.session.commit()

    assert campaign.sending_profile_id is None
    assert campaign.sending_profile is None
    assert event.to_dict()["delivery_channel"] is None

    profile = SendingProfile(
        name="Personal Gmail",
        from_name="Simulation Admin",
        from_email="simulation@gmail.com",
    )
    campaign.sending_profile = profile
    event.delivery_channel = "gmail"
    db.session.commit()
    db.session.expire_all()

    assert campaign.sending_profile_id == profile.profile_id
    assert campaign.sending_profile.provider == "gmail"
    assert event.to_dict()["delivery_channel"] == "gmail"


def test_upgrade_db_preserves_legacy_rows_and_is_idempotent(app):
    db.drop_all()
    db.session.execute(text("CREATE TABLE users (user_id INTEGER PRIMARY KEY)"))
    db.session.execute(text("CREATE TABLE campaigns (campaign_id INTEGER PRIMARY KEY)"))
    db.session.execute(text("CREATE TABLE tracking_events (event_id INTEGER PRIMARY KEY)"))
    db.session.execute(text("INSERT INTO users (user_id) VALUES (1)"))
    db.session.execute(text("INSERT INTO campaigns (campaign_id) VALUES (1)"))
    db.session.execute(text("INSERT INTO tracking_events (event_id) VALUES (1)"))
    db.session.commit()

    runner = app.test_cli_runner()
    for _ in range(2):
        result = runner.invoke(args=["upgrade-db"])
        assert result.exit_code == 0, result.output

    schema = inspect(db.engine)
    assert "sending_profiles" in schema.get_table_names()
    assert "simulation_email_approved" in {
        column["name"] for column in schema.get_columns("users")
    }
    assert db.session.execute(
        text("SELECT simulation_email_approved FROM users WHERE user_id = 1")
    ).scalar_one() == 0
    assert db.session.execute(
        text("SELECT sending_profile_id FROM campaigns WHERE campaign_id = 1")
    ).scalar_one() is None
    assert db.session.execute(
        text("SELECT delivery_channel FROM tracking_events WHERE event_id = 1")
    ).scalar_one() is None
    assert schema.get_columns("campaigns")[-1]["nullable"] is True
    assert schema.get_columns("tracking_events")[-1]["nullable"] is True
