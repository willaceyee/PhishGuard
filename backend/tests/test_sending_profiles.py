import smtplib
import ssl
from email.utils import getaddresses

import pytest
from unittest.mock import patch
from sqlalchemy import inspect, text
from sqlalchemy.exc import DataError, IntegrityError, OperationalError

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


@pytest.mark.parametrize("method", ["post", "patch"])
def test_profile_rejects_line_breaks_in_sender_display_name(
    client, auth_headers, profile_payload, stored_profile, method
):
    if method == "post":
        db.session.delete(stored_profile)
        db.session.commit()
        payload = {**profile_payload, "from_name": "Security\nInjected"}
    else:
        payload = {"from_name": "Security\r\nInjected"}
    response = getattr(client, method)(
        "/api/sending-profile", json=payload, headers=auth_headers
    )
    assert response.status_code == 400
    assert response.get_json() == {"error": "invalid_profile"}
    if method == "patch":
        db.session.expire_all()
        assert stored_profile.from_name == "Simulation Admin"


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


@pytest.fixture()
def tested_profile_campaign(auth_headers, stored_profile):
    stored_profile.enabled = True
    stored_profile.last_tested_at = utc_now()
    stored_profile.last_test_succeeded = True
    campaign = Campaign(
        campaign_name="Gmail simulation",
        admin=db.session.scalar(db.select(Admin)),
        template=EmailTemplate(template_name="Notice", subject="Notice", body="Notice"),
        sending_profile=stored_profile,
    )
    db.session.add(campaign)
    db.session.commit()
    return campaign


@pytest.mark.parametrize(
    "updates", [{"from_email": "new@gmail.com"}, {"app_password": "qrst uvwx yzab cdef"}],
)
def test_sender_or_password_change_invalidates_test_and_delivery_preview(
    client, auth_headers, stored_profile, tested_profile_campaign, updates,
):
    preview_path = f"/api/campaigns/{tested_profile_campaign.campaign_id}/delivery-preview"
    assert client.get(preview_path, headers=auth_headers).get_json()["preview"]["profile_ready"] is True

    response = client.patch("/api/sending-profile", json=updates, headers=auth_headers)

    assert response.status_code == 200
    assert response.get_json()["profile"]["last_test_succeeded"] is False
    assert response.get_json()["profile"]["last_tested_at"] is None
    db.session.expire_all()
    assert stored_profile.last_test_succeeded is False
    assert stored_profile.last_tested_at is None
    assert client.get(preview_path, headers=auth_headers).get_json()["preview"]["profile_ready"] is False


@pytest.mark.parametrize(
    "updates", [{"name": "Renamed", "from_name": "New display name"},
                {"from_email": " Owner@GMAIL.COM "}],
)
def test_cosmetic_edits_preserve_successful_test_and_delivery_readiness(
    client, auth_headers, stored_profile, tested_profile_campaign, updates,
):
    tested_at = stored_profile.last_tested_at.isoformat()
    response = client.patch("/api/sending-profile", json=updates, headers=auth_headers)
    assert response.status_code == 200
    assert response.get_json()["profile"]["last_test_succeeded"] is True
    assert response.get_json()["profile"]["last_tested_at"] == tested_at
    preview = client.get(
        f"/api/campaigns/{tested_profile_campaign.campaign_id}/delivery-preview",
        headers=auth_headers,
    ).get_json()["preview"]
    assert preview["profile_ready"] is True


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


