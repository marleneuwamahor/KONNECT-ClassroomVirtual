from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from audit.admin_mixins import AuditAdminChangesMixin
from .models import AdminProfile, Student, Teacher, User


@admin.register(User)
class UserAdmin(AuditAdminChangesMixin, BaseUserAdmin):
    ordering = ("email",)
    list_display = ("email", "name", "role", "is_active", "created_at")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("email", "name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("name", "role", "profile_image", "phone", "bio")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": (
            "email", "name", "role", "phone", "password1", "password2",
        )}),
    )

    def save_model(self, request, obj, form, change):
        if not change and request.user.role == User.Role.ADMIN:
            obj.managed_by = request.user.admin_profile
        super().save_model(request, obj, form, change)


@admin.register(Student)
class StudentAdmin(AuditAdminChangesMixin, admin.ModelAdmin):
    list_display = ("student_number", "user", "date_of_birth")
    search_fields = ("student_number", "user__email", "user__name")


@admin.register(Teacher)
class TeacherAdmin(AuditAdminChangesMixin, admin.ModelAdmin):
    list_display = ("employee_number", "user")
    search_fields = ("employee_number", "user__email", "user__name")


@admin.register(AdminProfile)
class AdminProfileAdmin(AuditAdminChangesMixin, admin.ModelAdmin):
    list_display = ("user", "admin_level")
    search_fields = ("user__email", "user__name")