from django.db import models
from django.utils import timezone


class Assignment(models.Model):
    school_class = models.ForeignKey(
        "academics.SchoolClass",
        on_delete=models.CASCADE,
        related_name="assignments",
        db_column="class_id",
    )
    teacher = models.ForeignKey(
        "accounts.Teacher", on_delete=models.PROTECT, related_name="assignments"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateTimeField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "assignments"

    def __str__(self):
        return self.title

class Submission(models.Model):
    assignment = models.ForeignKey(
        Assignment, on_delete=models.CASCADE, related_name="submissions"
    )
    student = models.ForeignKey(
        "accounts.Student", on_delete=models.CASCADE, related_name="submissions"
    )
    submitted_at = models.DateTimeField(default=timezone.now)
    grade = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    file_url = models.URLField(blank=True)
    feedback = models.TextField(blank=True)

    class Meta:
        db_table = "submissions"
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "student"], name="uniq_submission_per_student"
            )
        ]

    def __str__(self):
        return f"{self.student} -> {self.assignment}"