@pytest.mark.parametrize("migrated", [False, True])
@pytest.mark.parametrize("foreign_keys", [False, True])
def test_referenced_profile_cannot_be_deleted_or_recreated_to_rebind_campaign(
    app, client, auth_headers, stored_profile, profile_payload, migrated, foreign_keys,
):
    if migrated:
        db.session.execute(text("DROP TABLE campaigns"))
        db.session.execute(text(
            "CREATE TABLE campaigns (campaign_id INTEGER PRIMARY KEY, "
            "campaign_name VARCHAR(160) NOT NULL, template_id INTEGER NOT NULL, "
            "created_by INTEGER NOT NULL, scheduled_date DATETIME, "
            "status VARCHAR(40) NOT NULL, created_at DATETIME NOT NULL)"
        ))
        db.session.commit()
        result = app.test_cli_runner().invoke(args=["upgrade-db"])
        assert result.exit_code == 0, result.output
        assert inspect(db.engine).get_foreign_keys("campaigns") == []
    db.session.execute(text(f"PRAGMA foreign_keys = {int(foreign_keys)}"))
    assert db.session.execute(text("PRAGMA foreign_keys")).scalar_one() == int(foreign_keys)
    campaign = Campaign(
        campaign_name="Historical Gmail simulation", status="completed",
        admin=db.session.scalar(db.select(Admin)),
        template=EmailTemplate(template_name="Notice", subject="Notice", body="Notice"),
        sending_profile=stored_profile,
    )
    db.session.add(campaign)
    db.session.commit()
    campaign_id, profile_id = campaign.campaign_id, stored_profile.profile_id

    response = client.delete("/api/sending-profile", headers=auth_headers)

    assert response.status_code == 409
    assert response.get_json() == {"error": "sending_profile_in_use"}
    response = client.post(
        "/api/sending-profile", json={**profile_payload, "from_email": "replacement@gmail.com"},
        headers=auth_headers,
    )
    assert response.status_code == 409
    db.session.expire_all()
    campaign = db.session.get(Campaign, campaign_id)
    assert campaign.sending_profile_id == profile_id
    assert campaign.sending_profile.from_email == "owner@gmail.com"
    assert db.session.query(SendingProfile).count() == 1


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


@pytest.fixture()
def test_template(app):
    template = EmailTemplate(
        template_name="Connection test",
        subject="Connection test",
        body="Connection test body",
    )
    db.session.add(template)
    db.session.commit()
    return template


def test_gmail_connection_uses_tls_and_sends_only_to_approved_sender(
    client, auth_headers, stored_profile, approved_sender, caplog
):
    template = EmailTemplate(
        template_name="Document review",
        subject="Review the updated document",
        body="Open [INSERT CAMPAIGN TRACKING LINK] to continue.",
    )
    recipient = User(
        name="Test Recipient",
        email="recipient@example.com",
        simulation_email_approved=True,
    )
    db.session.add_all([recipient, template])
    db.session.commit()
    with patch("smtplib.SMTP") as smtp_class, patch(
        "ssl.create_default_context", wraps=ssl.create_default_context
    ) as context_factory:
        smtp = smtp_class.return_value.__enter__.return_value
        response = client.post(
            "/api/sending-profile/test",
            json={
                "recipient_user_id": recipient.user_id,
                "template_id": template.template_id,
            },
            headers=auth_headers,
        )
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
    assert getaddresses(message.get_all("To")) == [("", "recipient@example.com")]
    assert getaddresses(message.get_all("From")) == [("Simulation Admin", "owner@gmail.com")]
    assert message.get_all("Cc") is None
    assert message.get_all("Bcc") is None
    assert "security simulation" in message["Subject"].lower()
    assert message["Subject"].startswith("[SECURITY SIMULATION]")
    assert message["X-PhishGuard-Simulation"] == "authorized-training"
    assert message["Subject"] == "[SECURITY SIMULATION] Review the updated document"
    assert "Open http://localhost/phishguard-test-preview to continue." in message.get_content()
    assert "[INSERT CAMPAIGN TRACKING LINK]" not in message.get_content()
    assert db.session.query(TrackingEvent).count() == 0
    assert "abcdefghijklmnop" not in message.as_string()
    db.session.expire_all()
    assert stored_profile.last_tested_at is not None
    assert stored_profile.last_test_succeeded is True
    assert response.get_json()["profile"]["last_test_succeeded"] is True
    assert_safe_response(response, stored_profile)
    assert "abcdefghijklmnop" not in caplog.text
    assert stored_profile.encrypted_app_password not in caplog.text


@pytest.mark.parametrize("template_id", [None, "1", 9999])
def test_connection_requires_an_existing_template_before_decryption(
    client, auth_headers, stored_profile, approved_sender, template_id
):
    payload = {
        "recipient_user_id": approved_sender.user_id,
        "template_id": template_id,
    }
    with patch("app.sending_profiles.decrypt_app_password") as decrypt, patch(
        "smtplib.SMTP"
    ) as smtp_class:
        response = client.post(
            "/api/sending-profile/test", json=payload, headers=auth_headers
        )
    assert response.status_code == 400
    assert response.get_json() == {"error": "gmail_test_template_not_found"}
    decrypt.assert_not_called()
    smtp_class.assert_not_called()


