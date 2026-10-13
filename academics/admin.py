from django.contrib import admin

from .models import Attendance, Enrollment,LiveSession, SchoolClass

@admin.register(LiveSession)
class LiveSessionAdmin(admin.ModelAdmin):
    list_display = ("title", "school_class", "teacher", "start_time", "status")
    list_filter = ("status",)

@admin.register(Attendance) 
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("student", "school_class", "attendance_date", "status")
    list_filter = ("status", "attendance_date")

@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "school_class", "status", "enrolled_at")
    list_filter = ("status",)

@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ("name", "grade", "teacher", "created_at")
    list_filter = ("grade",)
    search_fields = ("name", "teacher__user__name")
