from cloudinary.exceptions import Error as CloudinaryError
import cloudinary
import cloudinary.uploader
import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class ProfileImageStorageError(Exception):
    """Cloudinary could not store a profile image."""


def upload_profile_image(image, *, user_id):
    """Store a user's image in Cloudinary and return its secure delivery URL."""
    if not settings.CLOUDINARY_URL:
        raise ImproperlyConfigured("CLOUDINARY_URL is not configured.")

    cloudinary.config(url=settings.CLOUDINARY_URL, secure=True)
    try:
        result = cloudinary.uploader.upload(
            image,
            folder="konnect/profile-images",
            public_id=f"user-{user_id}",
            overwrite=True,
            invalidate=True,
            resource_type="image",
        )
    except (CloudinaryError, requests.RequestException) as exc:
        raise ProfileImageStorageError from exc

    secure_url = result.get("secure_url") if isinstance(result, dict) else None
    if not secure_url:
        raise ProfileImageStorageError(
            "Cloudinary did not return a secure image URL."
        )
    return secure_url
