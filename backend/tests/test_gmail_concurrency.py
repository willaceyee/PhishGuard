from threading import Event, Lock, Thread, current_thread
from unittest.mock import patch

import pytest
from flask_jwt_extended import create_access_token

from app import create_app
from app.extensions import db
from app.models import (
    Admin, Campaign, CampaignRecipient, EmailTemplate, SendingProfile, TrackingEvent,
    User, utc_now,
)
from app.sending_profiles import decrypt_app_password, encrypt_app_password, profile_updates
from config import TestConfig as BackendTestConfig


@pytest.fixture()
def concurrent_gmail(tmp_path):
    class ConcurrentConfig(BackendTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'gmail.db').as_posix()}"
        PUBLIC_BASE_URL = "https://training.example.com"

    app = create_app(ConcurrentConfig)
    with app.app_context():
        db.create_all()
        admin = Admin(name="Admin", email="admin@example.com", password_hash="unused")
        profile = SendingProfile(
            name="Training Gmail", from_name="Simulation Admin",
            from_email="simulation@gmail.com",
            encrypted_app_password=encrypt_app_password("abcdefghijklmnop"),
            enabled=True, last_test_succeeded=True, last_tested_at=utc_now(),
        )
        campaign = Campaign(
            campaign_name="Concurrent exercise", admin=admin, sending_profile=profile,
            template=EmailTemplate(template_name="Training", subject="Training", body="Training"),
        )
        sender = User(name="Sender", email="simulation@gmail.com", simulation_email_approved=True)
        db.session.add(sender)
        for index in range(2):
            db.session.add(CampaignRecipient(
                campaign=campaign,
                user=User(name=f"Employee {index}", email=f"employee{index}@example.com",
                          simulation_email_approved=True),
                tracking_token=f"concurrent-token-{index}",
            ))
        db.session.commit()
        headers = {"Authorization": f"Bearer {create_access_token(identity=str(admin.admin_id))}"}
        campaign_id = campaign.campaign_id
        recipient_ids = [recipient.user_id for recipient in campaign.recipients]
    yield app, headers, campaign_id, recipient_ids
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.mark.parametrize(
    "updates,expected_success",
    [({"app_password": "qrst uvwx yzab cdef"}, False),
     ({"from_email": "replacement@gmail.com"}, False),
     ({"name": "Renamed", "from_name": "New display name"}, True)],
)
def test_overlapping_connection_test_and_patch_cannot_certify_replacement_credentials(
    concurrent_gmail, updates, expected_success,
):
    app, headers, _, _ = concurrent_gmail
    with app.app_context():
        profile = db.session.scalar(db.select(SendingProfile))
        profile.last_test_succeeded = False
        profile.last_tested_at = None
        db.session.commit()
    testing = Event()
    release_test = Event()
    mutation_ready = Event()
    outcomes = {}
    lock = Lock()

    class ObservedLock:
        def __enter__(self):
            if current_thread().name == "profile-mutation":
                mutation_ready.set()
            lock.acquire()

        def __exit__(self, *args):
            lock.release()

    def pause_login(*args):
        testing.set()
        assert release_test.wait(5), "Connection test was not released"

    def observe_mutation(data, **kwargs):
        if current_thread().name == "profile-mutation":
            mutation_ready.set()
        return profile_updates(data, **kwargs)

    def test_connection():
        with app.test_client() as client:
            outcomes["test"] = client.post("/api/sending-profile/test", headers=headers)

    def mutate_profile():
        try:
            with app.test_client() as client:
                outcomes["patch"] = client.patch(
                    "/api/sending-profile", headers=headers, json=updates,
                )
        finally:
            mutation_ready.set()

    first = Thread(target=test_connection, name="profile-test")
    second = Thread(target=mutate_profile, name="profile-mutation")
    with patch("app.sending_profiles.PROFILE_STATE_LOCK", ObservedLock(), create=True), patch(
        "app.sending_profiles.profile_updates", side_effect=observe_mutation
    ), patch("smtplib.SMTP") as smtp_class:
        smtp = smtp_class.return_value.__enter__.return_value
        smtp.login.side_effect = pause_login
        try:
            first.start()
            assert testing.wait(5), "Connection test did not reach SMTP"
            second.start()
            assert mutation_ready.wait(5), "Mutation did not contend or complete"
        finally:
            release_test.set()
            for thread in (first, second):
                if thread.ident is not None:
                    thread.join(5)
        assert not first.is_alive() and not second.is_alive()

    assert outcomes["test"].status_code == 200
    assert outcomes["patch"].status_code == 200
    smtp.login.assert_called_once_with("simulation@gmail.com", "abcdefghijklmnop")
    with app.app_context():
        saved = db.session.scalar(db.select(SendingProfile))
        assert saved.last_test_succeeded is expected_success
        assert (saved.last_tested_at is not None) is expected_success
        if "app_password" in updates:
            assert decrypt_app_password(saved.encrypted_app_password) == "qrstuvwxyzabcdef"
        if "from_email" in updates:
            assert saved.from_email == "replacement@gmail.com"


