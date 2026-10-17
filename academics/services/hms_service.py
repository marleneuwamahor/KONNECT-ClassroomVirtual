import uuid
from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


TOKEN_LIFETIME_SECONDS = 60 * 60  # 1 hour


def generate_hms_auth_token(*, room_id, user_id, role):
    """
    Generate a short-lived 100ms room authentication token.

    The caller must authorize the user before calling this function.
    The 100ms app secret must never be returned to the frontend.
    """
    access_key = getattr(settings, "HMS_ACCESS_KEY", "")
    app_secret = getattr(settings, "HMS_APP_SECRET", "")

    if not access_key or not app_secret:
        raise ImproperlyConfigured(
            "Configure HMS_ACCESS_KEY and HMS_APP_SECRET "
            "in the environment."
        )

    if not room_id or not user_id or not role:
        raise ValueError("room_id, user_id, and role are required.")

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
        "exp": now + timedelta(seconds=TOKEN_LIFETIME_SECONDS),
    }

    return jwt.encode(payload, app_secret, algorithm="HS256")