from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from academics.views import resolve_teacher
from accounts.models import User
from accounts.permissions import IsStudentRole, IsTeacherOrAdmin, IsTeacherOrAdminOrReadOnly
from accounts.scoping import class_scoped, student_scoped
from audit.mixins import AuditAdminWritesMixin
from audit.utils import log_action

from .models import Assignment, Submission
from .serializers import (
    AssignmentSerializer,
    SubmissionGradeSerializer,
    SubmissionSerializer,
)


class AssignmentViewSet(AuditAdminWritesMixin, viewsets.ModelViewSet):
    """Create and manage course exercises and quizzes, including deadlines and scores."""

    serializer_class = AssignmentSerializer
    permission_classes = [IsTeacherOrAdminOrReadOnly]
    filterset_fields = ["course", "teacher"]
    search_fields = ["title", "description"]
    ordering_fields = ["due_at", "created_at"]

    def get_queryset(self):
        qs = Assignment.objects.select_related("course", "teacher__user").order_by("-created_at")
        return class_scoped(qs, self.request.user)

    def perform_create(self, serializer):
        teacher = resolve_teacher(self.request, serializer)
        course = serializer.validated_data["course"]
        if course.status != "approved":
            raise ValidationError({"course": "Assignments require an approved course."})
        if course.teacher_id != teacher.id:
            raise PermissionDenied("Assignments must use the course's assigned teacher.")
        serializer.save(teacher=teacher)

    def perform_update(self, serializer):
        user = self.request.user
        teacher = (
            user.teacher_profile
            if user.role == User.Role.TEACHER
            else serializer.validated_data.get("teacher", serializer.instance.teacher)
        )
        course = serializer.validated_data.get("course", serializer.instance.course)
        if course.status != "approved":
            raise ValidationError({"course": "Assignments require an approved course."})
        if course.teacher_id != teacher.id:
            raise PermissionDenied("Assignments must use the course's assigned teacher.")
        serializer.save(teacher=teacher)


class SubmissionViewSet(AuditAdminWritesMixin, viewsets.ModelViewSet):
    """Students submit answers or files; assignment teachers provide grades and feedback."""

    serializer_class = SubmissionSerializer
    filterset_fields = ["assignment", "student"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = Submission.objects.select_related(
            "assignment__course", "student__user"
        ).order_by("-submitted_at")
        return student_scoped(qs, self.request.user, class_path="assignment__course")

    def get_permissions(self):
        if self.action == "create":
            return [IsStudentRole()]
        if self.action == "grade":
            return [IsTeacherOrAdmin()]
        return [permissions.IsAuthenticated()]

    def get_serializer_class(self):
        return (
            SubmissionGradeSerializer
            if self.action == "grade"
            else SubmissionSerializer
        )

    def perform_create(self, serializer):
        student = self.request.user.student_profile
        assignment = serializer.validated_data["assignment"]
        if not assignment.course.enrollments.filter(student=student, status="active").exists():
            raise PermissionDenied("You are not enrolled in this class.")
        if Submission.objects.filter(assignment=assignment, student=student).exists():
            raise ValidationError("You have already submitted this assignment.")
        submission = serializer.save(student=student)
        log_action(self.request, "submit", "submission", submission.id)

    def perform_update(self, serializer):
        # Students may only edit their own submission; grading goes through /grade/.
        if self.request.user.role != User.Role.STUDENT:
            raise PermissionDenied("Use the grade endpoint to grade submissions.")
        assignment = serializer.validated_data.get(
            "assignment",
            serializer.instance.assignment,
        )
        student = self.request.user.student_profile
        if not assignment.course.enrollments.filter(
            student=student,
            status="active",
        ).exists():
            raise PermissionDenied("You are not enrolled in this class.")
        serializer.save()

    @action(detail=True, methods=["patch"])
    def grade(self, request, pk=None):
        submission = self.get_object()
        serializer = SubmissionGradeSerializer(
            submission,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        log_action(request, "grade", "submission", submission.id)
        return Response(serializer.data)