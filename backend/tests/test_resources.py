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
    user_id = created.get_json()["user"]["user_id"]

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

