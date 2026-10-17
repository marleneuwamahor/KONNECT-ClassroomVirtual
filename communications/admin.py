from django.contrib import admin

from audit.admin_mixins import AuditAdminChangesMixin
from .models import Announcement, Notification


@admin.register(Announcement)
class AnnouncementAdmin(AuditAdminChangesMixin, admin.ModelAdmin):
    list_display = ("title", "course", "author", "created_at")


@admin.register(Notification)
class NotificationAdmin(AuditAdminChangesMixin, admin.ModelAdmin):
    list_display = ("user", "title", "is_read", "created_at")
    list_filter = ("is_read",)