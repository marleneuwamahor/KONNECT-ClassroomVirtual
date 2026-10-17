from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    admin_id = serializers.PrimaryKeyRelatedField(
        source="admin_profile",
        read_only=True,
    )

    class Meta:
        model = AuditLog
        fields = [
            "id", "admin_id", "admin_profile", "user", "action", "entity",
            "entity_id", "entity_key", "created_at", "ip_address",
        ]