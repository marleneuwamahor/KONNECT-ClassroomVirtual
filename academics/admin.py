from django.contrib import admin

from .models import Attendance, Course, Enrollment, LiveSession

@admin.register(LiveSession)
class LiveSessionAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "teacher", "start_time", "status")
    list_filter = ("status",)

@admin.register(Attendance) 
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("student", "course", "attendance_date", "status")
    list_filter = ("status", "attendance_date")

@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "course", "status", "enrolled_at")
    list_filter = ("status",)

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("title", "teacher", "status", "visibility", "created_at")
    list_filter = ("status", "visibility")
    search_fields = ("title", "teacher__user__name")
