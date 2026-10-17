from .models import AuditLog


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_action(request, action, entity, entity_id=None, entity_key=""):
    """Record who did what. Call this after a sensitive operation."""
    user = request.user if request.user.is_authenticated else None
    audit_log = AuditLog.objects.create(
        user=user,
        admin_profile=(
            user.admin_profile
            if user and user.role == "admin"
            else None
        ),
        action=action,
        entity=entity,
        entity_id=entity_id,
        entity_key=entity_key,
        ip_address=client_ip(request),
    )
    request._audit_logged = True
    return audit_log