import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from accounts.models import User
from accounts.permissions import IsAdminRole, IsTeacherOrAdmin, IsTeacherOrAdminOrReadOnly
from accounts.scoping import is_admin, student_scoped
from .models import Attendance, Course, Enrollment, LiveSession
from .serializers import (
    AttendanceSerializer,
    CourseSerializer,
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


class CourseViewSet(viewsets.ModelViewSet):
    serializer_class = CourseSerializer
    permission_classes = [IsTeacherOrAdminOrReadOnly]
    filterset_fields = ["status", "visibility", "teacher"]
    search_fields = ["title", "description"]

    def get_queryset(self):
        user = self.request.user
        qs = Course.objects.select_related("teacher__user", "approved_by").order_by(
            "title", "id"
        )
        if is_admin(user):
            return qs
        if user.role == User.Role.TEACHER:
            return qs.filter(teacher__user=user)
        return qs.filter(status=Course.Status.APPROVED).filter(
            Q(visibility=Course.Visibility.PUBLIC)
            | Q(
                enrollments__student__user=user,
                enrollments__status=Enrollment.Status.ACTIVE,
            )
        ).distinct()

    def perform_create(self, serializer):
        teacher = resolve_teacher(self.request, serializer)
        if self.request.user.role == User.Role.TEACHER:
            serializer.save(
                teacher=teacher,
                status=Course.Status.PENDING,
                approved_by=None,
            )
            return
        serializer.save(
            teacher=teacher,
            status=Course.Status.APPROVED,
            approved_by=self.request.user,
        )

    def perform_update(self, serializer):
        if self.request.user.role == User.Role.TEACHER:
            serializer.save(teacher=self.request.user.teacher_profile)
            return
        serializer.save()

    @action(detail=True, methods=["post"], permission_classes=[IsAdminRole])
    def approve(self, request, pk=None):
        course = self.get_object()
        course.status = Course.Status.APPROVED
        course.approved_by = request.user
        course.save(update_fields=["status", "approved_by"])
        return Response(self.get_serializer(course).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAdminRole])
    def reject(self, request, pk=None):
        course = self.get_object()
        course.status = Course.Status.REJECTED
        course.approved_by = None
        course.save(update_fields=["status", "approved_by"])
        return Response(self.get_serializer(course).data)


class SchoolClassViewSet(CourseViewSet):
    serializer_class = SchoolClassSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Course.objects.select_related("teacher__user").order_by("id")
        if is_admin(user):
            return qs
        if user.role == User.Role.TEACHER:
            return qs.filter(teacher__user=user)
        return qs.filter(
            status=Course.Status.APPROVED,
            enrollments__student__user=user,
            enrollments__status=Enrollment.Status.ACTIVE,
        ).distinct()


class EnrollmentViewSet(viewsets.ModelViewSet):
    serializer_class = EnrollmentSerializer
    filterset_fields = ["student", "course", "status"]

    def get_queryset(self):
        qs = Enrollment.objects.select_related("student__user", "course").order_by("id")
        return student_scoped(qs, self.request.user)

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated()]
        return [IsAdminRole()]

    def perform_create(self, serializer):
        course = serializer.validated_data["course"]
        if course.status != Course.Status.APPROVED:
            raise ValidationError({"course": "Students can only be enrolled in approved courses."})
        if (
            course.course_limit
            and course.enrollments.filter(status=Enrollment.Status.ACTIVE).count()
            >= course.course_limit
        ):
            raise ValidationError({"course": "This course has reached its enrollment limit."})
        serializer.save()


class AttendanceViewSet(viewsets.ModelViewSet):
    serializer_class = AttendanceSerializer
    filterset_fields = ["student", "course", "attendance_date", "status"]

    def get_queryset(self):
        qs = Attendance.objects.select_related("student__user", "course").order_by(
            "-attendance_date", "id"
        )
        return student_scoped(qs, self.request.user)

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated()]
        return [IsTeacherOrAdmin()]

    def _check_class_owner(self, serializer):
        user = self.request.user
        course = serializer.validated_data.get(
            "course", getattr(serializer.instance, "course", None)
        )
        if user.role == User.Role.TEACHER and course.teacher.user_id != user.id:
            raise PermissionDenied("You can only record attendance for your own courses.")

    def perform_create(self, serializer):
        self._check_class_owner(serializer)
        serializer.save()

    def perform_update(self, serializer):
        self._check_class_owner(serializer)
        serializer.save()


class LiveSessionViewSet(viewsets.ModelViewSet):
    serializer_class = LiveSessionSerializer
    permission_classes = [IsTeacherOrAdminOrReadOnly]
    filterset_fields = ["course", "teacher", "status"]
    search_fields = ["title"]

    def get_queryset(self):
        user = self.request.user
        qs = LiveSession.objects.select_related(
            "course", "teacher__user"
        ).order_by("start_time")
        if is_admin(user):
            return qs
        if user.role == User.Role.TEACHER:
            return qs.filter(teacher__user=user)
        if user.role == User.Role.STUDENT:
            return qs.filter(
                course__enrollments__student__user=user,
                course__enrollments__status=Enrollment.Status.ACTIVE,
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
        course = serializer.validated_data["course"]
        if course.status != Course.Status.APPROVED:
            raise ValidationError({"course": "Only approved courses can schedule sessions."})
        teacher = course.teacher
        requested_teacher = serializer.validated_data.get("teacher")
        if requested_teacher and requested_teacher.id != teacher.id:
            raise ValidationError({
                "teacher": "The session teacher must be assigned to the selected course."
            })
        if (
            self.request.user.role == User.Role.TEACHER
            and teacher.user_id != self.request.user.id
        ):
            raise PermissionDenied("You can only schedule sessions for your own courses.")

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