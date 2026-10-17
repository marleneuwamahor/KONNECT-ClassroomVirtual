from rest_framework import serializers

from academics.models import Course

from .models import Announcement, Notification, SystemSetting


class AnnouncementSerializer(serializers.ModelSerializer):
    school_class = serializers.PrimaryKeyRelatedField(
        source="course",
        queryset=Course.objects.all(),
        required=False,
    )

    class Meta:
        model = Announcement
        fields = [
            "id",
            "author",
            "course",
            "teacher",
            "school_class",
            "title",
            "content",
            "created_at",
        ]
        read_only_fields = ["id", "author", "teacher", "created_at"]
        extra_kwargs = {"course": {"required": False}}

    def validate(self, attrs):
        if not attrs.get("course", getattr(self.instance, "course", None)):
            raise serializers.ValidationError({"course": "This field is required."})
        return attrs


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "user", "title", "message", "type", "is_read", "created_at"]
        read_only_fields = ["id", "created_at"]


class SystemSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemSetting
        fields = ["key", "value", "updated_by", "updated_at"]
        read_only_fields = ["updated_by", "updated_at"]