@pytest.mark.parametrize("stage", ["login", "first_message"])
@pytest.mark.parametrize(
    "change", ["disabled", "revoked", "revoked_later", "sender", "password",
               "failed_test", "removed_profile"],
)
def test_committed_gmail_gate_change_aborts_remaining_messages(concurrent_gmail, stage, change):
    app, headers, campaign_id, recipient_ids = concurrent_gmail
    reached = Event()
    release = Event()
    outcomes = {}
    accepted = []

    def pause():
        reached.set()
        assert release.wait(5), "Sender was not released"

    def accept(message, **kwargs):
        accepted.append((str(message["From"]), str(message["To"]), kwargs))
        if stage == "first_message" and len(accepted) == 1:
            pause()

    def send():
        with app.test_client() as client:
            outcomes["send"] = client.post(
                f"/api/campaigns/{campaign_id}/send", headers=headers,
                json={"confirmation": "SEND 2 REAL EMAILS"},
            )

    sender = Thread(target=send)
    with patch("smtplib.SMTP") as smtp_class:
        smtp = smtp_class.return_value.__enter__.return_value
        if stage == "login":
            smtp.login.side_effect = lambda *args: pause()
        smtp.send_message.side_effect = accept
        try:
            sender.start()
            assert reached.wait(5), "Sender did not reach the paused stage"
            with app.test_client() as client:
                if change in {"revoked", "revoked_later"}:
                    target = recipient_ids[0 if stage == "login" and change == "revoked" else 1]
                    mutation = client.patch(
                        f"/api/users/{target}", headers=headers,
                        json={"simulation_email_approved": False},
                    )
                elif change == "failed_test":
                    with patch("app.sending_profiles.test_gmail_profile", side_effect=RuntimeError()):
                        mutation = client.post("/api/sending-profile/test", headers=headers)
                elif change == "removed_profile":
                    mutation = client.patch(
                        f"/api/campaigns/{campaign_id}", headers=headers,
                        json={"sending_profile_id": None},
                    )
                else:
                    updates = {"disabled": {"enabled": False},
                               "sender": {"from_email": "replacement@gmail.com"},
                               "password": {"app_password": "qrst uvwx yzab cdef"}}[change]
                    mutation = client.patch("/api/sending-profile", headers=headers, json=updates)
                assert mutation.status_code == (503 if change == "failed_test" else 200)
        finally:
            release.set()
            if sender.ident is not None:
                sender.join(5)
        assert not sender.is_alive()

    assert outcomes["send"].status_code == (
        403 if change in {"revoked", "revoked_later"} else 400
    )
    expected_delivered = 0 if stage == "login" else 1
    assert len(accepted) == expected_delivered
    with app.app_context():
        events = db.session.scalars(db.select(TrackingEvent)).all()
        assert [(event.event_type, event.delivery_channel) for event in events] == [
            ("email_delivered", "gmail")
        ] * expected_delivered


def test_gmail_batch_keeps_authenticated_sender_snapshot_after_session_expiration(concurrent_gmail):
    app, headers, campaign_id, _ = concurrent_gmail
    reached = Event()
    release = Event()
    messages = []
    outcomes = {}

    def accept(message, **kwargs):
        messages.append((str(message["From"]), kwargs))
        if len(messages) == 1:
            reached.set()
            assert release.wait(5), "Sender was not released"

    def send():
        with app.test_client() as client:
            outcomes["send"] = client.post(
                f"/api/campaigns/{campaign_id}/send", headers=headers,
                json={"confirmation": "SEND 2 REAL EMAILS"},
            )

    sender = Thread(target=send)
    with patch("smtplib.SMTP") as smtp_class:
        smtp = smtp_class.return_value.__enter__.return_value
        smtp.send_message.side_effect = accept
        try:
            sender.start()
            assert reached.wait(5), "Sender did not reach SMTP"
            with app.test_client() as client:
                response = client.patch(
                    "/api/sending-profile", headers=headers, json={"from_name": "Changed display"},
                )
                assert response.status_code == 200
        finally:
            release.set()
            sender.join(5)
        assert not sender.is_alive()

    assert outcomes["send"].status_code == 200
    smtp.login.assert_called_once_with("simulation@gmail.com", "abcdefghijklmnop")
    assert [message[0] for message in messages] == [
        "Simulation Admin <simulation@gmail.com>", "Simulation Admin <simulation@gmail.com>"
    ]
