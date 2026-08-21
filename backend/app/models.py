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

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "name": self.name,
            "email": self.email,
            "department": self.department,
            "role": self.role,
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

    template = db.relationship("EmailTemplate", lazy="joined")
    admin = db.relationship("Admin", lazy="joined")

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

