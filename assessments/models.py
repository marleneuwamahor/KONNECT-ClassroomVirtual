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