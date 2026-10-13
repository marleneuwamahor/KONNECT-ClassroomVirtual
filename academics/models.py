from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class SchoolClass(models.Model):
    """CLASSES table. Named SchoolClass because `class` is a Python keyword."""

    name = models.CharField(max_length=150)
    grade = models.CharField(max_length=50)
    teacher = models.ForeignKey(
        "accounts.Teacher", on_delete=models.PROTECT, related_name="classes"
    )
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "classes"
        verbose_name_plural = "classes"

    def __str__(self):
        return f"{self.name} ({self.grade})"


class Enrollment(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DROPPED = "dropped", "Dropped"
        COMPLETED = "completed", "Completed"

    student = models.ForeignKey(
        "accounts.Student", on_delete=models.CASCADE, related_name="enrollments"
    )
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE, related_name="enrollments", db_column="class_id"
    )
    enrolled_at = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        db_table = "enrollments"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "school_class"], name="uniq_student_class_enrollment"
            )
        ]

    def __str__(self):
        return f"{self.student} -> {self.school_class}"