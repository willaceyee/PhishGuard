def test_health_endpoint_is_public(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "healthy"


def test_bootstrap_login_and_current_admin(client):
    details = {
        "name": "Admin User",
        "email": "ADMIN@example.com",
        "password": "strong-password",
    }
    assert client.post("/api/auth/bootstrap", json=details).status_code == 201
    assert client.post("/api/auth/bootstrap", json=details).status_code == 409

    bad_login = client.post(
        "/api/auth/login", json={"email": details["email"], "password": "wrong-pass"}
    )
    assert bad_login.status_code == 401

    login = client.post(
        "/api/auth/login",
        json={"email": details["email"], "password": details["password"]},
    )
    assert login.status_code == 200
    body = login.get_json()
    assert body["admin"]["email"] == "admin@example.com"

    current = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert current.status_code == 200
    assert "password_hash" not in current.get_json()["admin"]


def test_management_endpoints_require_authentication(client):
    for endpoint in ("/api/users", "/api/templates", "/api/campaigns"):
        assert client.get(endpoint).status_code == 401

