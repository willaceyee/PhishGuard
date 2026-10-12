from contextlib import contextmanager
from threading import Event, Thread, current_thread
from unittest.mock import patch

import pytest
from flask_jwt_extended import create_access_token

from app import create_app
from app import email_delivery
from app.delivery_coordination import DELIVERY_STATE
from app.extensions import db
from app.models import (
    Admin, Campaign, CampaignRecipient, EmailTemplate, SendingProfile, TrackingEvent,
    User, utc_now,
)
from app.sending_profiles import decrypt_app_password, encrypt_app_password
from config import TestConfig as BackendTestConfig


@contextmanager
def observe_queued_change(ready, thread_name="gate-mutation"):
    original_wait = DELIVERY_STATE._condition.wait

    def observe_wait(timeout=None):
        if current_thread().name == thread_name:
            ready.set()
        return original_wait(timeout)

    with patch.object(DELIVERY_STATE._condition, "wait", side_effect=observe_wait):
        yield


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
        template_id = campaign.template_id
    yield app, headers, campaign_id, recipient_ids, template_id
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
    app, headers, _, recipient_ids, template_id = concurrent_gmail
    with app.app_context():
        profile = db.session.scalar(db.select(SendingProfile))
        profile.last_test_succeeded = False
        profile.last_tested_at = None
        db.session.commit()
    testing = Event()
    release_test = Event()
    mutation_ready = Event()
    outcomes = {}

    def pause_login(*args):
        testing.set()
        assert release_test.wait(5), "Connection test was not released"

    def test_connection():
        with app.test_client() as client:
            outcomes["test"] = client.post(
                "/api/sending-profile/test",
                headers=headers,
                json={"recipient_user_id": recipient_ids[0], "template_id": template_id},
            )

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
    with observe_queued_change(mutation_ready, "profile-mutation"), patch("smtplib.SMTP") as smtp_class:
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
    app, headers, campaign_id, recipient_ids, template_id = concurrent_gmail
    reached = Event()
    release = Event()
    outcomes = {}
    accepted = []
    mutation_ready = Event()
    mutation_finished = Event()

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

    def mutate():
        try:
            with app.test_client() as client:
                if change in {"revoked", "revoked_later"}:
                    target = recipient_ids[0 if stage == "login" and change == "revoked" else 1]
                    mutation = client.patch(
                        f"/api/users/{target}", headers=headers,
                        json={"simulation_email_approved": False},
                    )
                elif change == "failed_test":
                    with patch("app.sending_profiles.test_gmail_profile", side_effect=RuntimeError()):
                        mutation = client.post(
                            "/api/sending-profile/test",
                            headers=headers,
                            json={"recipient_user_id": recipient_ids[0], "template_id": template_id},
                        )
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
                outcomes["mutation"] = mutation
        finally:
            mutation_finished.set()
            mutation_ready.set()

    sender = Thread(target=send)
    mutation = Thread(target=mutate, name="gate-mutation")
    with observe_queued_change(mutation_ready), patch("smtplib.SMTP") as smtp_class:
        smtp = smtp_class.return_value.__enter__.return_value
        if stage == "login":
            smtp.login.side_effect = lambda *args: pause()
        smtp.send_message.side_effect = accept
        try:
            sender.start()
            assert reached.wait(5), "Sender did not reach the paused stage"
            mutation.start()
            if stage == "login":
                assert mutation_finished.wait(5), "Mutation did not commit during setup"
            else:
                assert mutation_ready.wait(5), "Mutation did not queue"
                assert not mutation_finished.is_set()
        finally:
            release.set()
            for thread in (sender, mutation):
                if thread.ident is not None:
                    thread.join(5)
        assert not sender.is_alive() and not mutation.is_alive()

    assert outcomes["mutation"].status_code == (503 if change == "failed_test" else 200)
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
    app, headers, campaign_id, _, _ = concurrent_gmail
    reached = Event()
    release = Event()
    messages = []
    outcomes = {}
    mutation_ready = Event()
    mutation_finished = Event()

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

    def mutate():
        with app.test_client() as client:
            outcomes["mutation"] = client.patch(
                "/api/sending-profile", headers=headers, json={"from_name": "Changed display"},
            )
        mutation_finished.set()
        mutation_ready.set()

    sender = Thread(target=send)
    mutation = Thread(target=mutate, name="gate-mutation")
    with observe_queued_change(mutation_ready), patch("smtplib.SMTP") as smtp_class:
        smtp = smtp_class.return_value.__enter__.return_value
        smtp.send_message.side_effect = accept
        try:
            sender.start()
            assert reached.wait(5), "Sender did not reach SMTP"
            mutation.start()
            assert mutation_ready.wait(5), "Metadata mutation did not queue"
            assert not mutation_finished.is_set()
        finally:
            release.set()
            for thread in (sender, mutation):
                if thread.ident is not None:
                    thread.join(5)
        assert not sender.is_alive() and not mutation.is_alive()

    assert outcomes["mutation"].status_code == 200
    assert outcomes["send"].status_code == 200
    smtp.login.assert_called_once_with("simulation@gmail.com", "abcdefghijklmnop")
    assert [message[0] for message in messages] == [
        "Simulation Admin <simulation@gmail.com>", "Simulation Admin <simulation@gmail.com>"
    ]


