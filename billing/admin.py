from django.contrib import admin

from audit.admin_mixins import AuditAdminChangesMixin
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(AuditAdminChangesMixin, admin.ModelAdmin):
    list_display = ("transaction_ref", "student", "amount", "status", "paid_at")
    list_filter = ("status",)
    search_fields = ("transaction_ref", "student__student_number")