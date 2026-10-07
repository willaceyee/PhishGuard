import smtplib
import ssl
from contextlib import contextmanager
from datetime import timedelta
from threading import Event, Lock, Thread, current_thread
from unittest.mock import patch

import pytest

from app import create_app, email_delivery
from app.extensions import db
from app.models import (
    Admin, Campaign, CampaignRecipient, EmailTemplate, SendingProfile, TrackingEvent,
    User, utc_now,
)
from app.sending_profiles import decrypt_app_password, encrypt_app_password
from config import TestConfig as BackendTestConfig


def create_campaign_with_user(client, auth_headers):
    user = client.post(
        "/api/users",
        headers=auth_headers,
        json={"name": "Jordan Lee", "email": "jordan@example.com"},
    ).get_json()["user"]
    user = client.patch(
        f"/api/users/{user['user_id']}",
        headers=auth_headers,
        json={"simulation_email_approved": True},
    ).get_json()["user"]
    template = client.post(
        "/api/templates",
        headers=auth_headers,
        json={
            "template_name": "Account warning",
            "subject": "Review your account",
            "body": "Account review required.",
        },
    ).get_json()["template"]
    campaign = client.post(
        "/api/campaigns",
        headers=auth_headers,
        json={"campaign_name": "Controlled test", "template_id": template["template_id"]},
    ).get_json()["campaign"]
    return user, campaign


@pytest.fixture()
def gmail_campaign(client, auth_headers, app):
    user, created = create_campaign_with_user(client, auth_headers)
    profile = SendingProfile(
        name="Training Gmail",
        from_name="Simulation Admin",
        from_email="simulation@gmail.com",
        encrypted_app_password=encrypt_app_password("abcd efgh ijkl mnop"),
        enabled=True,
        last_tested_at=utc_now(),
        last_test_succeeded=True,
    )
    campaign = db.session.get(Campaign, created["campaign_id"])
    campaign.sending_profile = profile
    db.session.add(
        CampaignRecipient(
            campaign=campaign,
            user=db.session.get(User, user["user_id"]),
            tracking_token="gmail-tracking-jordan",
        )
    )
    db.session.commit()
    app.config["PUBLIC_BASE_URL"] = "https://training.example.com"
    return campaign


def add_gmail_recipient(campaign, index, approved=True):
    recipient = CampaignRecipient(
        campaign=campaign,
        user=User(
            name=f"Recipient {index}",
            email=f"recipient{index}@example.com",
            simulation_email_approved=approved,
        ),
        tracking_token=f"gmail-tracking-{index}",
    )
    db.session.add(recipient)
    db.session.commit()
    return recipient


def test_tracking_flow_records_events_without_credentials(client, auth_headers, app):
    user, campaign = create_campaign_with_user(client, auth_headers)
    response = client.post(
        f"/api/campaigns/{campaign['campaign_id']}/recipients",
        headers=auth_headers,
        json={"user_ids": [user["user_id"]]},
    )
    assert response.status_code == 201
    tracking_url = response.get_json()["recipients"][0]["tracking_url"]
    tracking_path = tracking_url.removeprefix("http://localhost")

    click = client.get(tracking_path)
    assert click.status_code == 302
    assert "/simulation/" in click.headers["Location"]
    assert click.headers["Cache-Control"] == "no-store"

    landing = client.get(click.headers["Location"])
    assert landing.status_code == 200
    assert b"Verify your account" in landing.data
    assert b'type="password"' not in landing.data
    assert b'type="email"' not in landing.data

    submitted = client.post(
        f"{click.headers['Location']}/submit",
        data={"email": "must-not-be-stored@example.com", "password": "must-not-be-stored"},
    )
    assert submitted.status_code == 302
    assert "/training/" in submitted.headers["Location"]
    training = client.get(submitted.headers["Location"])
    assert training.status_code == 200
    assert b"This was a simulation" in training.data

    events_response = client.get(
        f"/api/campaigns/{campaign['campaign_id']}/events", headers=auth_headers
    )
    event_types = [event["event_type"] for event in events_response.get_json()["events"]]
    assert set(event_types) == {
        "link_clicked",
        "landing_viewed",
        "form_submitted",
        "training_viewed",
    }

    with app.app_context():
        serialized_events = " ".join(
            str(event.to_dict()) for event in db.session.scalars(db.select(TrackingEvent)).all()
        )
        assert "must-not-be-stored" not in serialized_events


def test_recipient_assignment_validates_and_skips_duplicates(client, auth_headers):
    user, campaign = create_campaign_with_user(client, auth_headers)
    endpoint = f"/api/campaigns/{campaign['campaign_id']}/recipients"
    assert client.post(endpoint, headers=auth_headers, json={"user_ids": [999]}).status_code == 404

    first = client.post(
        endpoint, headers=auth_headers, json={"user_ids": [user["user_id"], user["user_id"]]}
    )
    assert first.status_code == 201
    assert len(first.get_json()["recipients"]) == 1

    duplicate = client.post(
        endpoint, headers=auth_headers, json={"user_ids": [user["user_id"]]}
    )
    assert duplicate.status_code == 201
    assert duplicate.get_json()["recipients"] == []
    assert duplicate.get_json()["skipped_existing"] == 1


def test_invalid_tracking_token_is_safe(client):
    response = client.get("/track/not-a-valid-token")
    assert response.status_code == 404
    assert b"invalid or expired" in response.data
    assert response.headers["Cache-Control"] == "no-store"


