from rest_framework import status

from .utils import log_action


class AuditAdminWritesMixin:
    """Write an audit record for each successful administrator API mutation."""

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        user = getattr(request, "user", None)
        if (
            response.status_code < status.HTTP_200_OK
            or response.status_code >= status.HTTP_300_MULTIPLE_CHOICES
            or request.method not in {"POST", "PUT", "PATCH", "DELETE"}
            or getattr(user, "role", None) != "admin"
            or getattr(request, "_audit_logged", False)
        ):
            return response

        serializer_class = self.get_serializer_class()
        serializer_meta = getattr(serializer_class, "Meta", None)
        model = getattr(serializer_meta, "model", None)
        if model is None:
            queryset = getattr(self, "queryset", None)
            model = getattr(queryset, "model", None)
        if model is None:
            raise RuntimeError(
                f"{type(self).__name__} cannot determine its audit entity model."
            )

        data = getattr(response, "data", None)
        raw_entity_id = data.get("id") if isinstance(data, dict) else None
        if raw_entity_id is None:
            raw_entity_id = getattr(self, "kwargs", {}).get("pk")
        raw_entity_key = data.get("key") if isinstance(data, dict) else None
        try:
            entity_id = int(raw_entity_id) if raw_entity_id is not None else None
        except (TypeError, ValueError):
            entity_id = None
            if raw_entity_key is None and raw_entity_id is not None:
                raw_entity_key = str(raw_entity_id)

        log_action(
            request,
            getattr(self, "action", request.method.lower()),
            model._meta.model_name,
            entity_id,
            str(raw_entity_key) if raw_entity_key is not None else "",
        )
        return response
