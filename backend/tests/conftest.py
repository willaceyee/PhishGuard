import pytest

from app import create_app
from app.extensions import db


@pytest.fixture()
def app():
    app = create_app("config.TestConfig")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth_headers(client):
    response = client.post(
        "/api/auth/bootstrap",
        json={
            "name": "Test Admin",
            "email": "admin@example.com",
            "password": "secure-password",
        },
    )
    assert response.status_code == 201
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "secure-password"},
    )
    token = response.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