def test_allowlisted_mailpit_delivery_requires_confirmation(client, auth_headers, app):
    user, campaign = create_campaign_with_user(client, auth_headers)
    campaign_id = campaign["campaign_id"]
    client.post(
        f"/api/campaigns/{campaign_id}/recipients",
        headers=auth_headers,
        json={"user_ids": [user["user_id"]]},
    )

    preview_response = client.get(
        f"/api/campaigns/{campaign_id}/delivery-preview", headers=auth_headers
    )
    assert preview_response.status_code == 200
    preview = preview_response.get_json()["preview"]
    assert preview["allowed_recipients"][0]["email"] == "jordan@example.com"
    assert preview["blocked_recipients"] == []
    assert preview["confirmation_phrase"] == "SEND 1 AUTHORIZED EMAIL"
    assert preview["delivery_method"] == "mailpit"
    assert preview["real_delivery"] is False
    assert preview["profile"] is None
    assert preview["profile_ready"] is True
    assert preview["from"] == app.config["MAIL_FROM"]

    wrong_confirmation = client.post(
        f"/api/campaigns/{campaign_id}/send",
        headers=auth_headers,
        json={"confirmation": "send"},
    )
    assert wrong_confirmation.status_code == 400

    with patch("app.email_delivery.smtplib.SMTP") as smtp_class:
        smtp = smtp_class.return_value.__enter__.return_value
        delivered = client.post(
            f"/api/campaigns/{campaign_id}/send",
            headers=auth_headers,
            json={"confirmation": preview["confirmation_phrase"]},
        )
        assert delivered.status_code == 200
        assert delivered.get_json()["delivered"] == 1
        message = smtp.send_message.call_args.args[0]
        assert message["From"] == app.config["MAIL_FROM"]
        assert message["Subject"].startswith("[SECURITY SIMULATION]")
        assert message["X-PhishGuard-Simulation"] == "authorized-training"
        assert "/track/" in message.get_content()
        assert "Do not enter or send a real password" in message.get_content()
        smtp.starttls.assert_not_called()
        smtp.login.assert_not_called()

    refreshed = client.get(
        f"/api/campaigns/{campaign_id}/delivery-preview", headers=auth_headers
    ).get_json()["preview"]
    assert refreshed["already_delivered"] == 1
    assert refreshed["allowed_recipients"] == []

    event_types = [
        event["event_type"]
        for event in client.get(
            f"/api/campaigns/{campaign_id}/events", headers=auth_headers
        ).get_json()["events"]
    ]
    assert "email_delivered" in event_types
    events = client.get(
        f"/api/campaigns/{campaign_id}/events", headers=auth_headers
    ).get_json()["events"]
    assert events[0]["delivery_channel"] == "mailpit"


def test_delivery_blocks_non_allowlisted_recipient(client, auth_headers):
    user, campaign = create_campaign_with_user(client, auth_headers)
    second_user = client.post(
        "/api/users",
        headers=auth_headers,
        json={"name": "Blocked User", "email": "blocked@example.com"},
    ).get_json()["user"]
    campaign_id = campaign["campaign_id"]
    client.post(
        f"/api/campaigns/{campaign_id}/recipients",
        headers=auth_headers,
        json={"user_ids": [user["user_id"], second_user["user_id"]]},
    )
    preview = client.get(
        f"/api/campaigns/{campaign_id}/delivery-preview", headers=auth_headers
    ).get_json()["preview"]
    assert [user["email"] for user in preview["blocked_recipients"]] == [
        "blocked@example.com"
    ]
    blocked = client.post(
        f"/api/campaigns/{campaign_id}/send",
        headers=auth_headers,
        json={"confirmation": preview["confirmation_phrase"]},
    )
    assert blocked.status_code == 403

    approved = client.patch(
        f"/api/users/{second_user['user_id']}",
        headers=auth_headers,
        json={"simulation_email_approved": True},
    )
    assert approved.status_code == 200
    refreshed = client.get(
        f"/api/campaigns/{campaign_id}/delivery-preview", headers=auth_headers
    ).get_json()["preview"]
    assert refreshed["blocked_recipients"] == []
    assert {user["email"] for user in refreshed["allowed_recipients"]} == {
        "jordan@example.com",
        "blocked@example.com",
    }


def test_delivery_rejects_unsafe_public_url_and_recipient_overflow(
    client, auth_headers, app
):
    user, campaign = create_campaign_with_user(client, auth_headers)
    campaign_id = campaign["campaign_id"]
    client.post(
        f"/api/campaigns/{campaign_id}/recipients",
        headers=auth_headers,
        json={"user_ids": [user["user_id"]]},
    )
    app.config["PUBLIC_BASE_URL"] = "http://public.example.com"
    preview = client.get(
        f"/api/campaigns/{campaign_id}/delivery-preview", headers=auth_headers
    ).get_json()["preview"]
    assert preview["public_url_safe"] is False
    unsafe = client.post(
        f"/api/campaigns/{campaign_id}/send",
        headers=auth_headers,
        json={"confirmation": preview["confirmation_phrase"]},
    )
    assert unsafe.status_code == 400

    app.config["MAX_CAMPAIGN_RECIPIENTS"] = 1
    extra_user = client.post(
        "/api/users",
        headers=auth_headers,
        json={"name": "Extra User", "email": "extra@example.com"},
    ).get_json()["user"]
    overflow = client.post(
        f"/api/campaigns/{campaign_id}/recipients",
        headers=auth_headers,
        json={"user_ids": [extra_user["user_id"]]},
    )
    assert overflow.status_code == 400


def test_delivery_disabled_rate_limit_and_smtp_failure(client, auth_headers, app):
    user, campaign = create_campaign_with_user(client, auth_headers)
    campaign_id = campaign["campaign_id"]
    client.post(
        f"/api/campaigns/{campaign_id}/recipients",
        headers=auth_headers,
        json={"user_ids": [user["user_id"]]},
    )
    endpoint = f"/api/campaigns/{campaign_id}/send"

    app.config["MAIL_DELIVERY_ENABLED"] = False
    preview = client.get(
        f"/api/campaigns/{campaign_id}/delivery-preview", headers=auth_headers
    ).get_json()["preview"]
    disabled = client.post(
        endpoint,
        headers=auth_headers,
        json={"confirmation": preview["confirmation_phrase"]},
    )
    assert disabled.status_code == 400

    app.config["MAIL_DELIVERY_ENABLED"] = True
    app.config["MAX_EMAILS_PER_HOUR"] = 0
    limited = client.post(
        endpoint,
        headers=auth_headers,
        json={"confirmation": preview["confirmation_phrase"]},
    )
    assert limited.status_code == 400

    app.config["MAX_EMAILS_PER_HOUR"] = 10
    with patch("app.email_delivery.smtplib.SMTP", side_effect=OSError):
        failed = client.post(
            endpoint,
            headers=auth_headers,
            json={"confirmation": preview["confirmation_phrase"]},
        )
    assert failed.status_code == 502
    events = client.get(
        f"/api/campaigns/{campaign_id}/events", headers=auth_headers
    ).get_json()["events"]
    assert [event["event_type"] for event in events] == ["email_failed"]
    assert events[0]["delivery_channel"] == "mailpit"