def test_connection_rejects_an_unsafe_template_subject_before_decryption(
    client, auth_headers, stored_profile, approved_sender
):
    template = EmailTemplate(
        template_name="Unsafe subject",
        subject="First line\nInjected header",
        body="Test body",
    )
    db.session.add(template)
    db.session.commit()
    with patch("app.sending_profiles.decrypt_app_password") as decrypt, patch(
        "smtplib.SMTP"
    ) as smtp_class:
        response = client.post(
            "/api/sending-profile/test",
            json={
                "recipient_user_id": approved_sender.user_id,
                "template_id": template.template_id,
            },
            headers=auth_headers,
        )
    assert response.status_code == 400
    assert response.get_json() == {"error": "gmail_test_template_invalid"}
    decrypt.assert_not_called()
    smtp_class.assert_not_called()


@pytest.mark.parametrize("payload", [None, {}, {"recipient_user_id": "1"}, {"recipient_user_id": 9999}])
def test_connection_requires_an_existing_approved_test_recipient_before_decryption(
    client, auth_headers, stored_profile, approved_sender, payload
):
    with patch("app.sending_profiles.decrypt_app_password") as decrypt, patch(
        "smtplib.SMTP"
    ) as smtp_class:
        response = client.post(
            "/api/sending-profile/test", json=payload, headers=auth_headers
        )
    assert response.status_code == 403
    assert response.get_json() == {"error": "gmail_test_recipient_not_approved"}
    decrypt.assert_not_called()
    smtp_class.assert_not_called()


def test_connection_rejects_a_test_recipient_whose_approval_was_revoked(
    client, auth_headers, stored_profile, approved_sender
):
    recipient = User(
        name="Revoked Recipient",
        email="recipient@example.com",
        simulation_email_approved=False,
    )
    db.session.add(recipient)
    db.session.commit()
    with patch("app.sending_profiles.decrypt_app_password") as decrypt, patch(
        "smtplib.SMTP"
    ) as smtp_class:
        response = client.post(
            "/api/sending-profile/test",
            json={"recipient_user_id": recipient.user_id},
            headers=auth_headers,
        )
    assert response.status_code == 403
    assert response.get_json() == {"error": "gmail_test_recipient_not_approved"}
    decrypt.assert_not_called()
    smtp_class.assert_not_called()


@pytest.mark.parametrize(
    "email,approved", [(None, False), ("owner@gmail.com", False),
                       ("different@gmail.com", True), ("Owner@gmail.com", True)],
)
def test_connection_requires_exact_approved_user_before_decryption(
    client, auth_headers, stored_profile, email, approved
):
    recipient = User(
        name="Test Recipient",
        email="recipient@example.com",
        simulation_email_approved=True,
    )
    db.session.add(recipient)
    if email:
        db.session.add(User(name="Owner", email=email, simulation_email_approved=approved))
    db.session.commit()
    stored_profile.last_test_succeeded = True
    db.session.commit()
    with patch("app.sending_profiles.decrypt_app_password") as decrypt, patch("smtplib.SMTP") as smtp_class:
        response = client.post(
            "/api/sending-profile/test",
            json={"recipient_user_id": recipient.user_id},
            headers=auth_headers,
        )
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
    client, auth_headers, stored_profile, approved_sender, test_template,
    error, code, stage, caplog
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
        response = client.post(
            "/api/sending-profile/test",
            json={
                "recipient_user_id": approved_sender.user_id,
                "template_id": test_template.template_id,
            },
            headers=auth_headers,
        )
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
    app, client, auth_headers, stored_profile, approved_sender, test_template,
    failure, caplog
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
        response = client.post(
            "/api/sending-profile/test",
            json={
                "recipient_user_id": approved_sender.user_id,
                "template_id": test_template.template_id,
            },
            headers=auth_headers,
        )
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


@pytest.mark.parametrize("field,limit", [("name", 160), ("from_name", 120)])
@pytest.mark.parametrize("method", ["post", "patch"])
def test_metadata_length_limits_reject_before_credentials_change(
    client, auth_headers, profile_payload, stored_profile, field, limit, method, caplog
):
    ciphertext = stored_profile.encrypted_app_password
    if method == "post":
        db.session.delete(stored_profile)
        db.session.commit()
    data = {**profile_payload, field: "x" * (limit + 1)}
    response = getattr(client, method)("/api/sending-profile", json=data, headers=auth_headers)
    assert response.status_code == 400
    assert response.get_json() == {"error": "invalid_profile"}
    assert "abcdefghijklmnop" not in response.get_data(as_text=True)
    assert ciphertext not in response.get_data(as_text=True)
    assert "abcdefghijklmnop" not in caplog.text
    assert ciphertext not in caplog.text
    if method == "post":
        assert db.session.query(SendingProfile).count() == 0
    else:
        db.session.expire_all()
        assert stored_profile.name == "Personal Gmail"
        assert stored_profile.from_name == "Simulation Admin"
        assert stored_profile.encrypted_app_password == ciphertext


