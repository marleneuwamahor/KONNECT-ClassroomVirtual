from .utils import log_action


class AuditAdminChangesMixin:
    """Record object writes made through Django's admin site."""

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        self._log_admin_change(
            request,
            "update" if change else "create",
            obj,
        )

    def delete_model(self, request, obj):
        entity_id, entity_key = self._entity_identity(obj.pk)
        entity = obj._meta.model_name
        super().delete_model(request, obj)
        log_action(
            request,
            "delete",
            entity,
            entity_id=entity_id,
            entity_key=entity_key,
        )

    def delete_queryset(self, request, queryset):
        model = queryset.model
        identities = [
            self._entity_identity(pk)
            for pk in queryset.values_list("pk", flat=True)
        ]
        super().delete_queryset(request, queryset)
        for entity_id, entity_key in identities:
            log_action(
                request,
                "delete",
                model._meta.model_name,
                entity_id=entity_id,
                entity_key=entity_key,
            )

    def _log_admin_change(self, request, action, obj):
        entity_id, entity_key = self._entity_identity(obj.pk)
        log_action(
            request,
            action,
            obj._meta.model_name,
            entity_id=entity_id,
            entity_key=entity_key,
        )

    @staticmethod
    def _entity_identity(primary_key):
        try:
            return int(primary_key), ""
        except (TypeError, ValueError):
            return None, str(primary_key)
