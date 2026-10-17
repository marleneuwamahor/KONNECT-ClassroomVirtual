from django.db import models
from django.utils import timezone


class Assignment(models.Model):
    class Type(models.TextChoices):
        QUIZ = "quiz", "Quiz"
        EXERCISE = "exercise", "Exercise"

    course = models.ForeignKey(
        "academics.Course",
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    teacher = models.ForeignKey(
        "accounts.Teacher", on_delete=models.PROTECT, related_name="assignments"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.EXERCISE)
    due_at = models.DateTimeField()
    max_score = models.PositiveIntegerField(default=100)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "assignments"

    def __str__(self):
        return self.title

    @property
    def due_date(self):
        return self.due_at

    @due_date.setter
    def due_date(self, value):
        self.due_at = value


class Submission(models.Model):
    assignment = models.ForeignKey(
        Assignment, on_delete=models.CASCADE, related_name="submissions"
    )
    student = models.ForeignKey(
        "accounts.Student", on_delete=models.CASCADE, related_name="submissions"
    )
    submitted_at = models.DateTimeField(default=timezone.now)
    answers = models.JSONField(default=dict, blank=True)
    score = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    file_url = models.URLField(blank=True)
    teacher_feedback = models.TextField(blank=True)

    class Meta:
        db_table = "submissions"
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "student"], name="uniq_submission_per_student"
            )
        ]

    def __str__(self):
        return f"{self.student} -> {self.assignment}"

    @property
    def grade(self):
        return self.score

    @grade.setter
    def grade(self, value):
        self.score = value

    @property
    def feedback(self):
        return self.teacher_feedback

    @feedback.setter
    def feedback(self, value):
        self.teacher_feedback = value