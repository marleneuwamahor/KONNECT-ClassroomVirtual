import uuid
from datetime import datetime, timedelta, timezone

import jwt
import requests

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


HMS_API_URL = "https://api.100ms.live/v2"
TOKEN_LIFETIME_SECONDS = 60 * 60
HMS_WEBHOOK_SECRET_HEADER = "X-KONNECT-Webhook-Secret"


class HMSServiceError(Exception):
    """An expected failure communicating with the 100ms API."""


def _get_hms_credentials():
    access_key = getattr(settings, "HMS_ACCESS_KEY", "")
    app_secret = getattr(settings, "HMS_APP_SECRET", "")

    if not access_key or not app_secret:
        raise ImproperlyConfigured("Configure HMS_ACCESS_KEY and HMS_APP_SECRET.")

    return access_key, app_secret


def generate_hms_auth_token(*, room_id, user_id, role, expires_at=None):
    """Generate a short-lived client token for an authorized room participant."""
    access_key, app_secret = _get_hms_credentials()

    if not room_id or not user_id or not role:
        raise ValueError("room_id, user_id and role are required.")

    now = datetime.now(timezone.utc)
    payload = {
        "access_key": access_key,
        "type": "app",
        "version": 2,
        "room_id": str(room_id),
        "user_id": str(user_id),
        "role": str(role),
        "jti": str(uuid.uuid4()),
        "iat": now,
        "nbf": now,
        "exp": min(
            now + timedelta(seconds=TOKEN_LIFETIME_SECONDS),
            expires_at or now + timedelta(seconds=TOKEN_LIFETIME_SECONDS),
        ),
    }
    if payload["exp"] <= now:
        raise ValueError("The token expiration must be in the future.")
    return jwt.encode(payload, app_secret, algorithm="HS256")


def generate_hms_management_token():
    """Generate a short-lived token for server-side 100ms API calls."""
    access_key, app_secret = _get_hms_credentials()
    now = datetime.now(timezone.utc)
    payload = {
        "access_key": access_key,
        "type": "management",
        "version": 2,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=10),
    }
    return jwt.encode(payload, app_secret, algorithm="HS256")


def create_hms_room(*, name, description=""):
    """Create a 100ms room and return its room object."""
    access_key, _ = _get_hms_credentials()
    template_id = getattr(settings, "HMS_TEMPLATE_ID", "")
    webhook_url = getattr(settings, "HMS_WEBHOOK_URL", "")
    webhook_secret = getattr(settings, "HMS_WEBHOOK_SECRET", "")

    if not template_id:
        raise ImproperlyConfigured("Configure HMS_TEMPLATE_ID before creating rooms.")
    if not webhook_url or not webhook_secret:
        raise ImproperlyConfigured(
            "Configure HMS_WEBHOOK_URL and HMS_WEBHOOK_SECRET for attendance tracking."
        )
    if not webhook_url.startswith("https://"):
        raise ImproperlyConfigured("HMS_WEBHOOK_URL must use HTTPS.")

    payload = {
        "name": name,
        "description": description,
        "template_id": template_id,
        "webhook": {
            "url": webhook_url,
            "headers": {HMS_WEBHOOK_SECRET_HEADER: webhook_secret},
        },
    }
    headers = {
        "Authorization": f"Bearer {generate_hms_management_token()}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            f"{HMS_API_URL}/rooms",
            headers=headers,
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise HMSServiceError("The 100ms room request failed.") from exc
    except ValueError as exc:
        raise HMSServiceError("100ms returned an invalid room response.") from exc

    if not isinstance(data, dict) or not data.get("id"):
        raise HMSServiceError("100ms did not return a room ID.")

    return data
