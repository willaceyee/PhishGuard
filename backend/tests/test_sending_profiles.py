import pytest
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
