from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "admin_profile",
        "user",
        "action",
        "entity",
        "entity_id",
        "entity_key",
        "ip_address",
    )
    list_filter = ("action", "entity")
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False