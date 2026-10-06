from datetime import datetime

from flask import Blueprint, abort, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.extensions import db
from app.models import Campaign, CampaignRecipient, EmailTemplate, SendingProfile, User


main = Blueprint("main", __name__)
api = Blueprint("api", __name__, url_prefix="/api")


def payload():
    return request.get_json(silent=True) or {}


def required_text(data, field):
    value = data.get(field)
    return value.strip() if isinstance(value, str) else ""


def resolve_sending_profile(profile_id):
    if profile_id is None:
        return None
    if type(profile_id) is not int:
        abort(400, description="sending_profile_id must be an integer or null")
    profile = db.session.scalar(db.select(SendingProfile))
    if profile is None or profile.profile_id != profile_id:
        abort(404, description="Sending profile not found")
    return profile


@main.get("/")
def home():
    return jsonify(message="PhishGuard backend is running")


@main.get("/api/health")
def health():
    return jsonify(message="PhishGuard backend is running", status="healthy")


@api.get("/users")
@jwt_required()
def list_users():
    users = db.session.scalars(db.select(User).order_by(User.created_at.desc())).all()
    return jsonify(users=[user.to_dict() for user in users])


@api.post("/users")
@jwt_required()
def create_user():
    data = payload()
    name = required_text(data, "name")
    email = required_text(data, "email").lower()
    if not name or not email:
        return jsonify(error="Name and email are required"), 400
    if db.session.scalar(db.select(User).where(User.email == email)):
        return jsonify(error="A user with this email already exists"), 409
    user = User(
        name=name,
        email=email,
        department=required_text(data, "department") or None,
        role=required_text(data, "role") or "employee",
    )
    db.session.add(user)
    db.session.commit()
    return jsonify(user=user.to_dict()), 201


@api.patch("/users/<int:user_id>")
@jwt_required()
def update_user(user_id):
    user = db.get_or_404(User, user_id)
    data = payload()
    for field in ("name", "department", "role"):
        if field in data:
            setattr(user, field, required_text(data, field) or None)
    if "email" in data:
        email = required_text(data, "email").lower()
        if not email:
            return jsonify(error="Email cannot be empty"), 400
        duplicate = db.session.scalar(
            db.select(User).where(User.email == email, User.user_id != user_id)
        )
        if duplicate:
            return jsonify(error="A user with this email already exists"), 409
        user.email = email
    if "simulation_email_approved" in data:
        approved = data["simulation_email_approved"]
        if not isinstance(approved, bool):
            return jsonify(error="simulation_email_approved must be true or false"), 400
        user.simulation_email_approved = approved
    if not user.name or not user.role:
        return jsonify(error="Name and role cannot be empty"), 400
    db.session.commit()
    return jsonify(user=user.to_dict())


@api.delete("/users/<int:user_id>")
@jwt_required()
def delete_user(user_id):
    user = db.get_or_404(User, user_id)
    if db.session.scalar(
        db.select(CampaignRecipient.recipient_id)
        .where(CampaignRecipient.user_id == user_id)
        .limit(1)
    ):
        return jsonify(error="User is assigned to a campaign"), 409
    db.session.delete(user)
    db.session.commit()
    return "", 204


@api.get("/templates")
@jwt_required()
def list_templates():
    templates = db.session.scalars(
        db.select(EmailTemplate).order_by(EmailTemplate.created_at.desc())
    ).all()
    return jsonify(templates=[template.to_dict() for template in templates])


@api.post("/templates")
@jwt_required()
def create_template():
    data = payload()
    template_name = required_text(data, "template_name")
    subject = required_text(data, "subject")
    body = required_text(data, "body")
    if not template_name or not subject or not body:
        return jsonify(error="Template name, subject, and body are required"), 400
    template = EmailTemplate(
        template_name=template_name,
        subject=subject,
        body=body,
        category=required_text(data, "category") or None,
    )
    db.session.add(template)
    db.session.commit()
    return jsonify(template=template.to_dict()), 201


@api.patch("/templates/<int:template_id>")
@jwt_required()
def update_template(template_id):
    template = db.get_or_404(EmailTemplate, template_id)
    data = payload()
    updates = {}
    for field in ("template_name", "subject", "body", "category"):
        if field in data:
            value = required_text(data, field)
            if field in {"template_name", "subject", "body"} and not value:
                return jsonify(error="Template name, subject, and body cannot be empty"), 400
            updates[field] = value or None
    for field, value in updates.items():
        setattr(template, field, value)
    db.session.commit()
    return jsonify(template=template.to_dict())


@api.delete("/templates/<int:template_id>")
@jwt_required()
def delete_template(template_id):
    template = db.get_or_404(EmailTemplate, template_id)
    if db.session.scalar(
        db.select(Campaign.campaign_id).where(Campaign.template_id == template_id).limit(1)
    ):
        return jsonify(error="Template is used by a campaign"), 409
    db.session.delete(template)
    db.session.commit()
    return "", 204


@api.get("/campaigns")
@jwt_required()
def list_campaigns():
    campaigns = db.session.scalars(
        db.select(Campaign).order_by(Campaign.created_at.desc())
    ).all()
    return jsonify(campaigns=[campaign.to_dict() for campaign in campaigns])


@api.post("/campaigns")
@jwt_required()
def create_campaign():
    data = payload()
    campaign_name = required_text(data, "campaign_name")
    template_id = data.get("template_id")
    if not campaign_name or not isinstance(template_id, int):
        return jsonify(error="Campaign name and numeric template_id are required"), 400
    if db.session.get(EmailTemplate, template_id) is None:
        return jsonify(error="Email template not found"), 404
    sending_profile = resolve_sending_profile(data.get("sending_profile_id"))
    scheduled_date = None
    if data.get("scheduled_date"):
        try:
            scheduled_date = datetime.fromisoformat(str(data["scheduled_date"]).replace("Z", "+00:00"))
        except ValueError:
            return jsonify(error="scheduled_date must be ISO 8601"), 400
    campaign = Campaign(
        campaign_name=campaign_name,
        template_id=template_id,
        created_by=int(get_jwt_identity()),
        scheduled_date=scheduled_date,
        status=required_text(data, "status") or "draft",
        sending_profile=sending_profile,
    )
    db.session.add(campaign)
    db.session.commit()
    return jsonify(campaign=campaign.to_dict()), 201


@api.patch("/campaigns/<int:campaign_id>")
@jwt_required()
def update_campaign(campaign_id):
    campaign = db.get_or_404(Campaign, campaign_id)
    data = payload()
    if "sending_profile_id" in data:
        campaign.sending_profile = resolve_sending_profile(data["sending_profile_id"])
    if "campaign_name" in data:
        campaign.campaign_name = required_text(data, "campaign_name")
    if "status" in data:
        campaign.status = required_text(data, "status")
    if "template_id" in data:
        if not isinstance(data["template_id"], int):
            return jsonify(error="template_id must be numeric"), 400
        if db.session.get(EmailTemplate, data["template_id"]) is None:
            return jsonify(error="Email template not found"), 404
        campaign.template_id = data["template_id"]
    if not campaign.campaign_name or not campaign.status:
        return jsonify(error="Campaign name and status cannot be empty"), 400
    db.session.commit()
    return jsonify(campaign=campaign.to_dict())


@api.delete("/campaigns/<int:campaign_id>")
@jwt_required()
def delete_campaign(campaign_id):
    campaign = db.get_or_404(Campaign, campaign_id)
    db.session.delete(campaign)
    db.session.commit()
    return "", 204
