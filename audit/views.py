from rest_framework import viewsets

from accounts.permissions import IsAdminRole

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only audit history, available only to administrator accounts."""

    queryset = AuditLog.objects.select_related("user", "admin_profile")
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdminRole]
    filterset_fields = ["user", "admin_profile", "action", "entity"]