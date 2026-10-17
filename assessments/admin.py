from django.contrib import admin

from audit.admin_mixins import AuditAdminChangesMixin
from .models import Assignment,Submission


@admin.register(Assignment)
class AssignmentAdmin(AuditAdminChangesMixin, admin.ModelAdmin):
    list_display = ("title", "course", "type", "teacher", "due_at", "max_score")
    search_fields = ("title",)

@admin.register(Submission)
class SubmissionAdmin(AuditAdminChangesMixin, admin.ModelAdmin):
    list_display = ("assignment", "student", "submitted_at", "score")