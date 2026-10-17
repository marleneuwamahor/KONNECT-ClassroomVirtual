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
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user_id}: {self.title}"