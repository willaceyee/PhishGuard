from app.extensions import db
from app.models import Admin, QuizResult, User
from scripts import seed_evidence


def test_evidence_seed_is_anonymous_and_uses_five_question_results(app, monkeypatch):
    monkeypatch.setattr(seed_evidence, "create_app", lambda: app)

    seed_evidence.seed()

    emails = [
        *db.session.scalars(db.select(Admin.email)).all(),
        *db.session.scalars(db.select(User.email)).all(),
    ]
    results = db.session.scalars(
        db.select(QuizResult).order_by(QuizResult.score)
    ).all()

    assert emails
    assert all(email.endswith("@example.test") for email in emails)
    assert [(result.score, result.total_questions) for result in results] == [
        (4, 5),
        (5, 5),
    ]
