import pytest

from app.extensions import db
from app.models import SendingProfile


def test_user_crud(client, auth_headers):
    created = client.post(
        "/api/users",
        headers=auth_headers,
        json={
            "name": "Aisha Tan",
            "email": "aisha@example.com",
            "department": "Finance",
        },
    )
    assert created.status_code == 201
    created_user = created.get_json()["user"]
    user_id = created_user["user_id"]
    assert created_user["simulation_email_approved"] is False

    duplicate = client.post(
        "/api/users",
        headers=auth_headers,
        json={"name": "Duplicate", "email": "aisha@example.com"},
    )
    assert duplicate.status_code == 409

    updated = client.patch(
        f"/api/users/{user_id}",
        headers=auth_headers,
        json={"department": "Operations", "role": "manager"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["user"]["department"] == "Operations"
    approved = client.patch(
        f"/api/users/{user_id}",
        headers=auth_headers,
        json={"simulation_email_approved": True},
    )
    assert approved.status_code == 200
    assert approved.get_json()["user"]["simulation_email_approved"] is True
    invalid_approval = client.patch(
        f"/api/users/{user_id}",
        headers=auth_headers,
        json={"simulation_email_approved": "yes"},
    )
    assert invalid_approval.status_code == 400
    assert len(client.get("/api/users", headers=auth_headers).get_json()["users"]) == 1
    assert client.delete(f"/api/users/{user_id}", headers=auth_headers).status_code == 204


def test_template_and_campaign_crud(client, auth_headers):
    template_response = client.post(
        "/api/templates",
        headers=auth_headers,
        json={
            "template_name": "Password reset",
            "subject": "Password expiry warning",
            "body": "Review your account immediately.",
            "category": "credential",
        },
    )
    assert template_response.status_code == 201
    template_id = template_response.get_json()["template"]["template_id"]

    updated_template = client.patch(
        f"/api/templates/{template_id}",
        headers=auth_headers,
        json={
            "template_name": "Document review",
            "subject": "Review the shared document",
            "body": "Open the controlled simulation link.",
            "category": "document",
        },
    )
    assert updated_template.status_code == 200
    updated_template_body = updated_template.get_json()["template"]
    assert updated_template_body["template_name"] == "Document review"
    assert updated_template_body["category"] == "document"

    invalid_template = client.patch(
        f"/api/templates/{template_id}",
        headers=auth_headers,
        json={"subject": "   "},
    )
    assert invalid_template.status_code == 400

    campaign_response = client.post(
        "/api/campaigns",
        headers=auth_headers,
        json={
            "campaign_name": "August awareness exercise",
            "template_id": template_id,
            "scheduled_date": "2026-08-25T09:00:00+08:00",
        },
    )
    assert campaign_response.status_code == 201
    campaign_id = campaign_response.get_json()["campaign"]["campaign_id"]

    assert (
        client.delete(f"/api/templates/{template_id}", headers=auth_headers).status_code
        == 409
    )
    updated = client.patch(
        f"/api/campaigns/{campaign_id}",
        headers=auth_headers,
        json={"status": "scheduled"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["campaign"]["status"] == "scheduled"
    assert client.delete(f"/api/campaigns/{campaign_id}", headers=auth_headers).status_code == 204
    assert client.delete(f"/api/templates/{template_id}", headers=auth_headers).status_code == 204


@pytest.fixture()
def campaign_payload(client, auth_headers):
    response = client.post(
        "/api/templates",
        headers=auth_headers,
        json={
            "template_name": "Document review",
            "subject": "Review the shared document",
            "body": "Open the controlled simulation link.",
        },
    )
    assert response.status_code == 201
    return {
        "campaign_name": "Awareness exercise",
        "template_id": response.get_json()["template"]["template_id"],
    }


@pytest.fixture()
def gmail_profile(client, auth_headers):
    response = client.post(
        "/api/sending-profile",
        headers=auth_headers,
        json={
            "name": "Personal Gmail",
            "from_name": "Simulation Admin",
            "from_email": "owner@gmail.com",
            "app_password": "abcd efgh ijkl mnop",
        },
    )
    assert response.status_code == 201
    return response.get_json()["profile"]


@pytest.mark.parametrize("selection", [{}, {"sending_profile_id": None}])
def test_campaign_defaults_to_mailpit(client, auth_headers, campaign_payload, selection):
    response = client.post(
        "/api/campaigns", headers=auth_headers, json={**campaign_payload, **selection}
    )
    assert response.status_code == 201
    campaign = response.get_json()["campaign"]
    assert campaign["delivery_method"] == "mailpit"
    assert campaign["sending_profile"] is None


def test_campaign_selects_gmail_and_returns_only_safe_metadata(
    client, auth_headers, campaign_payload, gmail_profile
):
    response = client.post(
        "/api/campaigns",
        headers=auth_headers,
        json={**campaign_payload, "sending_profile_id": gmail_profile["profile_id"]},
    )
    assert response.status_code == 201
    campaign = response.get_json()["campaign"]
    assert campaign["delivery_method"] == "gmail"
    profile = campaign["sending_profile"]
    assert profile["profile_id"] == gmail_profile["profile_id"]
    assert profile["name"] == "Personal Gmail"
    assert profile["provider"] == "gmail"
    assert profile["from_name"] == "Simulation Admin"
    assert profile["from_email"] == "owner@gmail.com"
    assert profile["credential_configured"] is True
    assert profile["enabled"] is False
    assert profile["last_tested_at"] is None
    assert profile["last_test_succeeded"] is False
    stored_profile = db.session.get(SendingProfile, gmail_profile["profile_id"])
    listed = client.get("/api/campaigns", headers=auth_headers)
    assert listed.get_json()["campaigns"][0]["sending_profile"] == profile
    for serialized in (response.get_data(as_text=True), listed.get_data(as_text=True)):
        for secret in (
            "abcd efgh ijkl mnop",
            "abcdefghijklmnop",
            stored_profile.encrypted_app_password,
            "encrypted_app_password",
            '"app_password"',
        ):
            assert secret not in serialized


def test_campaign_patch_switches_delivery_and_preserves_omitted_selection(
    client, auth_headers, campaign_payload, gmail_profile
):
    created = client.post("/api/campaigns", headers=auth_headers, json=campaign_payload)
    assert created.status_code == 201
    campaign_id = created.get_json()["campaign"]["campaign_id"]
    selected = client.patch(
        f"/api/campaigns/{campaign_id}",
        headers=auth_headers,
        json={"sending_profile_id": gmail_profile["profile_id"]},
    )
    assert selected.status_code == 200
    assert selected.get_json()["campaign"]["delivery_method"] == "gmail"
    assert selected.get_json()["campaign"]["sending_profile"]["profile_id"] == gmail_profile["profile_id"]
    renamed = client.patch(
        f"/api/campaigns/{campaign_id}",
        headers=auth_headers,
        json={"campaign_name": "Renamed exercise"},
    )
    assert renamed.status_code == 200
    assert renamed.get_json()["campaign"]["delivery_method"] == "gmail"
    assert renamed.get_json()["campaign"]["sending_profile"]["profile_id"] == gmail_profile["profile_id"]
    cleared = client.patch(
        f"/api/campaigns/{campaign_id}",
        headers=auth_headers,
        json={"sending_profile_id": None},
    )
    assert cleared.status_code == 200
    assert cleared.get_json()["campaign"]["delivery_method"] == "mailpit"
    assert cleared.get_json()["campaign"]["sending_profile"] is None
    persisted = client.get("/api/campaigns", headers=auth_headers).get_json()["campaigns"][0]
    assert persisted["delivery_method"] == "mailpit"
    assert persisted["sending_profile"] is None


@pytest.mark.parametrize("method", ["post", "patch"])
@pytest.mark.parametrize("profile_id", [True, False, "1", 1.0, {}, []])
def test_campaign_rejects_non_integer_profile_ids(
    client, auth_headers, campaign_payload, gmail_profile, method, profile_id
):
    path = "/api/campaigns"
    if method == "patch":
        created = client.post(path, headers=auth_headers, json=campaign_payload)
        assert created.status_code == 201
        path += f'/{created.get_json()["campaign"]["campaign_id"]}'
    response = getattr(client, method)(
        path,
        headers=auth_headers,
        json={**campaign_payload, "sending_profile_id": profile_id},
    )
    assert response.status_code == 400


@pytest.mark.parametrize("method", ["post", "patch"])
@pytest.mark.parametrize("profile_id", [0, -1, 999, 9223372036854775808, -9223372036854775809])
def test_campaign_rejects_unknown_profile_ids(
    client, auth_headers, campaign_payload, gmail_profile, method, profile_id
):
    path = "/api/campaigns"
    if method == "patch":
        created = client.post(path, headers=auth_headers, json=campaign_payload)
        assert created.status_code == 201
        path += f'/{created.get_json()["campaign"]["campaign_id"]}'
    response = getattr(client, method)(
        path,
        headers=auth_headers,
        json={**campaign_payload, "sending_profile_id": profile_id},
    )
    assert response.status_code == 404
