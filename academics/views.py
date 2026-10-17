import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from accounts.models import User
from accounts.permissions import IsAdminRole, IsTeacherOrAdmin, IsTeacherOrAdminOrReadOnly
from accounts.scoping import is_admin, student_scoped
from .models import Attendance, Enrollment, LiveSession, SchoolClass
from .serializers import (
    AttendanceSerializer,
    EnrollmentSerializer,
    LiveSessionSerializer,
    SchoolClassSerializer,
)
from .services.hms_service import (
    HMS_WEBHOOK_SECRET_HEADER,
    HMSServiceError,
    TOKEN_LIFETIME_SECONDS,
    create_hms_room,
    generate_hms_auth_token,
)
from .services.hms_webhooks import process_hms_webhook


logger = logging.getLogger(__name__)


class HMSUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = "hms_unavailable"


def resolve_teacher(request, serializer):
    """Teachers always act as themselves; admins must pass `teacher` explicitly."""
    user = request.user
    if user.role == User.Role.TEACHER:
        return user.teacher_profile
    teacher = serializer.validated_data.get("teacher")
    if not teacher:
        raise ValidationError({"teacher": "This field is required for admins."})
    return teacher


class SchoolClassViewSet(viewsets.ModelViewSet):
    serializer_class = SchoolClassSerializer
    permission_classes = [IsTeacherOrAdminOrReadOnly]
    filterset_fields = ["grade", "teacher"]
    search_fields = ["name", "description"]

    def get_queryset(self):
        user = self.request.user
        qs = SchoolClass.objects.select_related("teacher__user").order_by("id")
        if is_admin(user):
            return qs
        if user.role == User.Role.TEACHER:
            return qs.filter(teacher__user=user)
        return qs.filter(enrollments__student__user=user).distinct()

    def perform_create(self, serializer):
        serializer.save(teacher=resolve_teacher(self.request, serializer))


class EnrollmentViewSet(viewsets.ModelViewSet):
    serializer_class = EnrollmentSerializer
    filterset_fields = ["student", "school_class", "status"]

    def get_queryset(self):
        qs = Enrollment.objects.select_related("student__user", "school_class").order_by("id")
        return student_scoped(qs, self.request.user)

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated()]
        return [IsAdminRole()]


class AttendanceViewSet(viewsets.ModelViewSet):
    serializer_class = AttendanceSerializer
    filterset_fields = ["student", "school_class", "attendance_date", "status"]

    def get_queryset(self):
        qs = Attendance.objects.select_related("student__user", "school_class").order_by(
            "-attendance_date", "id"
        )
        return student_scoped(qs, self.request.user)

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated()]
        return [IsTeacherOrAdmin()]

    def _check_class_owner(self, serializer):
        user = self.request.user
        school_class = serializer.validated_data.get(
            "school_class", getattr(serializer.instance, "school_class", None)
        )
        if user.role == User.Role.TEACHER and school_class.teacher.user_id != user.id:
            raise PermissionDenied("You can only record attendance for your own classes.")

    def perform_create(self, serializer):
        self._check_class_owner(serializer)
        serializer.save()

    def perform_update(self, serializer):
        self._check_class_owner(serializer)
        serializer.save()


class LiveSessionViewSet(viewsets.ModelViewSet):
    serializer_class = LiveSessionSerializer
    permission_classes = [IsTeacherOrAdminOrReadOnly]
    filterset_fields = ["school_class", "teacher", "status"]
    search_fields = ["title"]

    def get_queryset(self):
        user = self.request.user
        qs = LiveSession.objects.select_related(
            "school_class", "teacher__user"
        ).order_by("start_time")
        if is_admin(user):
            return qs
        if user.role == User.Role.TEACHER:
            return qs.filter(teacher__user=user)
        if user.role == User.Role.STUDENT:
            return qs.filter(
                school_class__enrollments__student__user=user,
                school_class__enrollments__status=Enrollment.Status.ACTIVE,
            ).distinct()
        return qs.none()

    def get_permissions(self):
        if self.action == "join":
            return [IsAuthenticated()]
        if self.action == "webhook":
            return [AllowAny()]
        return super().get_permissions()

    @transaction.atomic
    def perform_create(self, serializer):
        school_class = serializer.validated_data["school_class"]
        teacher = school_class.teacher
        requested_teacher = serializer.validated_data.get("teacher")
        if requested_teacher and requested_teacher.id != teacher.id:
            raise ValidationError({
                "teacher": "The session teacher must be assigned to the selected class."
            })
        if (
            self.request.user.role == User.Role.TEACHER
            and teacher.user_id != self.request.user.id
        ):
            raise PermissionDenied("You can only schedule sessions for your own classes.")

        session = serializer.save(teacher=teacher)
        if not settings.HMS_ENABLED:
            return

        try:
            room = create_hms_room(
                name=f"konnect-session-{session.pk}",
                description=session.title,
            )
        except (HMSServiceError, ImproperlyConfigured) as exc:
            logger.error(
                "Could not create a 100ms room for session %s: %s",
                session.pk,
                exc,
            )
            raise HMSUnavailable(
                "The live session could not be provisioned with 100ms. "
                "Check the server's 100ms configuration and try again."
            ) from exc

        session.hms_room_id = room["id"]
        session.save(update_fields=["hms_room_id"])

    @action(detail=True, methods=["post"])
    def join(self, request, pk=None):
        session = self.get_object()
        now = timezone.now()

        if session.status in (LiveSession.Status.ENDED, LiveSession.Status.CANCELLED):
            raise ValidationError({"detail": "This live session is no longer available."})
        if now > session.join_deadline:
            raise PermissionDenied("The live-session join deadline has passed.")
        if not settings.HMS_ENABLED:
            raise HMSUnavailable("100ms live sessions are not enabled.")
        if not session.hms_room_id:
            raise HMSUnavailable("This live session has no 100ms room configured.")
        token_expires_at = min(
            session.join_deadline,
            now + timedelta(seconds=TOKEN_LIFETIME_SECONDS),
        )

        role = (
            settings.HMS_TEACHER_ROLE
            if request.user.role == User.Role.TEACHER or is_admin(request.user)
            else settings.HMS_STUDENT_ROLE
        )
        try:
            token = generate_hms_auth_token(
                room_id=session.hms_room_id,
                user_id=request.user.id,
                role=role,
                expires_at=token_expires_at,
            )
        except ImproperlyConfigured as exc:
            logger.error("100ms token generation is not configured: %s", exc)
            raise HMSUnavailable(
                "The live-session service is not configured."
            ) from exc
        except ValueError as exc:
            raise PermissionDenied("The live-session join deadline has passed.") from exc

        return Response({
            "token": token,
            "room_id": session.hms_room_id,
            "role": role,
            "expires_in": max(
                1,
                int((token_expires_at - timezone.now()).total_seconds()),
            ),
        })

    @action(
        detail=False,
        methods=["post"],
        url_path="webhook",
        permission_classes=[AllowAny],
        authentication_classes=[],
    )
    def webhook(self, request):
        configured_secret = settings.HMS_WEBHOOK_SECRET
        if not configured_secret:
            return Response(
                {"detail": "The 100ms webhook is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        provided_secret = request.headers.get(HMS_WEBHOOK_SECRET_HEADER, "")
        if not secrets.compare_digest(provided_secret, configured_secret):
            return Response(
                {"detail": "Invalid webhook credentials."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            process_hms_webhook(request.data)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response({"received": True})