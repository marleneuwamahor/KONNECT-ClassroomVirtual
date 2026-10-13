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

class Attendance(models.Model):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        LATE = "late", "Late"
        EXCUSED = "excused", "Excused"

    student = models.ForeignKey(
        "accounts.Student", on_delete=models.CASCADE, related_name="attendance"
    )
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE, related_name="attendance", db_column="class_id"
    )
    attendance_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PRESENT)

    class Meta:
        db_table = "attendance"
        verbose_name_plural = "attendance"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "school_class", "attendance_date"],
                name="uniq_attendance_per_day",
            )
        ]

    def __str__(self):
        return f"{self.student} {self.attendance_date} {self.status}"


class LiveSession(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        LIVE = "live", "Live"
        ENDED = "ended", "Ended"
        CANCELLED = "cancelled", "Cancelled"

    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE, related_name="live_sessions", db_column="class_id"
    )
    teacher = models.ForeignKey(
        "accounts.Teacher", on_delete=models.PROTECT, related_name="live_sessions"
    )
    title = models.CharField(max_length=200)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    meeting_url = models.URLField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)

    class Meta:
        db_table = "live_sessions"
        constraints = [
            models.CheckConstraint(
                condition=Q(end_time__gt=F("start_time")),
                name="live_session_end_after_start",
            )
        ]

    def __str__(self):
        return f"{self.title} ({self.start_time:%Y-%m-%d %H:%M})"