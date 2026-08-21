from collections import defaultdict

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models import Campaign, CampaignRecipient, User


analytics = Blueprint("analytics", __name__, url_prefix="/api/dashboard")


def percentage(numerator, denominator):
    return round((numerator / denominator) * 100, 1) if denominator else 0.0


def recipient_event_types(recipient):
    return {event.event_type for event in recipient.events}


def recipient_risk(recipient):
    event_types = recipient_event_types(recipient)
    clicked = "link_clicked" in event_types
    submitted = "form_submitted" in event_types
    training_completed = bool(
        recipient.training_result and recipient.training_result.completed
    )
    quiz_percentage = (
        recipient.quiz_result.percentage if recipient.quiz_result is not None else None
    )

    factors = [
        {
            "factor": "Clicked simulation link",
            "points": 25 if clicked else 0,
            "triggered": clicked,
        },
        {
            "factor": "Submitted simulated form",
            "points": 45 if submitted else 0,
            "triggered": submitted,
        },
        {
            "factor": "Training incomplete",
            "points": 20 if not training_completed else 0,
            "triggered": not training_completed,
        },
        {
            "factor": "Quiz knowledge gap",
            "points": 10 if quiz_percentage is None else round((100 - quiz_percentage) * 0.1),
            "triggered": quiz_percentage is None or quiz_percentage < 100,
        },
    ]
    score = min(sum(factor["points"] for factor in factors), 100)
    band = "high" if score >= 60 else "medium" if score >= 30 else "low"
    return {
        "score": score,
        "band": band,
        "clicked": clicked,
        "submitted": submitted,
        "training_completed": training_completed,
        "quiz_percentage": quiz_percentage,
        "factors": factors,
    }


def campaign_metrics(campaign):
    recipients = campaign.recipients
    recipient_count = len(recipients)
    clicked = 0
    submitted = 0
    training_started = 0
    training_completed = 0
    quiz_percentages = []

    for recipient in recipients:
        events = recipient_event_types(recipient)
        clicked += "link_clicked" in events
        submitted += "form_submitted" in events
        training_started += recipient.training_result is not None
        training_completed += bool(
            recipient.training_result and recipient.training_result.completed
        )
        if recipient.quiz_result is not None:
            quiz_percentages.append(recipient.quiz_result.percentage)

    return {
        "campaign_id": campaign.campaign_id,
        "campaign_name": campaign.campaign_name,
        "status": campaign.status,
        "recipient_count": recipient_count,
        "unique_clicked": clicked,
        "unique_submitted": submitted,
        "click_through_rate": percentage(clicked, recipient_count),
        "submission_rate": percentage(submitted, recipient_count),
        "training_started": training_started,
        "training_completed": training_completed,
        "training_completion_rate": percentage(training_completed, recipient_count),
        "quiz_responses": len(quiz_percentages),
        "average_quiz_percentage": (
            round(sum(quiz_percentages) / len(quiz_percentages), 1)
            if quiz_percentages
            else None
        ),
    }


def aggregate_user_risks(recipients):
    by_user = defaultdict(list)
    for recipient in recipients:
        by_user[recipient.user_id].append(recipient_risk(recipient))

    users = db.session.scalars(
        db.select(User).where(User.user_id.in_(by_user.keys()))
    ).all() if by_user else []
    results = []
    for user in users:
        assessments = by_user[user.user_id]
        score = round(sum(item["score"] for item in assessments) / len(assessments))
        band = "high" if score >= 60 else "medium" if score >= 30 else "low"
        results.append(
            {
                "user_id": user.user_id,
                "name": user.name,
                "email": user.email,
                "department": user.department,
                "risk_score": score,
                "risk_band": band,
                "campaigns_assessed": len(assessments),
                "clicked_campaigns": sum(item["clicked"] for item in assessments),
                "submitted_campaigns": sum(item["submitted"] for item in assessments),
                "completed_training": sum(
                    item["training_completed"] for item in assessments
                ),
                "average_quiz_percentage": (
                    round(
                        sum(
                            item["quiz_percentage"]
                            for item in assessments
                            if item["quiz_percentage"] is not None
                        )
                        / sum(item["quiz_percentage"] is not None for item in assessments),
                        1,
                    )
                    if any(item["quiz_percentage"] is not None for item in assessments)
                    else None
                ),
            }
        )
    return sorted(results, key=lambda item: (-item["risk_score"], item["name"].lower()))


@analytics.get("/overview")
@jwt_required()
def overview():
    campaigns = db.session.scalars(
        db.select(Campaign).order_by(Campaign.created_at.desc())
    ).unique().all()
    recipients = db.session.scalars(db.select(CampaignRecipient)).all()
    campaign_rows = [campaign_metrics(campaign) for campaign in campaigns]

    total_recipients = len(recipients)
    clicked = sum("link_clicked" in recipient_event_types(item) for item in recipients)
    submitted = sum("form_submitted" in recipient_event_types(item) for item in recipients)
    completed = sum(
        bool(item.training_result and item.training_result.completed) for item in recipients
    )
    quiz_scores = [
        item.quiz_result.percentage for item in recipients if item.quiz_result is not None
    ]
    user_risks = aggregate_user_risks(recipients)

    return jsonify(
        summary={
            "total_campaigns": len(campaigns),
            "total_users": db.session.scalar(db.select(db.func.count(User.user_id))),
            "total_recipients": total_recipients,
            "unique_clicked": clicked,
            "unique_submitted": submitted,
            "click_through_rate": percentage(clicked, total_recipients),
            "submission_rate": percentage(submitted, total_recipients),
            "training_completed": completed,
            "training_completion_rate": percentage(completed, total_recipients),
            "average_quiz_percentage": (
                round(sum(quiz_scores) / len(quiz_scores), 1) if quiz_scores else None
            ),
            "high_risk_users": sum(item["risk_band"] == "high" for item in user_risks),
        },
        campaigns=campaign_rows,
        user_risks=user_risks,
        risk_method={
            "high_threshold": 60,
            "medium_threshold": 30,
            "weights": {
                "clicked": 25,
                "submitted": 45,
                "training_incomplete": 20,
                "quiz_gap_maximum": 10,
            },
        },
    )
