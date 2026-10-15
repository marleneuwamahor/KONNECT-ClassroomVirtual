from rest_framework import serializers

from .models import Assignment, Submission


class AssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Assignment
        fields = ["id", "school_class", "teacher", "title", "description", "due_date", "created_at"]
        read_only_fields = ["id", "created_at"]
        extra_kwargs = {"teacher": {"required": False}}


class SubmissionSerializer(serializers.ModelSerializer):
    """What a student sends. Grade and feedback are read-only here."""

    class Meta:
        model = Submission
        fields = ["id", "assignment", "student", "submitted_at", "grade", "file_url", "feedback"]
        read_only_fields = ["id", "student", "submitted_at", "grade", "feedback"]


class GradeSerializer(serializers.ModelSerializer):
    """What a teacher or admin sends to grade a submission."""

    class Meta:
        model = Submission
        fields = ["grade", "feedback"]

    def validate_grade(self, value):
        if value is not None and not (0 <= value <= 100):
            raise serializers.ValidationError("Grade must be between 0 and 100.")
        return value