from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError

from accounts.models import User
from accounts.permissions import IsAdminRole, IsTeacherOrAdmin, IsTeacherOrAdminOrReadOnly
from accounts.scoping import class_scoped, is_admin, student_scoped

from .models import Attendance, Enrollment, LiveSession, SchoolClass
from .serializers import (
    AttendanceSerializer,
    EnrollmentSerializer,
    LiveSessionSerializer,
    SchoolClassSerializer,
)


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
        qs = LiveSession.objects.select_related("school_class", "teacher__user").order_by("start_time")
        return class_scoped(qs, self.request.user)

    def perform_create(self, serializer):
        serializer.save(teacher=resolve_teacher(self.request, serializer))