@pytest.mark.parametrize("recipient_count", [1, 2])
def test_gmail_preview_identifies_real_delivery_without_exposing_credentials(
    client, auth_headers, gmail_campaign, recipient_count
):
    if recipient_count == 2:
        add_gmail_recipient(gmail_campaign, 2)
    with patch("smtplib.SMTP") as smtp_class, patch(
        "app.email_delivery.decrypt_app_password"
    ) as decrypt:
        response = client.get(
            f"/api/campaigns/{gmail_campaign.campaign_id}/delivery-preview",
            headers=auth_headers,
        )
    assert response.status_code == 200
    preview = response.get_json()["preview"]
    assert preview["delivery_method"] == "gmail"
    assert preview["real_delivery"] is True
    assert preview["delivery_enabled"] is True
    assert preview["profile_ready"] is True
    assert preview["public_url_safe"] is True
    assert preview["campaign_recipient_limit"] == 10
    assert preview["hourly_delivery_limit"] == 20
    assert preview["confirmation_phrase"] == (
        "SEND 1 REAL EMAIL" if recipient_count == 1 else "SEND 2 REAL EMAILS"
    )
    assert preview["from"] == "Simulation Admin <simulation@gmail.com>"
    assert preview["subject"] == "[SECURITY SIMULATION] Review your account"
    assert len(preview["allowed_recipients"]) == recipient_count
    assert preview["blocked_recipients"] == []
    assert preview["already_delivered"] == 0
    assert preview["profile"]["from_email"] == "simulation@gmail.com"
    assert preview["profile"]["credential_configured"] is True
    assert "app_password" not in preview["profile"]
    assert "encrypted_app_password" not in preview["profile"]
    assert "abcdefghijklmnop" not in response.get_data(as_text=True)
    assert gmail_campaign.sending_profile.encrypted_app_password not in response.get_data(
        as_text=True
    )
    smtp_class.assert_not_called()
    decrypt.assert_not_called()


@pytest.mark.parametrize("enabled,test_succeeded", [(False, True), (True, False)])
def test_gmail_preview_reports_profile_readiness(
    client, auth_headers, gmail_campaign, enabled, test_succeeded
):
    gmail_campaign.sending_profile.enabled = enabled
    gmail_campaign.sending_profile.last_test_succeeded = test_succeeded
    db.session.commit()
    preview = client.get(
        f"/api/campaigns/{gmail_campaign.campaign_id}/delivery-preview",
        headers=auth_headers,
    ).get_json()["preview"]
    assert preview["profile_ready"] is False


@pytest.mark.parametrize(
    "url,safe",
    [
        ("http://training.example.com", False),
        ("https://localhost", False),
        ("https://LOCALHOST.", False),
        ("https://training.local", False),
        ("https://training.LOCAL.", False),
        ("https://127.0.0.1", False),
        ("https://10.0.0.1", False),
        ("https://172.16.0.1", False),
        ("https://192.168.1.1", False),
        ("https://169.254.10.1", False),
        ("https://192.0.2.1", False),
        ("https://240.0.0.1", False),
        ("https://0.0.0.0", False),
        ("https://[::1]", False),
        ("https://[fc00::1]", False),
        ("https://[fe80::1]", False),
        ("https://[2001:db8::1]", False),
        ("https://[::]", False),
        ("https://[::ffff:127.0.0.1]", False),
        ("https://[invalid]", False),
        ("https://", False),
        ("https://training.example.com", True),
        ("https://does-not-resolve.example", True),
        ("https://8.8.8.8", True),
        ("https://[2606:4700:4700::1111]", True),
    ],
)
def test_gmail_public_url_validation_is_structural(app, url, safe):
    app.config["PUBLIC_BASE_URL"] = url
    with patch("socket.getaddrinfo", side_effect=AssertionError("No DNS probing")):
        assert email_delivery.public_gmail_url_is_safe() is safe