@pytest.mark.parametrize("change", ["disabled", "revoked"])
def test_gmail_final_gate_through_dispatch_is_atomic_with_mutations(concurrent_gmail, change):
    app, headers, campaign_id, recipient_ids, _ = concurrent_gmail
    with app.app_context():
        campaign = db.session.get(Campaign, campaign_id)
        db.session.add(CampaignRecipient(
            campaign=campaign,
            user=User(name="Third employee", email="employee2@example.com",
                      simulation_email_approved=True),
            tracking_token="concurrent-token-2",
        ))
        db.session.commit()
    building_second = Event()
    release_build = Event()
    mutation_ready = Event()
    mutation_finished = Event()
    outcomes = {}
    dispatched_after_mutation = []
    built = 0
    original_message_for = email_delivery.message_for

    def pause_second_message(*args, **kwargs):
        nonlocal built
        message = original_message_for(*args, **kwargs)
        built += 1
        if built == 2:
            building_second.set()
            assert release_build.wait(5), "Second message construction was not released"
        return message

    def send():
        with app.test_client() as client:
            outcomes["send"] = client.post(
                f"/api/campaigns/{campaign_id}/send", headers=headers,
                json={"confirmation": "SEND 3 REAL EMAILS"},
            )

    def mutate():
        with app.test_client() as client:
            if change == "disabled":
                outcomes["mutation"] = client.patch(
                    "/api/sending-profile", headers=headers, json={"enabled": False},
                )
            else:
                outcomes["mutation"] = client.patch(
                    f"/api/users/{recipient_ids[1]}", headers=headers,
                    json={"simulation_email_approved": False},
                )
        mutation_finished.set()
        mutation_ready.set()

    sender = Thread(target=send, name="gate-sender")
    mutation = Thread(target=mutate, name="gate-mutation")
    with observe_queued_change(mutation_ready), patch("app.email_delivery.message_for", side_effect=pause_second_message), patch(
        "smtplib.SMTP"
    ) as smtp_class:
        smtp_class.return_value.__enter__.return_value.send_message.side_effect = (
            lambda *args, **kwargs: dispatched_after_mutation.append(mutation_finished.is_set())
        )
        try:
            sender.start()
            assert building_second.wait(5), "Sender did not reach the final-check/dispatch gap"
            mutation.start()
            assert mutation_ready.wait(5), "Mutation did not queue or finish"
            assert not mutation_finished.is_set(), "Mutation committed before authorized dispatch finished"
        finally:
            release_build.set()
            for thread in (sender, mutation):
                if thread.ident is not None:
                    thread.join(5)
        assert not sender.is_alive() and not mutation.is_alive()

    assert outcomes["mutation"].status_code == 200
    assert outcomes["send"].status_code == (400 if change == "disabled" else 403)
    assert dispatched_after_mutation == [False, False]
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(TrackingEvent.event_id))) == 2
