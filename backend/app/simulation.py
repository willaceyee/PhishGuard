import secrets

from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models import Campaign, CampaignRecipient, TrackingEvent, User


simulation = Blueprint("simulation", __name__)


@simulation.after_request
def disable_sensitive_page_caching(response):
    if request.path.startswith(("/track/", "/simulation/", "/training/")):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
    return response


def recipient_for_token(token):
    return db.session.scalar(
        db.select(CampaignRecipient).where(CampaignRecipient.tracking_token == token)
    )


def record_event(recipient, event_type):
    event = TrackingEvent(recipient=recipient, event_type=event_type)
    db.session.add(event)
    db.session.commit()
    return event


@simulation.post("/api/campaigns/<int:campaign_id>/recipients")
@jwt_required()
def add_campaign_recipients(campaign_id):
    campaign = db.get_or_404(Campaign, campaign_id)
    data = request.get_json(silent=True) or {}
    user_ids = data.get("user_ids")
    if not isinstance(user_ids, list) or not user_ids:
        return jsonify(error="user_ids must be a non-empty list"), 400
    if any(not isinstance(user_id, int) for user_id in user_ids):
        return jsonify(error="Every user_id must be numeric"), 400

    unique_ids = list(dict.fromkeys(user_ids))
    users = db.session.scalars(db.select(User).where(User.user_id.in_(unique_ids))).all()
    users_by_id = {user.user_id: user for user in users}
    missing_ids = [user_id for user_id in unique_ids if user_id not in users_by_id]
    if missing_ids:
        return jsonify(error="Some users were not found", missing_user_ids=missing_ids), 404

    existing_ids = set(
        db.session.scalars(
            db.select(CampaignRecipient.user_id).where(
                CampaignRecipient.campaign_id == campaign_id,
                CampaignRecipient.user_id.in_(unique_ids),
            )
        ).all()
    )
    created = []
    for user_id in unique_ids:
        if user_id in existing_ids:
            continue
        recipient = CampaignRecipient(
            campaign=campaign,
            user=users_by_id[user_id],
            tracking_token=secrets.token_urlsafe(32),
        )
        db.session.add(recipient)
        created.append(recipient)
    db.session.commit()

    return (
        jsonify(
            recipients=[
                {
                    **recipient.to_dict(),
                    "tracking_url": url_for(
                        "simulation.track_link",
                        token=recipient.tracking_token,
                        _external=True,
                    ),
                }
                for recipient in created
            ],
            skipped_existing=len(existing_ids),
        ),
        201,
    )


@simulation.get("/api/campaigns/<int:campaign_id>/recipients")
@jwt_required()
def list_campaign_recipients(campaign_id):
    db.get_or_404(Campaign, campaign_id)
    recipients = db.session.scalars(
        db.select(CampaignRecipient)
        .where(CampaignRecipient.campaign_id == campaign_id)
        .order_by(CampaignRecipient.created_at)
    ).all()
    return jsonify(
        recipients=[
            {
                **recipient.to_dict(),
                "tracking_url": url_for(
                    "simulation.track_link",
                    token=recipient.tracking_token,
                    _external=True,
                ),
            }
            for recipient in recipients
        ]
    )


@simulation.get("/api/campaigns/<int:campaign_id>/events")
@jwt_required()
def list_campaign_events(campaign_id):
    db.get_or_404(Campaign, campaign_id)
    events = db.session.scalars(
        db.select(TrackingEvent)
        .join(CampaignRecipient)
        .where(CampaignRecipient.campaign_id == campaign_id)
        .order_by(TrackingEvent.occurred_at.desc())
    ).all()
    return jsonify(events=[event.to_dict() for event in events])


@simulation.get("/track/<token>")
def track_link(token):
    recipient = recipient_for_token(token)
    if recipient is None:
        return render_template("simulation_expired.html"), 404
    record_event(recipient, "link_clicked")
    return redirect(url_for("simulation.landing_page", token=token))


@simulation.get("/simulation/<token>")
def landing_page(token):
    recipient = recipient_for_token(token)
    if recipient is None:
        return render_template("simulation_expired.html"), 404
    record_event(recipient, "landing_viewed")
    return render_template("simulation_landing.html", token=token)


@simulation.post("/simulation/<token>/submit")
def simulated_submit(token):
    recipient = recipient_for_token(token)
    if recipient is None:
        return render_template("simulation_expired.html"), 404

    # Deliberately do not inspect or retain any submitted field values.
    record_event(recipient, "form_submitted")
    return redirect(url_for("simulation.training_page", token=token))


@simulation.get("/training/<token>")
def training_page(token):
    recipient = recipient_for_token(token)
    if recipient is None:
        return render_template("simulation_expired.html"), 404
    record_event(recipient, "training_viewed")
    return render_template(
        "simulation_training.html",
        user_name=recipient.user.name,
        campaign_name=recipient.campaign.campaign_name,
    )
