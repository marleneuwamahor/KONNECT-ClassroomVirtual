
from rest_framework import serializers

from .models import Attendance, Enrollment, LiveSession, SchoolClass


class SchoolClassSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchoolClass
        fields = [
            "id",
            "name",
            "grade",
            "teacher",
            "description",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
        extra_kwargs = {
            "teacher": {"required": False},
        }


class EnrollmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Enrollment
        fields = [
            "id",
            "student",
            "school_class",
            "enrolled_at",
            "status",
        ]
        read_only_fields = ["id"]


class AttendanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attendance
        fields = [
            "id",
            "student",
            "live_session",
            "school_class",
            "attendance_date",
            "status",
            "joined_at",
            "left_at",
            "auto_marked",
            "marked_at",
        ]
        read_only_fields = [
            "id",
            "live_session",
            "joined_at",
            "left_at",
            "auto_marked",
            "marked_at",
        ]


class LiveSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = LiveSession
        fields = [
            "id",
            "school_class",
            "teacher",
            "title",
            "start_time",
            "end_time",
            "meeting_url",
            "hms_room_id",
            "tools_enabled",
            "join_deadline",
            "attendance_cutoff",
            "status",
        ]
        read_only_fields = ["id", "hms_room_id", "join_deadline", "attendance_cutoff"]
        extra_kwargs = {
            "teacher": {"required": False},
        }

    def validate(self, attrs):
        school_class = attrs.get(
            "school_class",
            getattr(self.instance, "school_class", None),
        )
        teacher = attrs.get("teacher", getattr(self.instance, "teacher", None))
        if school_class and teacher and school_class.teacher_id != teacher.id:
            raise serializers.ValidationError({
                "teacher": "The session teacher must be assigned to the selected class."
            })

        start_time = attrs.get(
            "start_time",
            getattr(self.instance, "start_time", None),
        )
        end_time = attrs.get(
            "end_time",
            getattr(self.instance, "end_time", None),
        )

        if start_time and end_time and end_time <= start_time:
            raise serializers.ValidationError({
                "end_time": "End time must be after start time."
            })

        return attrs
