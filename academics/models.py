from datetime import timedelta

from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class Course(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    class Visibility(models.TextChoices):
        PUBLIC = "public", "Public"
        PRIVATE = "private", "Private"

    title = models.CharField(max_length=200)
    grade = models.CharField(max_length=50)
    teacher = models.ForeignKey(
        "accounts.Teacher", on_delete=models.PROTECT, related_name="courses"
    )
    description = models.TextField(blank=True)
    visibility = models.CharField(
        max_length=20,
        choices=Visibility.choices,
        default=Visibility.PUBLIC,
    )
    course_limit = models.PositiveIntegerField(
        default=0,
        help_text="Maximum active enrollments; zero means unlimited.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    approved_by = models.ForeignKey(
        "accounts.AdminProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_courses",
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "courses"
        ordering = ["title", "id"]

    def __str__(self):
        return self.title


class Enrollment(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DROPPED = "dropped", "Dropped"
        COMPLETED = "completed", "Completed"

    student = models.ForeignKey(
        "accounts.Student", on_delete=models.CASCADE, related_name="enrollments"
    )
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="enrollments"
    )
    enrolled_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        db_table = "enrollments"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "course"], name="uniq_student_course_enrollment"
            )
        ]

    def __str__(self):
        return f"{self.student} -> {self.course}"

class Attendance(models.Model):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        LATE = "late", "Late"
        EXCUSED = "excused", "Excused"

    student = models.ForeignKey(
        "accounts.Student", on_delete=models.CASCADE, related_name="attendance"
    )
    live_session = models.ForeignKey(
        "LiveSession",
        on_delete=models.CASCADE,
        related_name="attendance",
        null=True,
        blank=True,
    )
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="attendance"
    )
    attendance_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PRESENT)
    joined_at = models.DateTimeField(null=True, blank=True)
    left_at = models.DateTimeField(null=True, blank=True)
    auto_marked = models.BooleanField(default=False)
    marked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "attendance"
        verbose_name_plural = "attendance"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "course", "attendance_date"],
                condition=Q(live_session__isnull=True),
                name="uniq_attendance_per_day",
            ),
            models.UniqueConstraint(
                fields=["student", "live_session"],
                condition=Q(live_session__isnull=False),
                name="uniq_student_live_session_attendance",
            ),
        ]

    def __str__(self):
        return f"{self.student} {self.attendance_date} {self.status}"


class LiveSession(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        LIVE = "live", "Live"
        ENDED = "ended", "Ended"
        CANCELLED = "cancelled", "Cancelled"

    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="live_sessions"
    )
    teacher = models.ForeignKey(
        "accounts.Teacher", on_delete=models.PROTECT, related_name="live_sessions"
    )
    title = models.CharField(max_length=200)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    meeting_url = models.URLField(blank=True)
    hms_room_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Room ID assigned by 100ms.",
    )
    tools_enabled = models.JSONField(default=list, blank=True)
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

    @property
    def join_deadline(self):
        return self.start_time + timedelta(minutes=15)

    @property
    def attendance_cutoff(self):
        return self.end_time - timedelta(minutes=15)


class HMSWebhookEvent(models.Model):
    event_id = models.CharField(max_length=100, primary_key=True)
    received_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "hms_webhook_events"


class Exam(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="exams",
    )
    title = models.CharField(max_length=200)
    exam_date = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField()
    total_marks = models.PositiveIntegerField()

    class Meta:
        db_table = "exams"
        ordering = ["exam_date", "id"]

    def __str__(self):
        return f"{self.title} ({self.course})"


class Grade(models.Model):
    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="grades",
    )
    student = models.ForeignKey(
        "accounts.Student",
        on_delete=models.CASCADE,
        related_name="exam_grades",
    )
    graded_by = models.ForeignKey(
        "accounts.Teacher",
        on_delete=models.PROTECT,
        related_name="grades_awarded",
    )
    score = models.DecimalField(max_digits=8, decimal_places=2)
    grade_letter = models.CharField(max_length=5, blank=True)
    teacher_feedback = models.TextField(blank=True)
    graded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "grades"
        constraints = [
            models.UniqueConstraint(
                fields=["exam", "student"],
                name="uniq_grade_per_exam_student",
            )
        ]

    def __str__(self):
        return f"{self.student} - {self.exam}: {self.score}"


class StudentFlag(models.Model):
    student = models.ForeignKey(
        "accounts.Student",
        on_delete=models.CASCADE,
        related_name="flags",
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="student_flags",
    )
    flagged_by = models.ForeignKey(
        "accounts.Teacher",
        on_delete=models.PROTECT,
        related_name="student_flags",
    )
    reason = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "student_flags"
        ordering = ["-created_at", "id"]

    def __str__(self):
        return f"{self.student} flagged in {self.course}"


SchoolClass = Course