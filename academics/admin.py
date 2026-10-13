from django.contrib import admin

from .models import SchoolClass


@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ("name", "grade", "teacher", "created_at")
    list_filter = ("grade",)
    search_fields = ("name", "teacher__user__name")