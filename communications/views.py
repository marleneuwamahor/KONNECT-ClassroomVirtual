from rest_framework import mixins, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from accounts.models import User
from accounts.permissions import IsAdminRole, IsTeacherOrAdminOrReadOnly
from accounts.scoping import class_scoped

from .models import Announcement, Notification
from .serializers import AnnouncementSerializer, NotificationSerializer


class AnnouncementViewSet(viewsets.ModelViewSet):
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
        serializer.save(author=user)


class NotificationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Users see only their own notifications. Only admins can create them."""

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
        notification = self.get_object()
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return Response(self.get_serializer(notification).data)

    @action(detail=False, methods=["post"], url_path="read-all")
    def mark_all_read(self, request):
        updated = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({"updated": updated})