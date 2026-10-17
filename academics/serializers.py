
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
            "school_class",
            "attendance_date",
            "status",
        ]
        read_only_fields = ["id"]


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
            "status",
        ]
        read_only_fields = ["id"]
        extra_kwargs = {
            "teacher": {"required": False},
        }

    def validate(self, attrs):
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
