from django.conf import settings
from django.db import models
from django.utils import timezone


class Announcement(models.Model):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="announcements"
    )
    course = models.ForeignKey(
        "academics.Course",
        on_delete=models.CASCADE,
        related_name="announcements",
    )
    teacher = models.ForeignKey(
        "accounts.Teacher",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="announcements",
    )
    title = models.CharField(max_length=200)
    content = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "announcements"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    type = models.CharField(max_length=50, default="general")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user_id}: {self.title}"


class SystemSetting(models.Model):
    key = models.CharField(max_length=100, primary_key=True)
    value = models.TextField()
    updated_by = models.ForeignKey(
        "accounts.AdminProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="system_settings",
    )
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "system_settings"
        ordering = ["key"]

    def __str__(self):
        return self.key