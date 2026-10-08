import ipaddress
import re
import smtplib
import ssl
from contextlib import nullcontext
from datetime import timedelta
from email.errors import HeaderParseError
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import formataddr
from threading import Lock
from urllib.parse import urlparse

from cryptography.fernet import InvalidToken
from flask import current_app

from app.extensions import db
from app.delivery_coordination import DELIVERY_STATE
from app.models import CampaignRecipient, SendingProfile, TrackingEvent, utc_now
from app.sending_profiles import decrypt_app_password


SIMULATION_PREFIX = "[SECURITY SIMULATION]"
LINK_PLACEHOLDER = "[INSERT CAMPAIGN TRACKING LINK]"
GMAIL_SEND_LOCK = Lock()


class DeliveryApprovalChanged(PermissionError):
    pass


def tracking_url(recipient):
    return (
        f"{current_app.config['PUBLIC_BASE_URL']}"
        f"/track/{recipient.tracking_token}"
    )


def public_url_is_safe():
    parsed = urlparse(current_app.config["PUBLIC_BASE_URL"])
    if parsed.scheme == "https":
        return True
    return parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}


def public_gmail_url_is_safe():
    try:
        parsed = urlparse(current_app.config["PUBLIC_BASE_URL"])
        hostname = (
            (parsed.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
        )
        parsed.port  # urlparse validates malformed/out-of-range ports lazily.
    except (ValueError, UnicodeError):
        return False
    if parsed.scheme != "https" or not hostname or parsed.netloc.endswith(":"):
        return False
    if (
        hostname == "localhost" or hostname.endswith((".localhost", ".local"))
        or "%" in hostname or "\\" in parsed.netloc
    ):
        return False
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        # Browsers interpret a final numeric label as IPv4, including short,
        # octal, and hexadecimal forms that ipaddress deliberately rejects.
        return re.fullmatch(
            r"(?:[0-9]+|0x[0-9a-f]*)", hostname.rsplit(".", 1)[-1]
        ) is None
    return not (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
    )


def gmail_recipient_address(user):
    try:
        address = Address(addr_spec=user.email)
    except (ValueError, HeaderParseError):
        return None
    return address.addr_spec if address.username and address.domain else None


def allowed_recipient(user, gmail=False):
    return user.simulation_email_approved and (
        not gmail or gmail_recipient_address(user) is not None
    )


def pending_recipients(campaign):
    delivered_ids = set(
        db.session.scalars(
            db.select(TrackingEvent.recipient_id).where(
                TrackingEvent.event_type == "email_delivered",
                TrackingEvent.recipient_id.in_(
                    [recipient.recipient_id for recipient in campaign.recipients]
                ),
            )
        ).all()
    )
    return [
        recipient
        for recipient in campaign.recipients
        if recipient.recipient_id not in delivered_ids
    ]


def delivery_preview(campaign):
    gmail = campaign.sending_profile_id is not None
    profile = campaign.sending_profile if gmail else None
    pending = pending_recipients(campaign)
    allowed = [recipient for recipient in pending if allowed_recipient(recipient.user, gmail)]
    blocked = [
        recipient for recipient in pending if not allowed_recipient(recipient.user, gmail)
    ]
    noun = "EMAIL" if len(allowed) == 1 else "EMAILS"
    phrase = f"SEND {len(allowed)} {'REAL' if gmail else 'AUTHORIZED'} {noun}"
    return {
        "delivery_method": "gmail" if gmail else "mailpit",
        "real_delivery": gmail,
        "profile": profile.to_safe_dict() if profile else None,
        "profile_ready": bool(profile and profile.enabled and profile.last_test_succeeded)
        if gmail else True,
        "delivery_enabled": current_app.config["MAIL_DELIVERY_ENABLED"],
        "public_url_safe": public_gmail_url_is_safe() if gmail else public_url_is_safe(),
        "campaign_recipient_limit": current_app.config[
            "GMAIL_MAX_CAMPAIGN_RECIPIENTS" if gmail else "MAX_CAMPAIGN_RECIPIENTS"
        ],
        "hourly_delivery_limit": current_app.config[
            "GMAIL_MAX_EMAILS_PER_HOUR" if gmail else "MAX_EMAILS_PER_HOUR"
        ],
        "hourly_delivered_count": hourly_delivery_count("gmail" if gmail else None),
        "from": formataddr((profile.from_name, profile.from_email))
        if profile else current_app.config["MAIL_FROM"],
        "subject": f"{SIMULATION_PREFIX} {campaign.template.subject}",
        "allowed_recipients": [recipient.user.to_dict() for recipient in allowed],
        "blocked_recipients": [recipient.user.to_dict() for recipient in blocked],
        "already_delivered": len(campaign.recipients) - len(pending),
        "confirmation_phrase": phrase,
    }


def hourly_delivery_count(delivery_channel=None):
    since = utc_now() - timedelta(hours=1)
    statement = db.select(db.func.count(TrackingEvent.event_id)).where(
        TrackingEvent.event_type == "email_delivered",
        TrackingEvent.occurred_at >= since,
    )
    if delivery_channel is not None:
        statement = statement.where(TrackingEvent.delivery_channel == delivery_channel)
    return db.session.scalar(statement) or 0


def message_for(campaign, recipient, to_address=None, from_address=None):
    link = tracking_url(recipient)
    body = campaign.template.body
    if LINK_PLACEHOLDER in body:
        body = body.replace(LINK_PLACEHOLDER, link)
    else:
        body = f"{body.rstrip()}\n\nContinue the authorized exercise:\n{link}"
    body = (
        "AUTHORIZED SECURITY-AWARENESS SIMULATION\n"
        "Do not enter or send a real password or personal information.\n\n"
        f"{body}\n\n"
        "This message was generated by PhishGuard for an approved training exercise."
    )
    message = EmailMessage()
    if from_address is not None:
        message["From"] = from_address
    elif campaign.sending_profile_id is not None:
        profile = campaign.sending_profile
        message["From"] = formataddr((profile.from_name, profile.from_email))
    else:
        message["From"] = current_app.config["MAIL_FROM"]
    message["To"] = to_address if to_address is not None else recipient.user.email
    message["Subject"] = f"{SIMULATION_PREFIX} {campaign.template.subject}"
    message["X-PhishGuard-Simulation"] = "authorized-training"
    message.set_content(body)
    return message


def send_campaign(campaign, confirmation=None):
    if campaign.sending_profile_id is not None:
        with GMAIL_SEND_LOCK:
            db.session.expire_all()
            if campaign.sending_profile_id is None:
                raise ValueError("Gmail sending profile is no longer selected")
            return _send_campaign(campaign, confirmation=confirmation)
    return _send_campaign(campaign)


def _send_campaign(campaign, confirmation=None):
    preview = delivery_preview(campaign)
    if confirmation is not None and confirmation != preview["confirmation_phrase"]:
        raise ValueError("Review the updated delivery preview and confirm again")
    channel = preview["delivery_method"]
    gmail = channel == "gmail"
    if not preview["delivery_enabled"]:
        raise ValueError("Email delivery is disabled")
    if not preview["profile_ready"]:
        raise ValueError("Gmail sending profile must be enabled and successfully tested")
    if not preview["public_url_safe"]:
        if gmail:
            raise ValueError("Gmail delivery requires a public HTTPS URL")
        raise ValueError("PUBLIC_BASE_URL must use HTTPS outside localhost")
    if preview["blocked_recipients"]:
        if gmail:
            raise PermissionError("Every Gmail recipient must be approved with one valid mailbox")
        raise PermissionError("Every recipient must be explicitly allowlisted")

    pending = [
        recipient
        for recipient in pending_recipients(campaign)
        if allowed_recipient(recipient.user, gmail)
    ]
    if not pending:
        raise ValueError("No undelivered allowlisted recipients")
    recipient_count = len(pending) if gmail else len(campaign.recipients)
    if recipient_count > preview["campaign_recipient_limit"]:
        raise ValueError("Campaign exceeds the recipient safety limit")
    if hourly_delivery_count("gmail" if gmail else None) + len(pending) > preview[
        "hourly_delivery_limit"
    ]:
        raise ValueError("Hourly email safety limit would be exceeded")

    addresses = {
        recipient.recipient_id: gmail_recipient_address(recipient.user)
        for recipient in pending
    } if gmail else {}
    if gmail:
        profile = campaign.sending_profile
        profile_id = profile.profile_id
        sender_email = profile.from_email
        encrypted_password = profile.encrypted_app_password
        sender_header = formataddr((profile.from_name, sender_email))
    delivered = 0
    try:
        with smtplib.SMTP(
            "smtp.gmail.com" if gmail else current_app.config["MAIL_HOST"],
            587 if gmail else current_app.config["MAIL_PORT"],
            timeout=10,
        ) as smtp:
            if gmail:
                context = ssl.create_default_context()
                smtp.starttls(context=context)
                try:
                    smtp.login(
                        sender_email,
                        decrypt_app_password(encrypted_password or ""),
                    )
                except (RuntimeError, ValueError, InvalidToken) as error:
                    raise ConnectionError("Gmail credentials are unavailable") from error
            for recipient in pending:
                if gmail:
                    db.session.rollback()
                with DELIVERY_STATE.dispatch() if gmail else nullcontext():
                    if gmail:
                        profile = db.session.get(SendingProfile, profile_id)
                        if (
                            campaign.sending_profile_id != profile_id or profile is None
                            or not profile.enabled or not profile.last_test_succeeded
                            or profile.from_email != sender_email
                            or profile.encrypted_app_password != encrypted_password
                        ):
                            raise ValueError(
                                "Gmail sending profile changed; review the delivery preview again"
                            )
                        if any(not item.user.simulation_email_approved for item in pending):
                            raise DeliveryApprovalChanged(
                                "Gmail recipient approval changed; review the delivery preview again"
                            )
                    address = addresses[recipient.recipient_id] if gmail else None
                    message = message_for(
                        campaign, recipient, to_address=address,
                        from_address=sender_header if gmail else None,
                    )
                    if gmail:
                        smtp.send_message(message, to_addrs=[address])
                    else:
                        smtp.send_message(message)
                    db.session.add(
                        TrackingEvent(
                            recipient=recipient, event_type="email_delivered",
                            delivery_channel=channel,
                        )
                    )
                    db.session.commit()
                    delivered += 1
    except DeliveryApprovalChanged:
        raise
    except (OSError, smtplib.SMTPException) as error:
        db.session.rollback()
        for recipient in pending[delivered:]:
            db.session.add(
                TrackingEvent(
                    recipient=recipient, event_type="email_failed", delivery_channel=channel
                )
            )
        campaign.status = "delivery_failed"
        db.session.commit()
        if gmail:
            raise ConnectionError("Gmail email delivery failed") from error
        raise ConnectionError("The local email test server is unavailable") from error

    campaign.status = "active"
    db.session.commit()
    return delivered
