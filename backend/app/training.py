from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models import (
    Campaign,
    CampaignRecipient,
    QuizResult,
    TrackingEvent,
    TrainingResult,
    utc_now,
)
from app.simulation import recipient_for_token, record_event


training = Blueprint("training", __name__)


QUIZ_QUESTIONS = (
    {
        "id": "sender",
        "prompt": "What should you check first in an unexpected account-warning email?",
        "choices": (
            ("a", "The sender address and destination URL"),
            ("b", "Whether the message uses a company logo"),
            ("c", "Whether the email looks urgent"),
        ),
        "correct": "a",
        "explanation": "Display names and logos can be copied, so inspect the real sender and link destination.",
    },
    {
        "id": "urgent",
        "prompt": "An email threatens immediate account closure. What is the safest response?",
        "choices": (
            ("a", "Reply and ask whether the warning is genuine"),
            ("b", "Open the official service directly and verify there"),
            ("c", "Click quickly before the deadline expires"),
        ),
        "correct": "b",
        "explanation": "Use a known official route instead of links or contact details in the suspicious message.",
    },
    {
        "id": "credentials",
        "prompt": "A linked page unexpectedly asks for your password. What should you do?",
        "choices": (
            ("a", "Enter it if the page has a padlock icon"),
            ("b", "Enter it, then change the password later"),
            ("c", "Stop, close the page, and report the message"),
        ),
        "correct": "c",
        "explanation": "HTTPS alone does not prove a page is trustworthy. Stop and report the suspicious request.",
    },
    {
        "id": "report",
        "prompt": "Why should a suspicious email be reported even if you did not click?",
        "choices": (
            ("a", "It helps the organization protect other recipients"),
            ("b", "It automatically deletes every copy of the email"),
            ("c", "It guarantees the sender will be arrested"),
        ),
        "correct": "a",
        "explanation": "Early reports help security teams investigate and warn or protect other users.",
    },
    {
        "id": "links",
        "prompt": "Before opening a link in an unexpected email, what should you do?",
        "choices": (
            ("a", "Inspect the real destination and use a trusted route to the service"),
            ("b", "Trust it whenever the address begins with HTTPS"),
            ("c", "Open it if the message uses a familiar logo"),
        ),
        "correct": "a",
        "explanation": "Inspect the destination first and use a known bookmark or official application when possible.",
    },
)


@training.after_request
def disable_training_page_caching(response):
    if request.path.startswith(("/training/", "/quiz/")):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
    return response


@training.get("/training/<token>")
def training_page(token):
    recipient = recipient_for_token(token)
    if recipient is None:
        return render_template("simulation_expired.html"), 404

    result = recipient.training_result
    if result is None:
        result = TrainingResult(recipient=recipient)
        db.session.add(result)
    record_event(recipient, "training_viewed")
    return render_template(
        "simulation_training.html",
        token=token,
        user_name=recipient.user.name,
        campaign_name=recipient.campaign.campaign_name,
        completed=result.completed,
    )


@training.get("/quiz/<token>")
def quiz_page(token):
    recipient = recipient_for_token(token)
    if recipient is None:
        return render_template("simulation_expired.html"), 404
    return render_template(
        "training_quiz.html",
        token=token,
        questions=QUIZ_QUESTIONS,
        previous_result=recipient.quiz_result,
    )


@training.post("/quiz/<token>")
def submit_quiz(token):
    recipient = recipient_for_token(token)
    if recipient is None:
        return render_template("simulation_expired.html"), 404

    submitted_answers = {question["id"]: request.form.get(question["id"]) for question in QUIZ_QUESTIONS}
    valid_answers = {
        question["id"]: {choice[0] for choice in question["choices"]}
        for question in QUIZ_QUESTIONS
    }
    if any(submitted_answers[key] not in valid_answers[key] for key in valid_answers):
        return (
            render_template(
                "training_quiz.html",
                token=token,
                questions=QUIZ_QUESTIONS,
                previous_result=recipient.quiz_result,
                error="Please answer every question before submitting.",
            ),
            400,
        )

    score = sum(
        submitted_answers[question["id"]] == question["correct"]
        for question in QUIZ_QUESTIONS
    )
    quiz_result = recipient.quiz_result
    if quiz_result is None:
        quiz_result = QuizResult(recipient=recipient, score=score, total_questions=len(QUIZ_QUESTIONS))
        db.session.add(quiz_result)
    else:
        quiz_result.score = score
        quiz_result.total_questions = len(QUIZ_QUESTIONS)
        quiz_result.completed_at = utc_now()

    training_result = recipient.training_result
    if training_result is None:
        training_result = TrainingResult(recipient=recipient)
        db.session.add(training_result)
    training_result.completed = True
    training_result.completed_at = utc_now()
    event = TrackingEvent(recipient=recipient, event_type="quiz_completed")
    db.session.add(event)
    db.session.commit()
    return redirect(url_for("training.quiz_result_page", token=token), code=303)


@training.get("/quiz/<token>/result")
def quiz_result_page(token):
    recipient = recipient_for_token(token)
    if recipient is None:
        return render_template("simulation_expired.html"), 404
    if recipient.quiz_result is None:
        return redirect(url_for("training.quiz_page", token=token))
    return render_template(
        "training_quiz_result.html",
        result=recipient.quiz_result,
        questions=QUIZ_QUESTIONS,
    )


@training.get("/api/campaigns/<int:campaign_id>/training-results")
@jwt_required()
def campaign_training_results(campaign_id):
    db.get_or_404(Campaign, campaign_id)
    results = db.session.scalars(
        db.select(TrainingResult)
        .join(CampaignRecipient)
        .where(CampaignRecipient.campaign_id == campaign_id)
        .order_by(TrainingResult.created_at.desc())
    ).all()
    return jsonify(results=[result.to_dict() for result in results])


@training.get("/api/campaigns/<int:campaign_id>/quiz-results")
@jwt_required()
def campaign_quiz_results(campaign_id):
    db.get_or_404(Campaign, campaign_id)
    results = db.session.scalars(
        db.select(QuizResult)
        .join(CampaignRecipient)
        .where(CampaignRecipient.campaign_id == campaign_id)
        .order_by(QuizResult.completed_at.desc())
    ).all()
    return jsonify(results=[result.to_dict() for result in results])
