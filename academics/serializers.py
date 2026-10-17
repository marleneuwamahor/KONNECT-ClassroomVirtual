
from rest_framework import serializers

from .models import Attendance, Course, Enrollment, LiveSession


class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = [
            "id",
            "title",
            "teacher",
            "description",
            "visibility",
            "course_limit",
            "status",
            "approved_by",
            "created_at",
        ]
        read_only_fields = ["id", "status", "approved_by", "created_at"]
        extra_kwargs = {
            "teacher": {"required": False},
        }

    def validate_course_limit(self, value):
        if value < 0:
            raise serializers.ValidationError("Course limit cannot be negative.")
        return value


class SchoolClassSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="title", max_length=200)

    class Meta:
        model = Course
        fields = ["id", "name", "grade", "teacher", "description", "created_at"]
        read_only_fields = ["id", "created_at"]
        extra_kwargs = {"teacher": {"required": False}}


class EnrollmentSerializer(serializers.ModelSerializer):
    school_class = serializers.PrimaryKeyRelatedField(
        source="course",
        queryset=Course.objects.all(),
        required=False,
    )

    class Meta:
        model = Enrollment
        fields = [
            "id",
            "student",
            "course",
            "school_class",
            "enrolled_at",
            "status",
        ]
        read_only_fields = ["id"]
        extra_kwargs = {"course": {"required": False}}
        validators = []

    def validate(self, attrs):
        course = attrs.get("course", getattr(self.instance, "course", None))
        student = attrs.get("student", getattr(self.instance, "student", None))
        if not course:
            raise serializers.ValidationError(
                {"course": "This field is required."}
            )
        if student and Enrollment.objects.filter(
            student=student,
            course=course,
        ).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise serializers.ValidationError(
                {"course": "This student is already enrolled in the course."}
            )
        return attrs


class AttendanceSerializer(serializers.ModelSerializer):
    school_class = serializers.PrimaryKeyRelatedField(
        source="course",
        queryset=Course.objects.all(),
        required=False,
    )

    class Meta:
        model = Attendance
        fields = [
            "id",
            "student",
            "live_session",
            "course",
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
        extra_kwargs = {"course": {"required": False}}
        validators = []

    def validate(self, attrs):
        course = attrs.get("course", getattr(self.instance, "course", None))
        student = attrs.get("student", getattr(self.instance, "student", None))
        live_session = attrs.get(
            "live_session", getattr(self.instance, "live_session", None)
        )
        attendance_date = attrs.get(
            "attendance_date",
            getattr(self.instance, "attendance_date", None),
        )
        if not course:
            raise serializers.ValidationError(
                {"course": "This field is required."}
            )
        duplicate = Attendance.objects.filter(student=student)
        if self.instance:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if live_session:
            duplicate = duplicate.filter(live_session=live_session)
        elif attendance_date:
            duplicate = duplicate.filter(
                live_session__isnull=True,
                course=course,
                attendance_date=attendance_date,
            )
        if student and duplicate.exists():
            raise serializers.ValidationError(
                {"student": "Attendance has already been recorded for this session or date."}
            )
        return attrs


class LiveSessionSerializer(serializers.ModelSerializer):
    school_class = serializers.PrimaryKeyRelatedField(
        source="course",
        queryset=Course.objects.all(),
        required=False,
    )

    class Meta:
        model = LiveSession
        fields = [
            "id",
            "course",
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
            "course": {"required": False},
        }

    def validate(self, attrs):
        course = attrs.get("course", getattr(self.instance, "course", None))
        if not course:
            raise serializers.ValidationError({"course": "This field is required."})
        teacher = attrs.get("teacher", getattr(self.instance, "teacher", None))
        if course and teacher and course.teacher_id != teacher.id:
            raise serializers.ValidationError({
                "teacher": "The session teacher must be assigned to the selected course."
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
