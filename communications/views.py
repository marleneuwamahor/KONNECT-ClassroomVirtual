from rest_framework import mixins, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from audit.mixins import AuditAdminWritesMixin
from accounts.models import User
from accounts.permissions import IsAdminRole, IsTeacherOrAdminOrReadOnly
from accounts.scoping import class_scoped

from .models import Announcement, Notification, SystemSetting
from .serializers import (
    AnnouncementSerializer,
    NotificationSerializer,
    SystemSettingSerializer,
)


class AnnouncementViewSet(AuditAdminWritesMixin, viewsets.ModelViewSet):
    """Course announcements; teachers can write only to courses they teach."""

    serializer_class = AnnouncementSerializer
    permission_classes = [IsTeacherOrAdminOrReadOnly]
    filterset_fields = ["course", "author"]
    search_fields = ["title", "content"]

    def get_queryset(self):
        qs = Announcement.objects.select_related("author", "course")
        return class_scoped(qs, self.request.user)

    def perform_create(self, serializer):
        user = self.request.user
        course = serializer.validated_data["course"]
        if user.role == User.Role.TEACHER and course.teacher.user_id != user.id:
            raise PermissionDenied("You can only post announcements to your own courses.")
        serializer.save(author=user, teacher=course.teacher)

    def perform_update(self, serializer):
        user = self.request.user
        course = serializer.validated_data.get(
            "course",
            serializer.instance.course,
        )
        if user.role == User.Role.TEACHER and course.teacher.user_id != user.id:
            raise PermissionDenied("You can only post announcements to your own courses.")
        serializer.save(teacher=course.teacher)


class NotificationViewSet(
    AuditAdminWritesMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Users read and manage their own notifications; admins can create notifications."""

    serializer_class = NotificationSerializer
    filterset_fields = ["is_read"]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    def get_permissions(self):
        if self.action == "create":
            return [IsAdminRole()]
        return [permissions.IsAuthenticated()]

    @action(detail=True, methods=["post"], url_path="read")
    def mark_read(self, request, pk=None):
        """Mark this user's notification as read."""
        notification = self.get_object()
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return Response(self.get_serializer(notification).data)

    @action(detail=False, methods=["post"], url_path="read-all")
    def mark_all_read(self, request):
        """Mark every unread notification belonging to the current user as read."""
        updated = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({"updated": updated})


class SystemSettingViewSet(AuditAdminWritesMixin, viewsets.ModelViewSet):
    """Admin-only key/value settings; every write records the acting admin profile."""

    queryset = SystemSetting.objects.select_related("updated_by__user").order_by("key")
    serializer_class = SystemSettingSerializer
    permission_classes = [IsAdminRole]
    search_fields = ["key", "value"]

    def perform_create(self, serializer):
        serializer.save(updated_by=self.request.user.admin_profile)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user.admin_profile)