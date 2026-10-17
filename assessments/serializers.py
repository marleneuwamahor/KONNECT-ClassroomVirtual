from rest_framework import serializers

from academics.models import Course

from .models import Assignment, Submission


class AssignmentSerializer(serializers.ModelSerializer):
    """Course quiz/exercise schedule and maximum achievable score."""

    due_date = serializers.DateTimeField(source="due_at", required=False)
    school_class = serializers.PrimaryKeyRelatedField(
        source="course",
        queryset=Course.objects.all(),
        required=False,
    )

    class Meta:
        model = Assignment
        fields = [
            "id",
            "course",
            "school_class",
            "teacher",
            "title",
            "description",
            "type",
            "max_score",
            "due_at",
            "due_date",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
        extra_kwargs = {
            "teacher": {"required": False},
            "course": {"required": False},
            "due_at": {"required": False},
        }

    def validate(self, attrs):
        if not attrs.get("course", getattr(self.instance, "course", None)):
            raise serializers.ValidationError({"course": "This field is required."})
        if not attrs.get("due_at", getattr(self.instance, "due_at", None)):
            raise serializers.ValidationError({"due_at": "This field is required."})
        if attrs.get("max_score", getattr(self.instance, "max_score", 100)) <= 0:
            raise serializers.ValidationError({"max_score": "Maximum score must be positive."})
        return attrs


class SubmissionSerializer(serializers.ModelSerializer):
    """Student answers and files, with legacy grade/feedback response aliases."""

    grade = serializers.DecimalField(
        source="score",
        max_digits=8,
        decimal_places=2,
        read_only=True,
    )
    feedback = serializers.CharField(source="teacher_feedback", read_only=True)

    class Meta:
        model = Submission
        fields = [
            "id", "assignment", "student", "submitted_at", "answers", "score",
            "grade", "file_url", "teacher_feedback", "feedback",
        ]
        read_only_fields = [
            "id", "student", "submitted_at", "score", "grade",
            "teacher_feedback", "feedback",
        ]


class SubmissionGradeSerializer(serializers.ModelSerializer):
    """Teacher score and feedback, accepting legacy grade/feedback input names."""

    grade = serializers.DecimalField(
        source="score",
        max_digits=8,
        decimal_places=2,
        required=False,
    )
    feedback = serializers.CharField(
        source="teacher_feedback",
        required=False,
    )

    class Meta:
        model = Submission
        fields = [
            "score", "grade", "teacher_feedback", "feedback",
        ]

    def validate(self, attrs):
        score = attrs.get("score", getattr(self.instance, "score", None))
        assignment = getattr(self.instance, "assignment", None)
        if score is not None:
            if score < 0:
                raise serializers.ValidationError({"score": "Score cannot be negative."})
            if assignment and score > assignment.max_score:
                raise serializers.ValidationError(
                    {"score": "Score cannot exceed the assignment's maximum score."}
                )
        return attrs