@pytest.mark.parametrize("field,limit", [("name", 160), ("from_name", 120)])
@pytest.mark.parametrize("method", ["post", "patch"])
def test_metadata_limits_apply_after_trimming(
    client, auth_headers, profile_payload, stored_profile, field, limit, method
):
    if method == "post":
        db.session.delete(stored_profile)
        db.session.commit()
    data = {**profile_payload, field: " " + "x" * limit + " "}
    response = getattr(client, method)("/api/sending-profile", json=data, headers=auth_headers)
    assert response.status_code == (201 if method == "post" else 200)
    assert response.get_json()["profile"][field] == "x" * limit


@pytest.mark.parametrize("error_class", [DataError, OperationalError])
@pytest.mark.parametrize(
    "method,path",
    [("post", "/api/sending-profile"), ("patch", "/api/sending-profile"),
     ("delete", "/api/sending-profile"), ("post", "/api/sending-profile/test")],
)
def test_persistence_errors_do_not_expose_credential_bind_parameters(
    app, client, auth_headers, profile_payload, stored_profile, approved_sender, test_template,
    error_class, method, path, caplog,
):
    app.config["PROPAGATE_EXCEPTIONS"] = False
    previous_ciphertext = stored_profile.encrypted_app_password
    if method == "post" and path == "/api/sending-profile":
        db.session.delete(stored_profile)
        db.session.commit()
    bound_ciphertexts = []

    def fail_commit():
        changed = list(db.session.new) + list(db.session.dirty) + list(db.session.deleted)
        profile = next(item for item in changed if isinstance(item, SendingProfile))
        bound_ciphertexts.append(profile.encrypted_app_password)
        raise error_class(
            "credential persistence statement",
            {"encrypted_app_password": profile.encrypted_app_password},
            Exception("plaintext-marker-abcdefghijklmnop"),
        )

    request_payload = (
        {
            "recipient_user_id": approved_sender.user_id,
            "template_id": test_template.template_id,
        }
        if path == "/api/sending-profile/test"
        else profile_payload
    )
    with patch.object(db.session, "commit", side_effect=fail_commit), patch("smtplib.SMTP"):
        response = getattr(client, method)(path, json=request_payload, headers=auth_headers)
    for marker in bound_ciphertexts + [previous_ciphertext, "plaintext-marker-abcdefghijklmnop"]:
        assert marker not in response.get_data(as_text=True)
        assert marker not in caplog.text
    assert response.status_code == 503
    assert response.get_json() == {"error": "sending_profile_persistence_failed"}
    if method == "post" and path == "/api/sending-profile":
        assert db.session.query(SendingProfile).count() == 0
    else:
        db.session.expire_all()
        assert stored_profile.name == "Personal Gmail"
        assert stored_profile.encrypted_app_password == previous_ciphertext
        assert stored_profile.last_tested_at is None
        assert stored_profile.last_test_succeeded is False


def test_unapproved_test_persistence_failure_is_safe(
    app, client, auth_headers, stored_profile, caplog
):
    app.config["PROPAGATE_EXCEPTIONS"] = False
    ciphertext = stored_profile.encrypted_app_password
    failure = DataError("statement", {"encrypted_app_password": ciphertext}, Exception("plaintext-marker"))
    with patch.object(db.session, "commit", side_effect=failure), patch("smtplib.SMTP") as smtp:
        response = client.post(
            "/api/sending-profile/test",
            headers=auth_headers,
        )
    assert ciphertext not in response.get_data(as_text=True)
    assert ciphertext not in caplog.text
    assert "plaintext-marker" not in response.get_data(as_text=True)
    assert "plaintext-marker" not in caplog.text
    assert response.status_code == 503
    assert response.get_json() == {"error": "sending_profile_persistence_failed"}
    smtp.assert_not_called()
    db.session.expire_all()
    assert stored_profile.last_tested_at is None


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
