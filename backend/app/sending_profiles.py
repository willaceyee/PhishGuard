from cryptography.fernet import Fernet
from flask import current_app


def cipher():
    value = current_app.config["SENDING_PROFILE_ENCRYPTION_KEY"]
    if not value:
        raise RuntimeError("Sending-profile encryption is not configured")
    return Fernet(value.encode())


def encrypt_app_password(value: str) -> str:
    normalized = "".join(value.split())
    if not normalized:
        raise ValueError("Google app password is required")
    return cipher().encrypt(normalized.encode()).decode()


def decrypt_app_password(value: str) -> str:
    return cipher().decrypt(value.encode()).decode()
