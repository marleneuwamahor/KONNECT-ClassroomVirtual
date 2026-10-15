"""Role-based queryset filtering shared by all apps.

admin   -> everything
teacher -> data belonging to classes they teach
student -> their own data / classes they are enrolled in
"""
from .models import User


def is_admin(user):
    return user.is_superuser or user.role == User.Role.ADMIN


def student_scoped(qs, user, student="student", class_path="school_class"):
    """For tables that have a student column (enrollments, attendance, submissions, ...)."""
    if is_admin(user):
        return qs
    if user.role == User.Role.TEACHER:
        return qs.filter(**{f"{class_path}__teacher__user": user})
    return qs.filter(**{f"{student}__user": user})


def class_scoped(qs, user, class_path="school_class"):
    """For tables that belong to a class (assignments, announcements, live sessions)."""
    if is_admin(user):
        return qs
    if user.role == User.Role.TEACHER:
        return qs.filter(**{f"{class_path}__teacher__user": user})
    return qs.filter(**{f"{class_path}__enrollments__student__user": user}).distinct()