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