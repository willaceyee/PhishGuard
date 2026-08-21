from app.extensions import db
from app.models import TrackingEvent


def create_campaign_with_user(client, auth_headers):
    user = client.post(
        "/api/users",
        headers=auth_headers,
        json={"name": "Jordan Lee", "email": "jordan@example.com"},
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

