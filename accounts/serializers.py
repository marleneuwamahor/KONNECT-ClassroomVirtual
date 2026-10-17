from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field

from .models import AdminProfile, Student, Teacher, User


@extend_schema_field(OpenApiTypes.STR)
class UserStatusField(serializers.Field):
    def to_representation(self, value):
        return "active" if value else "inactive"

    def to_internal_value(self, data):
        if data not in ("active", "inactive"):
            raise serializers.ValidationError("Choose 'active' or 'inactive'.")
        return data == "active"


class UserSerializer(serializers.ModelSerializer):
    """Full user, used by admins."""

    password = serializers.CharField(write_only=True, required=False, validators=[validate_password])
    full_name = serializers.CharField(source="name", required=False)
    status = UserStatusField(source="is_active", required=False)

    class Meta:
        model = User
        fields = [
            "id", "name", "full_name", "email", "role", "status",
            "managed_by", "profile_image", "phone", "bio", "is_active",
            "created_at", "password",
        ]
        read_only_fields = ["id", "managed_by", "is_active", "created_at"]
        extra_kwargs = {"name": {"required": False}}

    def validate(self, attrs):
        full_name = self.initial_data.get("full_name")
        legacy_name = self.initial_data.get("name")
        if full_name and legacy_name and full_name != legacy_name:
            raise serializers.ValidationError(
                {"full_name": "Use the same value as the legacy name field."}
            )
        if full_name:
            attrs["name"] = full_name
        if not attrs.get("name", getattr(self.instance, "name", None)):
            raise serializers.ValidationError({"full_name": "This field is required."})
        return attrs

    def create(self, validated_data):
        if not validated_data.get("password"):
            raise serializers.ValidationError({"password": "This field is required."})
        return User.objects.create_user(**validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        instance = super().update(instance, validated_data)
        if password:
            instance.set_password(password)
            instance.save(update_fields=["password"])
        return instance


class MeSerializer(serializers.ModelSerializer):
    """What a user can see and edit about themselves. Role and email are read-only."""

    full_name = serializers.CharField(source="name", required=False)
    status = UserStatusField(source="is_active", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "name", "full_name", "email", "role", "status",
            "profile_image", "phone", "bio", "created_at",
        ]
        read_only_fields = ["id", "email", "role", "status", "created_at"]
        extra_kwargs = {"name": {"required": False}}

    def validate(self, attrs):
        full_name = self.initial_data.get("full_name")
        legacy_name = self.initial_data.get("name")
        if full_name and legacy_name and full_name != legacy_name:
            raise serializers.ValidationError(
                {"full_name": "Use the same value as the legacy name field."}
            )
        if full_name:
            attrs["name"] = full_name
        return attrs

class StudentSerializer(serializers.ModelSerializer):
    user_detail = UserSerializer(source="user", read_only=True)
    username = serializers.CharField(source="student_number", required=False)
    student_number = serializers.CharField(read_only=True)

    class Meta:
        model = Student
        fields = [
            "id", "user", "user_detail", "username", "student_number",
            "profile_picture_url", "bio", "date_of_birth", "grade_level", "created_at",
        ]
        read_only_fields = ["id", "student_number", "created_at"]

    def validate(self, attrs):
        username = attrs.get("student_number")
        if username and Student.objects.filter(student_number=username).exclude(
            pk=getattr(self.instance, "pk", None)
        ).exists():
            raise serializers.ValidationError({"username": "This username is already in use."})
        if not username and self.instance is None:
            raise serializers.ValidationError({"username": "This field is required."})
        return attrs


class TeacherSerializer(serializers.ModelSerializer):
    user_detail = UserSerializer(source="user", read_only=True)

    class Meta:
        model = Teacher
        fields = [
            "id", "user", "user_detail", "employee_number", "full_legal_name",
            "display_name", "phone_number", "country", "legal_name_on_documents",
            "cv_url", "degree_certificate_url", "profile_picture_url", "headline",
            "years_of_experience", "bio", "subjects_expertise",
            "education_level_taught", "languages", "current_institution",
            "teaching_mode", "portfolio_url", "verification_status",
            "verified_by", "created_at",
        ]
        read_only_fields = [
            "id", "verification_status", "verified_by", "created_at",
        ]

    def validate_user(self, value):
        if value.role != User.Role.TEACHER:
            raise serializers.ValidationError("Teacher profiles require a teacher account.")
        request = self.context.get("request")
        if (
            self.instance
            and request
            and request.user.role == User.Role.TEACHER
            and value.pk != self.instance.user_id
        ):
            raise serializers.ValidationError("Teachers cannot reassign their user account.")
        return value


class TeacherDirectorySerializer(serializers.ModelSerializer):
    """Fields safe to expose in the authenticated teacher directory."""

    class Meta:
        model = Teacher
        fields = [
            "id", "display_name", "profile_picture_url", "headline",
            "years_of_experience", "bio", "subjects_expertise",
            "education_level_taught", "languages", "current_institution",
            "teaching_mode", "portfolio_url", "verification_status",
        ]


class StudentProfileSerializer(serializers.ModelSerializer):
    """A student may update only the profile details on their own student record."""

    username = serializers.CharField(source="student_number", read_only=True)

    class Meta:
        model = Student
        fields = [
            "id", "username", "profile_picture_url", "bio", "date_of_birth",
            "grade_level", "created_at",
        ]
        read_only_fields = ["id", "username", "created_at"]


class AdminProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminProfile
        fields = ["id", "user", "profile_picture_url", "admin_level"]
        read_only_fields = ["id", "user"]

    def validate_user(self, value):
        if value.role != User.Role.ADMIN:
            raise serializers.ValidationError("Admin profiles require an admin account.")
        return value


class RegisterSerializer(serializers.Serializer):
    """Public sign-up. Always creates a STUDENT account plus its Student profile."""

    name = serializers.CharField(max_length=150, required=False)
    full_name = serializers.CharField(max_length=150, required=False)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    username = serializers.CharField(max_length=30, required=False)
    student_number = serializers.CharField(max_length=30, required=False, write_only=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_student_number(self, value):
        if Student.objects.filter(student_number=value).exists():
            raise serializers.ValidationError("This student number is already registered.")
        return value

    def validate_username(self, value):
        if Student.objects.filter(student_number=value).exists():
            raise serializers.ValidationError("This username is already registered.")
        return value

    def validate(self, attrs):
        full_name = attrs.get("full_name")
        name = attrs.get("name")
        if full_name and name and full_name != name:
            raise serializers.ValidationError(
                {"full_name": "Use the same value as the legacy name field."}
            )
        if full_name:
            attrs["name"] = full_name
        if not attrs.get("name"):
            raise serializers.ValidationError({"full_name": "This field is required."})
        username = attrs.get("username")
        student_number = attrs.get("student_number")
        if username and student_number and username != student_number:
            raise serializers.ValidationError(
                {"username": "Use the same value as student_number when both are provided."}
            )
        if not username and not student_number:
            raise serializers.ValidationError({"username": "This field is required."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        validated_data.pop("full_name", None)
        student_number = validated_data.pop(
            "username",
            validated_data.pop("student_number", None),
        )
        validated_data.pop("student_number", None)
        dob = validated_data.pop("date_of_birth", None)
        user = User.objects.create_user(role=User.Role.STUDENT, **validated_data)
        Student.objects.create(user=user, student_number=student_number, date_of_birth=dob)
        return user