def test_gmail_sends_separate_labeled_messages_after_starttls_and_login(
    client, auth_headers, gmail_campaign
):
    second = add_gmail_recipient(gmail_campaign, 2)
    gmail_campaign.template.body = "Review [INSERT CAMPAIGN TRACKING LINK]."
    db.session.commit()
    steps = []

    def decrypt_for_login(ciphertext):
        steps.append("decrypt")
        return decrypt_app_password(ciphertext)

    with patch("smtplib.SMTP") as smtp_class, patch(
        "app.email_delivery.decrypt_app_password", side_effect=decrypt_for_login
    ) as decrypt:
        smtp = smtp_class.return_value.__enter__.return_value
        smtp.starttls.side_effect = lambda **kwargs: steps.append("starttls")
        smtp.login.side_effect = lambda *args: steps.append("login")
        smtp.send_message.side_effect = lambda message, **kwargs: steps.append("send")
        response = client.post(
            f"/api/campaigns/{gmail_campaign.campaign_id}/send",
            headers=auth_headers,
            json={"confirmation": "SEND 2 REAL EMAILS"},
        )

    assert response.status_code == 200
    assert response.get_json()["delivered"] == 2
    smtp_class.assert_called_once_with("smtp.gmail.com", 587, timeout=10)
    smtp.starttls.assert_called_once()
    context = smtp.starttls.call_args.kwargs["context"]
    assert isinstance(context, ssl.SSLContext)
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
    smtp.login.assert_called_once_with("simulation@gmail.com", "abcdefghijklmnop")
    decrypt.assert_called_once_with(gmail_campaign.sending_profile.encrypted_app_password)
    assert steps == ["starttls", "decrypt", "login", "send", "send"]
    messages = [call.args[0] for call in smtp.send_message.call_args_list]
    assert [message["To"] for message in messages] == [
        "jordan@example.com", "recipient2@example.com"
    ]
    links = [
        "https://training.example.com/track/gmail-tracking-jordan",
        "https://training.example.com/track/gmail-tracking-2",
    ]
    for index, message in enumerate(messages):
        assert message["From"] == "Simulation Admin <simulation@gmail.com>"
        assert message["Subject"] == "[SECURITY SIMULATION] Review your account"
        assert message["X-PhishGuard-Simulation"] == "authorized-training"
        assert message["Cc"] is None
        assert message["Bcc"] is None
        assert "AUTHORIZED SECURITY-AWARENESS SIMULATION" in message.get_content()
        assert "Do not enter or send a real password" in message.get_content()
        assert links[index] in message.get_content()
        assert links[1 - index] not in message.get_content()
        assert "[INSERT CAMPAIGN TRACKING LINK]" not in message.get_content()
    events = db.session.scalars(db.select(TrackingEvent)).all()
    assert {event.recipient_id for event in events} == {
        gmail_campaign.recipients[0].recipient_id, second.recipient_id
    }
    assert [(event.event_type, event.delivery_channel) for event in events] == [
        ("email_delivered", "gmail"), ("email_delivered", "gmail")
    ]
    assert gmail_campaign.status == "active"


@pytest.mark.parametrize("enabled,test_succeeded", [(False, True), (True, False)])
def test_gmail_send_requires_enabled_and_successfully_tested_profile(
    client, auth_headers, gmail_campaign, enabled, test_succeeded
):
    gmail_campaign.sending_profile.enabled = enabled
    gmail_campaign.sending_profile.last_test_succeeded = test_succeeded
    db.session.commit()
    with patch("smtplib.SMTP") as smtp_class:
        response = client.post(
            f"/api/campaigns/{gmail_campaign.campaign_id}/send",
            headers=auth_headers,
            json={"confirmation": "SEND 1 REAL EMAIL"},
        )
    assert response.status_code == 400
    smtp_class.assert_not_called()
    assert db.session.query(TrackingEvent).count() == 0


def test_gmail_send_requires_global_delivery_enabled(
    client, auth_headers, gmail_campaign, app
):
    app.config["MAIL_DELIVERY_ENABLED"] = False
    with patch("smtplib.SMTP") as smtp_class:
        response = client.post(
            f"/api/campaigns/{gmail_campaign.campaign_id}/send",
            headers=auth_headers,
            json={"confirmation": "SEND 1 REAL EMAIL"},
        )
    assert response.status_code == 400
    smtp_class.assert_not_called()
    assert db.session.query(TrackingEvent).count() == 0


@pytest.mark.parametrize(
    "confirmation", ["SEND 1 AUTHORIZED EMAIL", "SEND 2 REAL EMAILS", "send"]
)
def test_gmail_send_requires_exact_real_email_confirmation(
    client, auth_headers, gmail_campaign, confirmation
):
    with patch("smtplib.SMTP") as smtp_class:
        response = client.post(
            f"/api/campaigns/{gmail_campaign.campaign_id}/send",
            headers=auth_headers,
            json={"confirmation": confirmation},
        )
    assert response.status_code == 400
    smtp_class.assert_not_called()
    assert db.session.query(TrackingEvent).count() == 0


def test_gmail_send_blocks_every_message_if_any_pending_recipient_is_unapproved(
    client, auth_headers, gmail_campaign
):
    add_gmail_recipient(gmail_campaign, 2, approved=False)
    preview = client.get(
        f"/api/campaigns/{gmail_campaign.campaign_id}/delivery-preview",
        headers=auth_headers,
    ).get_json()["preview"]
    assert [user["email"] for user in preview["blocked_recipients"]] == [
        "recipient2@example.com"
    ]
    with patch("smtplib.SMTP") as smtp_class:
        response = client.post(
            f"/api/campaigns/{gmail_campaign.campaign_id}/send",
            headers=auth_headers,
            json={"confirmation": "SEND 1 REAL EMAIL"},
        )
    assert response.status_code == 403
    smtp_class.assert_not_called()
    assert db.session.query(TrackingEvent).count() == 0


@pytest.mark.parametrize(
    "url", ["http://training.example.com", "https://localhost", "https://training.local",
            "https://10.0.0.1", "https://[::1]", "https://[invalid]"]
)
def test_gmail_send_rejects_unsafe_public_url_before_connecting(
    client, auth_headers, gmail_campaign, app, url
):
    app.config["PUBLIC_BASE_URL"] = url
    with patch("smtplib.SMTP") as smtp_class:
        response = client.post(
            f"/api/campaigns/{gmail_campaign.campaign_id}/send",
            headers=auth_headers,
            json={"confirmation": "SEND 1 REAL EMAIL"},
        )
    assert response.status_code == 400
    smtp_class.assert_not_called()
    assert db.session.query(TrackingEvent).count() == 0


def test_gmail_send_rejects_eleven_pending_recipients(
    client, auth_headers, gmail_campaign, app
):
    app.config["MAX_CAMPAIGN_RECIPIENTS"] = 100
    app.config["MAX_EMAILS_PER_HOUR"] = 100
    for index in range(2, 12):
        add_gmail_recipient(gmail_campaign, index)
    with patch("smtplib.SMTP") as smtp_class:
        response = client.post(
            f"/api/campaigns/{gmail_campaign.campaign_id}/send",
            headers=auth_headers,
            json={"confirmation": "SEND 11 REAL EMAILS"},
        )
    assert response.status_code == 400
    smtp_class.assert_not_called()
    assert db.session.query(TrackingEvent).count() == 0


