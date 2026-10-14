from django.contrib import admin

from .models import Assignment,Submission


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("title", "school_class", "teacher", "due_date")
    search_fields = ("title",)

@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("assignment", "student", "submitted_at", "grade")