
from rest_framework import serializers

from .models import Attendance, Course, Enrollment, Exam, Grade, LiveSession, StudentFlag


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


class ExamSerializer(serializers.ModelSerializer):
    """Exam schedule and maximum mark for a course."""

    class Meta:
        model = Exam
        fields = [
            "id",
            "course",
            "title",
            "exam_date",
            "duration_minutes",
            "total_marks",
        ]
        read_only_fields = ["id"]

    def validate_duration_minutes(self, value):
        if value <= 0:
            raise serializers.ValidationError("Duration must be greater than zero.")
        return value

    def validate_total_marks(self, value):
        if value <= 0:
            raise serializers.ValidationError("Total marks must be greater than zero.")
        return value


class ExamGradeSerializer(serializers.ModelSerializer):
    """A student's result for one exam; grade letters are entered by the teacher."""

    class Meta:
        model = Grade
        fields = [
            "id",
            "exam",
            "student",
            "graded_by",
            "score",
            "grade_letter",
            "teacher_feedback",
            "graded_at",
        ]
        read_only_fields = ["id", "graded_by", "graded_at"]

    def validate(self, attrs):
        exam = attrs.get("exam", getattr(self.instance, "exam", None))
        score = attrs.get("score", getattr(self.instance, "score", None))
        if exam and score is not None and score > exam.total_marks:
            raise serializers.ValidationError(
                {"score": "Score cannot exceed the exam's total marks."}
            )
        return attrs


class StudentFlagSerializer(serializers.ModelSerializer):
    """A teacher's reason for flagging a student in one course."""

    class Meta:
        model = StudentFlag
        fields = [
            "id",
            "student",
            "course",
            "flagged_by",
            "reason",
            "created_at",
        ]
        read_only_fields = ["id", "flagged_by", "created_at"]


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
    """Schedule a course session and expose the deadline and attendance cutoff."""

    school_class = serializers.PrimaryKeyRelatedField(
        source="course",
        queryset=Course.objects.all(),
        required=False,
    )
    join_link = serializers.URLField(source="meeting_url", required=False)
    starts_at = serializers.DateTimeField(source="start_time", required=False)
    ends_at = serializers.DateTimeField(source="end_time", required=False)
    join_deadline = serializers.DateTimeField(read_only=True)
    attendance_cutoff = serializers.DateTimeField(read_only=True)

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
            "starts_at",
            "ends_at",
            "meeting_url",
            "join_link",
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
            "start_time": {"required": False},
            "end_time": {"required": False},
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

        if not start_time:
            raise serializers.ValidationError({"starts_at": "This field is required."})
        if not end_time:
            raise serializers.ValidationError({"ends_at": "This field is required."})
        if start_time and end_time and end_time <= start_time:
            raise serializers.ValidationError({
                "end_time": "End time must be after start time."
            })

        return attrs
