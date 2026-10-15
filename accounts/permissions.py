from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import User


def role_of(request):
    user = request.user
    return user.role if user and user.is_authenticated else None


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        return role_of(request) == User.Role.ADMIN


class IsTeacherOrAdmin(BasePermission):
    def has_permission(self, request, view):
        return role_of(request) in (User.Role.TEACHER, User.Role.ADMIN)


class IsStudentRole(BasePermission):
    def has_permission(self, request, view):
        return role_of(request) == User.Role.STUDENT


class IsAdminOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return role_of(request) == User.Role.ADMIN


class IsTeacherOrAdminOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return role_of(request) in (User.Role.TEACHER, User.Role.ADMIN)