def test_gmail_recipient_limit_applies_to_ten_pending_recipients(
    client, auth_headers, gmail_campaign, app
):
    app.config["MAX_EMAILS_PER_HOUR"] = 100
    for index in range(2, 12):
        add_gmail_recipient(gmail_campaign, index)
    db.session.add(
        TrackingEvent(
            recipient=gmail_campaign.recipients[0], event_type="email_delivered"
        )
    )
    db.session.commit()
    with patch("smtplib.SMTP") as smtp_class:
        response = client.post(
            f"/api/campaigns/{gmail_campaign.campaign_id}/send",
            headers=auth_headers,
            json={"confirmation": "SEND 10 REAL EMAILS"},
        )
    assert response.status_code == 200
    assert response.get_json()["delivered"] == 10
    messages = smtp_class.return_value.__enter__.return_value.send_message.call_args_list
    assert len(messages) == 10
    assert all(call.args[0]["To"] != "jordan@example.com" for call in messages)


@pytest.mark.parametrize(
    "prior_count,pending_count,status", [(19, 1, 200), (20, 1, 400), (19, 2, 400)]
)
def test_gmail_hourly_limit_includes_the_requested_send(
    client, auth_headers, gmail_campaign, app, prior_count, pending_count, status
):
    app.config["MAX_EMAILS_PER_HOUR"] = 100
    if pending_count == 2:
        add_gmail_recipient(gmail_campaign, 2)
    prior_campaign = Campaign(
        campaign_name="Earlier Gmail exercise",
        template=gmail_campaign.template,
        admin=gmail_campaign.admin,
        sending_profile=gmail_campaign.sending_profile,
    )
    prior = add_gmail_recipient(prior_campaign, 99)
    for _ in range(prior_count):
        db.session.add(
            TrackingEvent(
                recipient=prior,
                event_type="email_delivered",
                delivery_channel="gmail",
                occurred_at=utc_now() - timedelta(minutes=30),
            )
        )
    db.session.commit()
    with patch("smtplib.SMTP") as smtp_class:
        response = client.post(
            f"/api/campaigns/{gmail_campaign.campaign_id}/send",
            headers=auth_headers,
            json={"confirmation": (
                "SEND 1 REAL EMAIL" if pending_count == 1 else "SEND 2 REAL EMAILS"
            )},
        )
    assert response.status_code == status
    if status == 400:
        smtp_class.assert_not_called()
        assert db.session.query(TrackingEvent).count() == prior_count
    else:
        assert response.get_json()["delivered"] == 1


def test_gmail_hourly_count_ignores_other_channels_failures_and_older_successes(
    client, auth_headers, gmail_campaign
):
    prior = add_gmail_recipient(gmail_campaign, 99)
    now = utc_now()
    for event_type, channel, occurred_at in [
        ("email_delivered", "mailpit", now),
        ("email_delivered", None, now),
        ("email_failed", "gmail", now),
        ("email_delivered", "gmail", now - timedelta(hours=1, seconds=1)),
    ]:
        for _ in range(20):
            db.session.add(
                TrackingEvent(
                    recipient=prior, event_type=event_type, delivery_channel=channel,
                    occurred_at=occurred_at,
                )
            )
    db.session.commit()
    with patch("smtplib.SMTP"):
        response = client.post(
            f"/api/campaigns/{gmail_campaign.campaign_id}/send",
            headers=auth_headers,
            json={"confirmation": "SEND 1 REAL EMAIL"},
        )
    assert response.status_code == 200
    assert response.get_json()["delivered"] == 1


def test_gmail_hourly_count_includes_successes_exactly_one_hour_ago(
    client, auth_headers, gmail_campaign, app
):
    app.config["MAX_EMAILS_PER_HOUR"] = 100
    prior = add_gmail_recipient(gmail_campaign, 99)
    now = utc_now()
    for _ in range(20):
        db.session.add(
            TrackingEvent(
                recipient=prior, event_type="email_delivered", delivery_channel="gmail",
                occurred_at=now - timedelta(hours=1),
            )
        )
    db.session.commit()
    with patch("app.email_delivery.utc_now", return_value=now), patch(
        "smtplib.SMTP"
    ) as smtp_class:
        response = client.post(
            f"/api/campaigns/{gmail_campaign.campaign_id}/send",
            headers=auth_headers,
            json={"confirmation": "SEND 1 REAL EMAIL"},
        )
    assert response.status_code == 400
    smtp_class.assert_not_called()


@pytest.mark.parametrize("channel", [None, "mailpit", "gmail"])
def test_gmail_never_resends_recipients_with_historical_delivery_events(
    client, auth_headers, gmail_campaign, channel
):
    delivered_recipient = gmail_campaign.recipients[0]
    add_gmail_recipient(gmail_campaign, 2)
    db.session.add(
        TrackingEvent(
            recipient=delivered_recipient, event_type="email_delivered",
            delivery_channel=channel, occurred_at=utc_now() - timedelta(days=2),
        )
    )
    db.session.commit()
    preview = client.get(
        f"/api/campaigns/{gmail_campaign.campaign_id}/delivery-preview",
        headers=auth_headers,
    ).get_json()["preview"]
    assert preview["already_delivered"] == 1
    assert [user["email"] for user in preview["allowed_recipients"]] == [
        "recipient2@example.com"
    ]
    assert preview["confirmation_phrase"] == "SEND 1 REAL EMAIL"
    with patch("smtplib.SMTP") as smtp_class:
        response = client.post(
            f"/api/campaigns/{gmail_campaign.campaign_id}/send",
            headers=auth_headers,
            json={"confirmation": "SEND 1 REAL EMAIL"},
        )
    assert response.status_code == 200
    assert response.get_json()["delivered"] == 1
    messages = smtp_class.return_value.__enter__.return_value.send_message.call_args_list
    assert [call.args[0]["To"] for call in messages] == ["recipient2@example.com"]
    events = db.session.scalars(db.select(TrackingEvent).order_by(TrackingEvent.event_id)).all()
    assert [event.delivery_channel for event in events] == [channel, "gmail"]
    refreshed = client.get(
        f"/api/campaigns/{gmail_campaign.campaign_id}/delivery-preview",
        headers=auth_headers,
    ).get_json()["preview"]
    assert refreshed["already_delivered"] == 2
    assert refreshed["allowed_recipients"] == []
    assert refreshed["confirmation_phrase"] == "SEND 0 REAL EMAILS"
    with patch("smtplib.SMTP") as smtp_class:
        repeated = client.post(
            f"/api/campaigns/{gmail_campaign.campaign_id}/send",
            headers=auth_headers,
            json={"confirmation": "SEND 0 REAL EMAILS"},
        )
    assert repeated.status_code == 400
    smtp_class.assert_not_called()
    assert db.session.query(TrackingEvent).count() == 2


