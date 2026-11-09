from app.extensions import db
from app.models import QuizResult, TrainingResult


def create_training_token(client, auth_headers):
    user = client.post(
        "/api/users",
        headers=auth_headers,
        json={"name": "Sam Wong", "email": "sam@example.com"},
    ).get_json()["user"]
    template = client.post(
        "/api/templates",
        headers=auth_headers,
        json={
            "template_name": "Document share",
            "subject": "A document was shared with you",
            "body": "Open the document.",
        },
    ).get_json()["template"]
    campaign = client.post(
        "/api/campaigns",
        headers=auth_headers,
        json={"campaign_name": "Training test", "template_id": template["template_id"]},
    ).get_json()["campaign"]
    assignment = client.post(
        f"/api/campaigns/{campaign['campaign_id']}/recipients",
        headers=auth_headers,
        json={"user_ids": [user["user_id"]]},
    ).get_json()["recipients"][0]
    token = assignment["tracking_url"].rsplit("/", 1)[-1]
    return campaign, token


def test_training_quiz_and_admin_results(client, auth_headers, app):
    campaign, token = create_training_token(client, auth_headers)

    training = client.get(f"/training/{token}")
    assert training.status_code == 200
    assert b"Take the awareness quiz" in training.data
    assert b"Verify through a known channel" in training.data
    assert b"Inspect the link destination" in training.data

    missing_answers = client.post(
        f"/quiz/{token}",
        data={"sender": "a", "urgent": "b", "credentials": "c", "report": "a"},
    )
    assert missing_answers.status_code == 400
    assert b"answer every question" in missing_answers.data
    with app.app_context():
        assert db.session.scalar(db.select(QuizResult)) is None

    submitted = client.post(
        f"/quiz/{token}",
        data={
            "sender": "a",
            "urgent": "b",
            "credentials": "c",
            "report": "a",
            "links": "a",
        },
    )
    assert submitted.status_code == 303
    result_page = client.get(submitted.headers["Location"])
    assert result_page.status_code == 200
    assert b"100%" in result_page.data
    assert b"Training complete" in result_page.data

    training_results = client.get(
        f"/api/campaigns/{campaign['campaign_id']}/training-results",
        headers=auth_headers,
    ).get_json()["results"]
    quiz_results = client.get(
        f"/api/campaigns/{campaign['campaign_id']}/quiz-results",
        headers=auth_headers,
    ).get_json()["results"]
    assert len(training_results) == 1
    assert training_results[0]["completed"] is True
    assert len(quiz_results) == 1
    assert quiz_results[0]["score"] == 5
    assert quiz_results[0]["total_questions"] == 5
    assert quiz_results[0]["percentage"] == 100

    with app.app_context():
        assert db.session.scalar(db.select(TrainingResult)).completed is True
        assert db.session.scalar(db.select(QuizResult)).total_questions == 5


def test_quiz_retry_replaces_previous_result(client, auth_headers):
    campaign, token = create_training_token(client, auth_headers)
    correct = {
        "sender": "a",
        "urgent": "b",
        "credentials": "c",
        "report": "a",
        "links": "a",
    }
    incorrect = {
        "sender": "b",
        "urgent": "a",
        "credentials": "a",
        "report": "b",
        "links": "b",
    }

    assert client.post(f"/quiz/{token}", data=correct).status_code == 303
    assert client.post(f"/quiz/{token}", data=incorrect).status_code == 303

    results = client.get(
        f"/api/campaigns/{campaign['campaign_id']}/quiz-results",
        headers=auth_headers,
    ).get_json()["results"]
    assert len(results) == 1
    assert results[0]["score"] == 0
    assert results[0]["total_questions"] == 5
    assert results[0]["percentage"] == 0


def test_historical_four_question_result_keeps_its_percentage(app):
    with app.app_context():
        result = QuizResult(score=4, total_questions=4)
        assert result.percentage == 100


def test_training_results_are_admin_only(client, auth_headers):
    campaign, _ = create_training_token(client, auth_headers)
    campaign_id = campaign["campaign_id"]
    assert client.get(f"/api/campaigns/{campaign_id}/training-results").status_code == 401
    assert client.get(f"/api/campaigns/{campaign_id}/quiz-results").status_code == 401
