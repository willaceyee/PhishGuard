from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


def utc_now():
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)


class Admin(TimestampMixin, db.Model):
    __tablename__ = "admins"

    admin_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "admin_id": self.admin_id,
            "name": self.name,
            "email": self.email,
            "created_at": self.created_at.isoformat(),
        }


class User(TimestampMixin, db.Model):
    __tablename__ = "users"

    user_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    department = db.Column(db.String(120))
    role = db.Column(db.String(80), default="employee", nullable=False)
    simulation_email_approved = db.Column(db.Boolean, default=False, nullable=False)

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "name": self.name,
            "email": self.email,
            "department": self.department,
            "role": self.role,
            "simulation_email_approved": self.simulation_email_approved,
            "created_at": self.created_at.isoformat(),
        }


class EmailTemplate(TimestampMixin, db.Model):
    __tablename__ = "email_templates"

    template_id = db.Column(db.Integer, primary_key=True)
    template_name = db.Column(db.String(160), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(100))

    def to_dict(self):
        return {
            "template_id": self.template_id,
            "template_name": self.template_name,
            "subject": self.subject,
            "body": self.body,
            "category": self.category,
            "created_at": self.created_at.isoformat(),
        }


class SendingProfile(TimestampMixin, db.Model):
    __tablename__ = "sending_profiles"
    __table_args__ = (
        db.UniqueConstraint("provider", name="uq_sending_profile_provider"),
        db.CheckConstraint("provider = 'gmail'", name="ck_sending_profile_gmail"),
    )

    profile_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    provider = db.Column(db.String(40), default="gmail", nullable=False)
    from_name = db.Column(db.String(120), nullable=False)
    from_email = db.Column(db.String(255), nullable=False)
    encrypted_app_password = db.Column(db.Text)
    enabled = db.Column(db.Boolean, default=False, nullable=False)
    last_tested_at = db.Column(db.DateTime(timezone=True))
    last_test_succeeded = db.Column(db.Boolean, default=False, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    def to_safe_dict(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "name": self.name,
            "provider": self.provider,
            "from_name": self.from_name,
            "from_email": self.from_email,
            "credential_configured": bool(self.encrypted_app_password),
            "enabled": self.enabled,
            "last_tested_at": (
                self.last_tested_at.isoformat() if self.last_tested_at else None
            ),
            "last_test_succeeded": self.last_test_succeeded,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class Campaign(TimestampMixin, db.Model):
    __tablename__ = "campaigns"

    campaign_id = db.Column(db.Integer, primary_key=True)
    campaign_name = db.Column(db.String(160), nullable=False)
    template_id = db.Column(
        db.Integer, db.ForeignKey("email_templates.template_id"), nullable=False
    )
    created_by = db.Column(db.Integer, db.ForeignKey("admins.admin_id"), nullable=False)
    scheduled_date = db.Column(db.DateTime(timezone=True))
    status = db.Column(db.String(40), default="draft", nullable=False)
    sending_profile_id = db.Column(
        db.Integer, db.ForeignKey("sending_profiles.profile_id")
    )

    template = db.relationship("EmailTemplate", lazy="joined")
    admin = db.relationship("Admin", lazy="joined")
    sending_profile = db.relationship("SendingProfile")
    recipients = db.relationship(
        "CampaignRecipient", back_populates="campaign", cascade="all, delete-orphan"
    )

    def to_dict(self):
        return {
            "campaign_id": self.campaign_id,
            "campaign_name": self.campaign_name,
            "template_id": self.template_id,
            "created_by": self.created_by,
            "scheduled_date": (
                self.scheduled_date.isoformat() if self.scheduled_date else None
            ),
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }


class CampaignRecipient(TimestampMixin, db.Model):
    __tablename__ = "campaign_recipients"
    __table_args__ = (
        db.UniqueConstraint("campaign_id", "user_id", name="uq_campaign_recipient"),
    )

    recipient_id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(
        db.Integer, db.ForeignKey("campaigns.campaign_id"), nullable=False, index=True
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.user_id"), nullable=False, index=True
    )
    tracking_token = db.Column(db.String(128), unique=True, nullable=False, index=True)

    campaign = db.relationship("Campaign", back_populates="recipients")
    user = db.relationship("User", lazy="joined")
    events = db.relationship(
        "TrackingEvent", back_populates="recipient", cascade="all, delete-orphan"
    )
    training_result = db.relationship(
        "TrainingResult",
        back_populates="recipient",
        cascade="all, delete-orphan",
        uselist=False,
    )
    quiz_result = db.relationship(
        "QuizResult",
        back_populates="recipient",
        cascade="all, delete-orphan",
        uselist=False,
    )

    def to_dict(self, include_token=False):
        data = {
            "recipient_id": self.recipient_id,
            "campaign_id": self.campaign_id,
            "user": self.user.to_dict(),
            "created_at": self.created_at.isoformat(),
        }
        if include_token:
            data["tracking_token"] = self.tracking_token
        return data


class TrackingEvent(db.Model):
    __tablename__ = "tracking_events"

    event_id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(
        db.Integer,
        db.ForeignKey("campaign_recipients.recipient_id"),
        nullable=False,
        index=True,
    )
    event_type = db.Column(db.String(40), nullable=False, index=True)
    delivery_channel = db.Column(db.String(40))
    occurred_at = db.Column(
        db.DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    recipient = db.relationship("CampaignRecipient", back_populates="events")

    def to_dict(self):
        return {
            "event_id": self.event_id,
            "recipient_id": self.recipient_id,
            "campaign_id": self.recipient.campaign_id,
            "user_id": self.recipient.user_id,
            "event_type": self.event_type,
            "delivery_channel": self.delivery_channel,
            "occurred_at": self.occurred_at.isoformat(),
        }


class TrainingResult(TimestampMixin, db.Model):
    __tablename__ = "training_results"

    training_id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(
        db.Integer,
        db.ForeignKey("campaign_recipients.recipient_id"),
        unique=True,
        nullable=False,
        index=True,
    )
    completed = db.Column(db.Boolean, default=False, nullable=False)
    completed_at = db.Column(db.DateTime(timezone=True))

    recipient = db.relationship("CampaignRecipient", back_populates="training_result")

    def to_dict(self):
        return {
            "training_id": self.training_id,
            "recipient_id": self.recipient_id,
            "campaign_id": self.recipient.campaign_id,
            "user_id": self.recipient.user_id,
            "completed": self.completed,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "started_at": self.created_at.isoformat(),
        }


class QuizResult(TimestampMixin, db.Model):
    __tablename__ = "quiz_results"

    quiz_id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(
        db.Integer,
        db.ForeignKey("campaign_recipients.recipient_id"),
        unique=True,
        nullable=False,
        index=True,
    )
    score = db.Column(db.Integer, nullable=False)
    total_questions = db.Column(db.Integer, nullable=False)
    completed_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    recipient = db.relationship("CampaignRecipient", back_populates="quiz_result")

    @property
    def percentage(self):
        return round((self.score / self.total_questions) * 100) if self.total_questions else 0

    def to_dict(self):
        return {
            "quiz_id": self.quiz_id,
            "recipient_id": self.recipient_id,
            "campaign_id": self.recipient.campaign_id,
            "user_id": self.recipient.user_id,
            "score": self.score,
            "total_questions": self.total_questions,
            "percentage": self.percentage,
            "completed_at": self.completed_at.isoformat(),
        }