def test_gmail_partial_failure_commits_success_and_retries_only_remaining_recipients(
    client, auth_headers, gmail_campaign, caplog
):
    second = add_gmail_recipient(gmail_campaign, 2)
    third = add_gmail_recipient(gmail_campaign, 3)
    delivered_recipient = gmail_campaign.recipients[0]
    commits_before_each_message = []
    messages = []

    with patch("smtplib.SMTP") as smtp_class, patch.object(
        db.session, "commit", wraps=db.session.commit
    ) as commit:
        def accept_first_message(message, **kwargs):
            commits_before_each_message.append(commit.call_count)
            messages.append(message)
            if len(messages) == 2:
                raise smtplib.SMTPDataError(550, b"provider-secret-abcdefghijklmnop")

        smtp_class.return_value.__enter__.return_value.send_message.side_effect = (
            accept_first_message
        )
        response = client.post(
            f"/api/campaigns/{gmail_campaign.campaign_id}/send",
            headers=auth_headers,
            json={"confirmation": "SEND 3 REAL EMAILS"},
        )
    assert response.status_code == 502
    assert commits_before_each_message == [0, 1]
    assert [message["To"] for message in messages] == [
        "jordan@example.com", "recipient2@example.com"
    ]
    assert "provider-secret" not in response.get_data(as_text=True)
    assert "abcdefghijklmnop" not in response.get_data(as_text=True)
    assert "provider-secret" not in caplog.text
    events = db.session.scalars(db.select(TrackingEvent).order_by(TrackingEvent.event_id)).all()
    assert [(event.recipient_id, event.event_type, event.delivery_channel) for event in events] == [
        (delivered_recipient.recipient_id, "email_delivered", "gmail"),
        (second.recipient_id, "email_failed", "gmail"),
        (third.recipient_id, "email_failed", "gmail"),
    ]
    assert gmail_campaign.status == "delivery_failed"
    preview = client.get(
        f"/api/campaigns/{gmail_campaign.campaign_id}/delivery-preview",
        headers=auth_headers,
    ).get_json()["preview"]
    assert preview["already_delivered"] == 1
    assert [user["email"] for user in preview["allowed_recipients"]] == [
        "recipient2@example.com", "recipient3@example.com"
    ]
    assert preview["confirmation_phrase"] == "SEND 2 REAL EMAILS"
    with patch("smtplib.SMTP") as retry_smtp:
        retry = client.post(
            f"/api/campaigns/{gmail_campaign.campaign_id}/send",
            headers=auth_headers,
            json={"confirmation": "SEND 2 REAL EMAILS"},
        )
    assert retry.status_code == 200
    assert retry.get_json()["delivered"] == 2
    retried_messages = retry_smtp.return_value.__enter__.return_value.send_message.call_args_list
    assert [call.args[0]["To"] for call in retried_messages] == [
        "recipient2@example.com", "recipient3@example.com"
    ]
    assert gmail_campaign.status == "active"


@pytest.mark.parametrize("stage", ["connect", "starttls", "login"])
def test_gmail_provider_failures_are_sanitized_and_record_attempted_channel(
    client, auth_headers, gmail_campaign, stage, caplog
):
    with patch("smtplib.SMTP") as smtp_class:
        smtp = smtp_class.return_value.__enter__.return_value
        if stage == "connect":
            smtp_class.side_effect = OSError("provider-secret-abcdefghijklmnop")
        else:
            getattr(smtp, stage).side_effect = smtplib.SMTPAuthenticationError(
                535, b"provider-secret-abcdefghijklmnop"
            )
        response = client.post(
            f"/api/campaigns/{gmail_campaign.campaign_id}/send",
            headers=auth_headers,
            json={"confirmation": "SEND 1 REAL EMAIL"},
        )
    assert response.status_code == 502
    smtp.send_message.assert_not_called()
    assert "provider-secret" not in response.get_data(as_text=True)
    assert "abcdefghijklmnop" not in response.get_data(as_text=True)
    assert "provider-secret" not in caplog.text
    events = db.session.scalars(db.select(TrackingEvent)).all()
    assert [(event.event_type, event.delivery_channel) for event in events] == [
        ("email_failed", "gmail")
    ]
    assert gmail_campaign.status == "delivery_failed"


@pytest.mark.parametrize(
    "email",
    [
        "approved@example.com, unapproved@example.com",
        "Approved <approved@example.com>, Unapproved <unapproved@example.com>",
        "training-list: approved@example.com, unapproved@example.com;",
        "approved@example.com; unapproved@example.com",
        "not-an-address",
        "@example.com",
        "approved@",
        "approved@example.com trailing",
        "approved@example.com\nBcc: unapproved@example.com",
    ],
)
def test_gmail_preview_and_send_block_approved_rows_without_one_valid_mailbox(
    client, auth_headers, gmail_campaign, email
):
    gmail_campaign.recipients[0].user.email = email
    db.session.commit()
    preview = client.get(
        f"/api/campaigns/{gmail_campaign.campaign_id}/delivery-preview",
        headers=auth_headers,
    ).get_json()["preview"]
    assert preview["allowed_recipients"] == []
    assert [user["email"] for user in preview["blocked_recipients"]] == [email]
    assert preview["confirmation_phrase"] == "SEND 0 REAL EMAILS"
    with patch("smtplib.SMTP") as smtp_class:
        response = client.post(
            f"/api/campaigns/{gmail_campaign.campaign_id}/send",
            headers=auth_headers,
            json={"confirmation": "SEND 0 REAL EMAILS"},
        )
    assert response.status_code == 403
    smtp_class.assert_not_called()
    assert db.session.query(TrackingEvent).count() == 0


