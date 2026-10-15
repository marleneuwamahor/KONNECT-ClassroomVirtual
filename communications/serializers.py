from rest_framework import serializers

from .models import Announcement, Notification


class AnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = ["id", "author", "school_class", "title", "content", "created_at"]
        read_only_fields = ["id", "author", "created_at"]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "user", "title", "message", "is_read", "created_at"]
        read_only_fields = ["id", "created_at"]