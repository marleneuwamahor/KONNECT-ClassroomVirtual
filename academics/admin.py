from django.contrib import admin

from .models import Enrollment, SchoolClass

@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "school_class", "status", "enrolled_at")
    list_filter = ("status",)
    
@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ("name", "grade", "teacher", "created_at")
    list_filter = ("grade",)
    search_fields = ("name", "teacher__user__name")