@pytest.mark.parametrize(
    "email,envelope_address",
    [
        ("approved+training@example.com", "approved+training@example.com"),
        ('"approved user"@example.com', '"approved user"@example.com'),
        ("approved@example.com (Training)", "approved@example.com"),
    ],
)
def test_gmail_binds_delivery_to_one_validated_envelope_recipient(
    client, auth_headers, gmail_campaign, email, envelope_address
):
    gmail_campaign.recipients[0].user.email = email
    db.session.commit()
    with patch("smtplib.SMTP") as smtp_class:
        response = client.post(
            f"/api/campaigns/{gmail_campaign.campaign_id}/send",
            headers=auth_headers,
            json={"confirmation": "SEND 1 REAL EMAIL"},
        )
    assert response.status_code == 200
    smtp = smtp_class.return_value.__enter__.return_value
    assert smtp.send_message.call_args.kwargs == {"to_addrs": [envelope_address]}
    assert smtp.send_message.call_args.args[0]["To"] == envelope_address


def test_gmail_message_uses_the_mailbox_validated_before_smtp_setup(
    client, auth_headers, gmail_campaign
):
    def change_mailbox_during_setup(**kwargs):
        gmail_campaign.recipients[0].user.email = "changed@example.com\nBcc: unapproved@example.com"
        db.session.commit()

    with patch("smtplib.SMTP") as smtp_class:
        smtp = smtp_class.return_value.__enter__.return_value
        smtp.starttls.side_effect = change_mailbox_during_setup
        response = client.post(
            f"/api/campaigns/{gmail_campaign.campaign_id}/send",
            headers=auth_headers,
            json={"confirmation": "SEND 1 REAL EMAIL"},
        )
    assert response.status_code == 200
    assert smtp.send_message.call_args.args[0]["To"] == "jordan@example.com"
    assert smtp.send_message.call_args.kwargs == {"to_addrs": ["jordan@example.com"]}


@pytest.mark.parametrize("change", ["added", "delivered"])
def test_gmail_requires_fresh_confirmation_when_pending_count_changes_under_lock(
    client, auth_headers, gmail_campaign, app, change
):
    campaign_id = gmail_campaign.campaign_id
    if change == "delivered":
        add_gmail_recipient(gmail_campaign, 2)
    original_phrase = "SEND 1 REAL EMAIL" if change == "added" else "SEND 2 REAL EMAILS"

    @contextmanager
    def lock_after_recipient_change():
        with app.app_context():
            current = db.session.get(Campaign, campaign_id)
            if change == "added":
                add_gmail_recipient(current, 2)
            else:
                db.session.add(
                    TrackingEvent(
                        recipient=current.recipients[0], event_type="email_delivered",
                        delivery_channel="gmail",
                    )
                )
                db.session.commit()
        yield

    with patch("app.email_delivery.GMAIL_SEND_LOCK", lock_after_recipient_change()), patch(
        "smtplib.SMTP"
    ) as smtp_class:
        response = client.post(
            f"/api/campaigns/{campaign_id}/send",
            headers=auth_headers,
            json={"confirmation": original_phrase},
        )
    assert response.status_code == 400
    smtp_class.assert_not_called()
    preview = client.get(
        f"/api/campaigns/{campaign_id}/delivery-preview", headers=auth_headers
    ).get_json()["preview"]
    fresh_phrase = "SEND 2 REAL EMAILS" if change == "added" else "SEND 1 REAL EMAIL"
    assert preview["confirmation_phrase"] == fresh_phrase
    with patch("smtplib.SMTP"):
        retry = client.post(
            f"/api/campaigns/{campaign_id}/send",
            headers=auth_headers,
            json={"confirmation": fresh_phrase},
        )
    assert retry.status_code == 200
    assert retry.get_json()["delivered"] == (2 if change == "added" else 1)


@pytest.mark.parametrize("credential_problem", ["missing_key", "invalid_ciphertext", "missing"])
def test_gmail_credential_failures_do_not_expose_secrets_or_send_messages(
    client, auth_headers, gmail_campaign, app, credential_problem, caplog
):
    if credential_problem == "missing_key":
        app.config["SENDING_PROFILE_ENCRYPTION_KEY"] = ""
    elif credential_problem == "invalid_ciphertext":
        gmail_campaign.sending_profile.encrypted_app_password = "invalid-secret-ciphertext"
    else:
        gmail_campaign.sending_profile.encrypted_app_password = None
    db.session.commit()
    with patch("smtplib.SMTP") as smtp_class:
        smtp = smtp_class.return_value.__enter__.return_value
        response = client.post(
            f"/api/campaigns/{gmail_campaign.campaign_id}/send",
            headers=auth_headers,
            json={"confirmation": "SEND 1 REAL EMAIL"},
        )
    assert response.status_code == 502
    smtp.login.assert_not_called()
    smtp.send_message.assert_not_called()
    for marker in ("invalid-secret-ciphertext", "abcdefghijklmnop"):
        assert marker not in response.get_data(as_text=True)
        assert marker not in caplog.text
    events = db.session.scalars(db.select(TrackingEvent)).all()
    assert [(event.event_type, event.delivery_channel) for event in events] == [
        ("email_failed", "gmail")
    ]


