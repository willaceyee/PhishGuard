"""Seed an empty disposable database with anonymous final-report evidence data."""

import secrets

from app import create_app
from app.extensions import db
from app.models import (
    Admin,
    Campaign,
    CampaignRecipient,
    EmailTemplate,
    QuizResult,
    TrackingEvent,
    TrainingResult,
    User,
    utc_now,
)


DEMO_EMAIL = "evidence.admin@example.test"
DEMO_PASSWORD = "Evidence-Only-Password-2026"


def seed():
    app = create_app()
    with app.app_context():
        db.create_all()
        if db.session.scalar(db.select(Admin.admin_id).limit(1)) is not None:
            raise RuntimeError("Evidence seeding requires an empty database")

        admin = Admin(name="Evidence Admin", email=DEMO_EMAIL)
        admin.set_password(DEMO_PASSWORD)
        template = EmailTemplate(
            template_name="Anonymous evidence template",
            subject="Account review required",
            body="Review your account through the supplied link.",
            category="awareness",
        )
        users = [
            User(name="Alex Morgan", email="alex@example.test", department="Finance"),
            User(name="Priya Shah", email="priya@example.test", department="Operations"),
            User(name="Jordan Lee", email="jordan@example.test", department="Technology"),
        ]
        db.session.add_all([admin, template, *users])
        db.session.flush()

        campaign = Campaign(
            campaign_name="Quarterly awareness exercise",
            template=template,
            admin=admin,
            status="completed",
        )
        db.session.add(campaign)
        db.session.flush()

        recipients = [
            CampaignRecipient(
                campaign=campaign,
                user=user,
                tracking_token=secrets.token_urlsafe(32),
            )
            for user in users
        ]
        db.session.add_all(recipients)
        db.session.flush()

        db.session.add_all(
            [
                TrackingEvent(recipient=recipients[0], event_type="link_clicked"),
                TrackingEvent(recipient=recipients[0], event_type="form_submitted"),
                TrackingEvent(recipient=recipients[0], event_type="training_viewed"),
                TrackingEvent(recipient=recipients[0], event_type="quiz_completed"),
                TrainingResult(
                    recipient=recipients[0], completed=True, completed_at=utc_now()
                ),
                QuizResult(
                    recipient=recipients[0],
                    score=4,
                    total_questions=5,
                    completed_at=utc_now(),
                ),
                TrackingEvent(recipient=recipients[1], event_type="link_clicked"),
                TrainingResult(recipient=recipients[1], completed=False),
                TrainingResult(
                    recipient=recipients[2], completed=True, completed_at=utc_now()
                ),
                QuizResult(
                    recipient=recipients[2],
                    score=5,
                    total_questions=5,
                    completed_at=utc_now(),
                ),
            ]
        )
        db.session.commit()

    print(f"Evidence database seeded. Login: {DEMO_EMAIL} / {DEMO_PASSWORD}")


if __name__ == "__main__":
    seed()
