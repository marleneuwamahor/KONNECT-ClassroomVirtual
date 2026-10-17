from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.permissions import IsAdminRole
from accounts.scoping import is_admin
from audit.mixins import AuditAdminWritesMixin
from audit.utils import log_action

from .models import Payment
from .serializers import PaymentSerializer


class PaymentViewSet(AuditAdminWritesMixin, viewsets.ModelViewSet):
    """Admin-managed student payments; authenticated students can read their own records."""

    serializer_class = PaymentSerializer
    filterset_fields = ["student", "status"]
    search_fields = ["transaction_ref"]

    def get_queryset(self):
        qs = Payment.objects.select_related("student__user")
        user = self.request.user
        return qs if is_admin(user) else qs.filter(student__user=user)

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated()]
        return [IsAdminRole()]

    def perform_create(self, serializer):
        payment = serializer.save()
        log_action(self.request, "create", "payment", payment.id)

    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request, pk=None):
        """Mark a payment as paid, timestamp the change and write an audit event."""
        payment = self.get_object()
        payment.status = Payment.Status.PAID
        payment.paid_at = timezone.now()
        payment.save(update_fields=["status", "paid_at"])
        log_action(request, "mark_paid", "payment", payment.id)
        return Response(self.get_serializer(payment).data)