@pytest.fixture()
def gmail_concurrency_app(tmp_path):
    class ConcurrentConfig(BackendTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'gmail-concurrent.db').as_posix()}"
        PUBLIC_BASE_URL = "https://training.example.com"

    app = create_app(ConcurrentConfig)
    with app.app_context():
        db.create_all()
        admin = Admin(name="Admin", email="admin@example.com", password_hash="unused")
        template = EmailTemplate(template_name="Training", subject="Training", body="Training")
        profile = SendingProfile(
            name="Training Gmail", from_name="Simulation Admin",
            from_email="simulation@gmail.com",
            encrypted_app_password=encrypt_app_password("abcdefghijklmnop"),
            enabled=True, last_test_succeeded=True, last_tested_at=utc_now(),
        )
        campaigns = [
            Campaign(
                campaign_name=f"Concurrent exercise {index}", admin=admin,
                template=template, sending_profile=profile,
            )
            for index in range(3)
        ]
        db.session.add_all([
            CampaignRecipient(
                campaign=campaign,
                user=User(
                    name=f"Employee {index}", email=f"employee{index}@example.com",
                    simulation_email_approved=True,
                ),
                tracking_token=f"concurrent-tracking-{index}",
            )
            for index, campaign in enumerate(campaigns)
        ])
        db.session.commit()
        campaign_ids = [campaign.campaign_id for campaign in campaigns]
    yield app, campaign_ids
    with app.app_context():
        db.drop_all()
        db.session.remove()
        db.engine.dispose()


@pytest.mark.parametrize("same_campaign,prior_count", [(False, 19), (True, 0)])
def test_overlapping_gmail_sends_recheck_hourly_allowance_and_pending_recipients(
    gmail_concurrency_app, same_campaign, prior_count
):
    app, campaign_ids = gmail_concurrency_app
    with app.app_context():
        historical = db.session.get(Campaign, campaign_ids[2]).recipients[0]
        db.session.add_all([
            TrackingEvent(
                recipient=historical, event_type="email_delivered", delivery_channel="gmail"
            )
            for _ in range(prior_count)
        ])
        db.session.commit()

    first_sending = Event()
    release_first = Event()
    second_ready = Event()
    lock = Lock()
    outcomes = {}
    accepted = []

    class ObservedLock:
        def __enter__(self):
            if current_thread().name == "gmail-second":
                second_ready.set()
            lock.acquire()

        def __exit__(self, *args):
            lock.release()

    def attempt_send(campaign_id):
        name = current_thread().name
        try:
            with app.app_context():
                campaign = db.session.get(Campaign, campaign_id)
                email_delivery.delivery_preview(campaign)
                outcomes[name] = email_delivery.send_campaign(campaign)
        except Exception as error:
            outcomes[name] = error
        finally:
            if name == "gmail-second":
                second_ready.set()

    def accept_message(message, *, to_addrs):
        accepted.append((message["To"], to_addrs))
        if current_thread().name == "gmail-first":
            first_sending.set()
            assert release_first.wait(5), "First sender was not released"

    first = Thread(target=attempt_send, args=(campaign_ids[0],), name="gmail-first")
    second = Thread(
        target=attempt_send,
        args=(campaign_ids[0] if same_campaign else campaign_ids[1],),
        name="gmail-second",
    )
    with patch("app.email_delivery.GMAIL_SEND_LOCK", ObservedLock(), create=True), patch(
        "smtplib.SMTP"
    ) as smtp_class:
        smtp_class.return_value.__enter__.return_value.send_message.side_effect = accept_message
        try:
            first.start()
            assert first_sending.wait(5), "First sender did not reach SMTP"
            second.start()
            assert second_ready.wait(5), "Second sender did not contend or finish"
        finally:
            release_first.set()
            for thread in (first, second):
                if thread.ident is not None:
                    thread.join(5)
        assert not first.is_alive() and not second.is_alive()

    assert outcomes["gmail-first"] == 1
    assert isinstance(outcomes["gmail-second"], ValueError)
    smtp_class.assert_called_once_with("smtp.gmail.com", 587, timeout=10)
    assert accepted == [("employee0@example.com", ["employee0@example.com"])]
    with app.app_context():
        successes = db.session.scalar(
            db.select(db.func.count(TrackingEvent.event_id)).where(
                TrackingEvent.event_type == "email_delivered",
                TrackingEvent.delivery_channel == "gmail",
            )
        )
        assert successes == prior_count + 1


@pytest.mark.parametrize(
    "change",
    ["disabled_profile", "failed_test", "unapproved", "address_list", "removed_profile",
     "new_unapproved", "pending_overflow", "delivery_disabled", "unsafe_url"],
)
def test_gmail_revalidates_current_state_after_acquiring_send_lock(
    gmail_concurrency_app, change
):
    app, campaign_ids = gmail_concurrency_app

    @contextmanager
    def lock_after_state_change():
        with app.app_context():
            latest = db.session.get(Campaign, campaign_ids[0])
            if change == "disabled_profile":
                latest.sending_profile.enabled = False
            elif change == "failed_test":
                latest.sending_profile.last_test_succeeded = False
            elif change == "unapproved":
                latest.recipients[0].user.simulation_email_approved = False
            elif change == "address_list":
                latest.recipients[0].user.email = "approved@example.com, unapproved@example.com"
            elif change == "removed_profile":
                latest.sending_profile = None
            elif change == "new_unapproved":
                add_gmail_recipient(latest, 10, approved=False)
            elif change == "pending_overflow":
                for index in range(10, 20):
                    add_gmail_recipient(latest, index)
            elif change == "delivery_disabled":
                app.config["MAIL_DELIVERY_ENABLED"] = False
            else:
                app.config["PUBLIC_BASE_URL"] = "http://training.example.com"
            db.session.commit()
        yield

    with app.app_context():
        campaign = db.session.get(Campaign, campaign_ids[0])
        initial = email_delivery.delivery_preview(campaign)
        assert initial["profile_ready"] is True
        assert len(initial["allowed_recipients"]) == 1
        with patch(
            "app.email_delivery.GMAIL_SEND_LOCK", lock_after_state_change(), create=True
        ), patch("smtplib.SMTP") as smtp_class:
            with pytest.raises((ValueError, PermissionError)):
                email_delivery.send_campaign(campaign)
        smtp_class.assert_not_called()
        assert db.session.query(TrackingEvent).count() == 0
