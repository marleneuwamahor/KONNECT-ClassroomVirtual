from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from .models import Student, Teacher, User

MAX_IMAGE_SIZE = 2 * 1024 * 1024  # 2 MB
ALLOWED_IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")


def check_image(value):
    if value.size > MAX_IMAGE_SIZE:
        raise serializers.ValidationError("Image must be 2 MB or smaller.")
    content_type = getattr(value, "content_type", None)
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise serializers.ValidationError("Only JPEG, PNG or WebP images are allowed.")
    return value


class UserSerializer(serializers.ModelSerializer):
    """Full user, used by admins."""

    password = serializers.CharField(write_only=True, required=False, validators=[validate_password])

    class Meta:
        model = User
        fields = [
            "id", "name", "email", "role", "profile_image", "phone", "bio",
            "is_active", "created_at", "password",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_profile_image(self, value):
        return check_image(value) if value else value

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

    class Meta:
        model = User
        fields = ["id", "name", "email", "role", "profile_image", "phone", "bio", "created_at"]
        read_only_fields = ["id", "email", "role", "created_at"]

    def validate_profile_image(self, value):
        return check_image(value) if value else value


class StudentSerializer(serializers.ModelSerializer):
    user_detail = UserSerializer(source="user", read_only=True)

    class Meta:
        model = Student
        fields = ["id", "user", "user_detail", "student_number", "date_of_birth", "created_at"]
        read_only_fields = ["id", "created_at"]


class TeacherSerializer(serializers.ModelSerializer):
    user_detail = UserSerializer(source="user", read_only=True)

    class Meta:
        model = Teacher
        fields = ["id", "user", "user_detail", "employee_number", "created_at"]
        read_only_fields = ["id", "created_at"]


class RegisterSerializer(serializers.Serializer):
    """Public sign-up. Always creates a STUDENT account plus its Student profile."""

    name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    student_number = serializers.CharField(max_length=30)
    date_of_birth = serializers.DateField(required=False, allow_null=True)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_student_number(self, value):
        if Student.objects.filter(student_number=value).exists():
            raise serializers.ValidationError("This student number is already registered.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        student_number = validated_data.pop("student_number")
        dob = validated_data.pop("date_of_birth", None)
        user = User.objects.create_user(role=User.Role.STUDENT, **validated_data)
        Student.objects.create(user=user, student_number=student_number, date_of_birth=dob)
        return user