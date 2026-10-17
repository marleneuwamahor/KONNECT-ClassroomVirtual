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
from .models import Attendance, Course, Enrollment, Exam, Grade, LiveSession, StudentFlag
from .serializers import (
    AttendanceSerializer,
    CourseSerializer,
    EnrollmentSerializer,
    ExamGradeSerializer,
    ExamSerializer,
    LiveSessionSerializer,
    SchoolClassSerializer,
    StudentFlagSerializer,
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
    """Browse courses, create pending teacher courses and administer approvals."""

    lookup_value_regex = r"\d+"
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
            approved_by=self.request.user.admin_profile,
        )

    def perform_update(self, serializer):
        if self.request.user.role == User.Role.TEACHER:
            serializer.save(teacher=self.request.user.teacher_profile)
            return
        serializer.save()

    @action(detail=True, methods=["post"], permission_classes=[IsAdminRole])
    def approve(self, request, pk=None):
        """Approve a pending course and record the approving administrator profile."""
        course = self.get_object()
        course.status = Course.Status.APPROVED
        course.approved_by = request.user.admin_profile
        course.save(update_fields=["status", "approved_by"])
        return Response(self.get_serializer(course).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAdminRole])
    def reject(self, request, pk=None):
        """Reject a course and clear its approving administrator."""
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


class ExamViewSet(viewsets.ModelViewSet):
    """Schedule course exams; students can read exams for their active courses."""

    serializer_class = ExamSerializer
    filterset_fields = ["course", "exam_date"]
    search_fields = ["title"]
    ordering_fields = ["exam_date", "title"]

    def get_queryset(self):
        queryset = Exam.objects.select_related("course", "course__teacher__user")
        user = self.request.user
        if is_admin(user):
            return queryset
        if user.role == User.Role.TEACHER:
            return queryset.filter(course__teacher__user=user)
        if user.role == User.Role.STUDENT:
            return queryset.filter(
                course__status=Course.Status.APPROVED,
                course__enrollments__student__user=user,
                course__enrollments__status=Enrollment.Status.ACTIVE,
            ).distinct()
        return queryset.none()

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated()]
        return [IsTeacherOrAdmin()]

    def _validate_course_access(self, course):
        if course.status != Course.Status.APPROVED:
            raise ValidationError({"course": "Exams require an approved course."})
        if (
            self.request.user.role == User.Role.TEACHER
            and course.teacher.user_id != self.request.user.id
        ):
            raise PermissionDenied("You can manage exams only for your own courses.")

    def perform_create(self, serializer):
        self._validate_course_access(serializer.validated_data["course"])
        serializer.save()

    def perform_update(self, serializer):
        course = serializer.validated_data.get(
            "course",
            serializer.instance.course,
        )
        self._validate_course_access(course)
        serializer.save()


class GradeViewSet(viewsets.ModelViewSet):
    """Record exam scores; students can read only their own grades."""

    serializer_class = ExamGradeSerializer
    filterset_fields = ["exam", "student", "graded_by"]
    ordering_fields = ["graded_at", "score"]

    def get_queryset(self):
        queryset = Grade.objects.select_related(
            "exam__course",
            "student__user",
            "graded_by__user",
        ).order_by("-graded_at", "id")
        return student_scoped(
            queryset,
            self.request.user,
            class_path="exam__course",
        )

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated()]
        return [IsTeacherOrAdmin()]

    def perform_create(self, serializer):
        exam = serializer.validated_data["exam"]
        student = serializer.validated_data["student"]
        if not exam.course.enrollments.filter(
            student=student,
            status=Enrollment.Status.ACTIVE,
        ).exists():
            raise ValidationError(
                {"student": "Grades can be recorded only for active course enrollments."}
            )
        teacher = exam.course.teacher
        if (
            self.request.user.role == User.Role.TEACHER
            and teacher.user_id != self.request.user.id
        ):
            raise PermissionDenied("You can grade exams only for your own courses.")
        serializer.save(graded_by=teacher)

    def perform_update(self, serializer):
        exam = serializer.validated_data.get("exam", serializer.instance.exam)
        student = serializer.validated_data.get("student", serializer.instance.student)
        if not exam.course.enrollments.filter(
            student=student,
            status=Enrollment.Status.ACTIVE,
        ).exists():
            raise ValidationError(
                {"student": "Grades can be recorded only for active course enrollments."}
            )
        teacher = exam.course.teacher
        if (
            self.request.user.role == User.Role.TEACHER
            and teacher.user_id != self.request.user.id
        ):
            raise PermissionDenied("You can grade exams only for your own courses.")
        serializer.save(graded_by=teacher)


class StudentFlagViewSet(viewsets.ModelViewSet):
    """Flag a student in a course; teachers may flag their own active enrollees."""

    serializer_class = StudentFlagSerializer
    filterset_fields = ["student", "course", "flagged_by"]
    search_fields = ["reason"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        queryset = StudentFlag.objects.select_related(
            "student__user",
            "course",
            "flagged_by__user",
        )
        return student_scoped(queryset, self.request.user)

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated()]
        return [IsTeacherOrAdmin()]

    def _validate_flag(self, student, course):
        if not course.enrollments.filter(
            student=student,
            status=Enrollment.Status.ACTIVE,
        ).exists():
            raise ValidationError(
                {"student": "Only students actively enrolled in the course can be flagged."}
            )
        teacher = course.teacher
        if (
            self.request.user.role == User.Role.TEACHER
            and teacher.user_id != self.request.user.id
        ):
            raise PermissionDenied("You can flag students only in your own courses.")
        return teacher

    def perform_create(self, serializer):
        student = serializer.validated_data["student"]
        course = serializer.validated_data["course"]
        teacher = self._validate_flag(student, course)
        serializer.save(flagged_by=teacher)

    def perform_update(self, serializer):
        student = serializer.validated_data.get(
            "student",
            serializer.instance.student,
        )
        course = serializer.validated_data.get(
            "course",
            serializer.instance.course,
        )
        teacher = self._validate_flag(student, course)
        serializer.save(flagged_by=teacher)


class EnrollmentViewSet(viewsets.ModelViewSet):
    """Admin-managed student-course enrollments with course approval and capacity checks."""

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
    """Read attendance by role and record manual attendance for teacher-owned courses."""

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
        student = serializer.validated_data.get(
            "student", getattr(serializer.instance, "student", None)
        )
        if student and not course.enrollments.filter(
            student=student,
            status=Enrollment.Status.ACTIVE,
        ).exists():
            raise ValidationError(
                {"student": "Attendance can be recorded only for active course enrollments."}
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
    """Schedule and join course sessions; 100ms tokens and webhook routes are server-managed."""

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
        """Return a short-lived 100ms join token to an eligible participant."""
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
        """Receive authenticated 100ms room events and update attendance."""
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