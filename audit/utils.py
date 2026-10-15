from .models import AuditLog


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_action(request, action, entity, entity_id=None):
    """Record who did what. Call this after a sensitive operation."""
    return AuditLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        action=action,
        entity=entity,
        entity_id=entity_id,
        ip_address=client_ip(request),
    )