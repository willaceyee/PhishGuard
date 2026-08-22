def test_security_headers_are_applied(client):
    response = client.get("/api/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"


def test_cors_allows_configured_frontend_only(client):
    allowed = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    denied = client.get("/api/health", headers={"Origin": "https://untrusted.example"})
    assert allowed.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert "Access-Control-Allow-Origin" not in denied.headers


def test_admin_can_change_password(client, auth_headers):
    wrong = client.post(
        "/api/auth/change-password",
        headers=auth_headers,
        json={"current_password": "wrong-password", "new_password": "new-secure-password"},
    )
    assert wrong.status_code == 401

    too_short = client.post(
        "/api/auth/change-password",
        headers=auth_headers,
        json={"current_password": "secure-password", "new_password": "short"},
    )
    assert too_short.status_code == 400

    changed = client.post(
        "/api/auth/change-password",
        headers=auth_headers,
        json={
            "current_password": "secure-password",
            "new_password": "replacement-password-2026",
        },
    )
    assert changed.status_code == 200
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "secure-password"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login",
            json={
                "email": "admin@example.com",
                "password": "replacement-password-2026",
            },
        ).status_code
        == 200
    )


def test_password_change_requires_authentication(client):
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": "secure-password", "new_password": "replacement-password"},
    )
    assert response.status_code == 401
