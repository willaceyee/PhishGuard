from unittest.mock import patch

from app.extensions import db
from app.models import TrackingEvent


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
        assert message["Subject"].startswith("[SECURITY SIMULATION]")
        assert message["X-PhishGuard-Simulation"] == "authorized-training"
        assert "/track/" in message.get_content()
        assert "Do not enter or send a real password" in message.get_content()

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
