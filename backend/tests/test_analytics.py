def create_dashboard_campaign(client, auth_headers):
    users = []
    for name, email, department in (
        ("High Risk", "high@example.com", "Finance"),
        ("No Interaction", "quiet@example.com", "Operations"),
    ):
        users.append(
            client.post(
                "/api/users",
                headers=auth_headers,
                json={"name": name, "email": email, "department": department},
            ).get_json()["user"]
        )
    template = client.post(
        "/api/templates",
        headers=auth_headers,
        json={
            "template_name": "Dashboard test",
            "subject": "Review required",
            "body": "Review your account.",
        },
    ).get_json()["template"]
    campaign = client.post(
        "/api/campaigns",
        headers=auth_headers,
        json={
            "campaign_name": "Dashboard campaign",
            "template_id": template["template_id"],
            "status": "active",
        },
    ).get_json()["campaign"]
    recipients = client.post(
        f"/api/campaigns/{campaign['campaign_id']}/recipients",
        headers=auth_headers,
        json={"user_ids": [user["user_id"] for user in users]},
    ).get_json()["recipients"]
    return campaign, recipients


def test_dashboard_aggregates_unique_events_and_risk(client, auth_headers):
    campaign, recipients = create_dashboard_campaign(client, auth_headers)
    tracking_path = recipients[0]["tracking_url"].removeprefix("http://localhost")

    first_click = client.get(tracking_path)
    client.get(tracking_path)
    landing_path = first_click.headers["Location"]
    client.get(landing_path)
    training_redirect = client.post(f"{landing_path}/submit")
    training_path = training_redirect.headers["Location"]
    client.get(training_path)
    token = training_path.rsplit("/", 1)[-1]
    client.post(
        f"/quiz/{token}",
        data={"sender": "b", "urgent": "a", "credentials": "a", "report": "b"},
    )

    response = client.get("/api/dashboard/overview", headers=auth_headers)
    assert response.status_code == 200
    body = response.get_json()
    summary = body["summary"]
    assert summary["total_campaigns"] == 1
    assert summary["total_users"] == 2
    assert summary["total_recipients"] == 2
    assert summary["unique_clicked"] == 1
    assert summary["click_through_rate"] == 50.0
    assert summary["unique_submitted"] == 1
    assert summary["training_completion_rate"] == 50.0
    assert summary["average_quiz_percentage"] == 0.0
    assert summary["high_risk_users"] == 1

    campaign_row = body["campaigns"][0]
    assert campaign_row["campaign_id"] == campaign["campaign_id"]
    assert campaign_row["click_through_rate"] == 50.0
    assert campaign_row["submission_rate"] == 50.0
    assert campaign_row["training_completion_rate"] == 50.0

    risks = body["user_risks"]
    assert risks[0]["name"] == "High Risk"
    assert risks[0]["risk_score"] == 80
    assert risks[0]["risk_band"] == "high"
    assert risks[1]["risk_score"] == 30
    assert risks[1]["risk_band"] == "medium"
    assert body["risk_method"]["weights"]["submitted"] == 45


def test_empty_dashboard_and_authentication(client, auth_headers):
    assert client.get("/api/dashboard/overview").status_code == 401
    response = client.get("/api/dashboard/overview", headers=auth_headers)
    assert response.status_code == 200
    summary = response.get_json()["summary"]
    assert summary["total_campaigns"] == 0
    assert summary["click_through_rate"] == 0.0
    assert summary["average_quiz_percentage"] is None
