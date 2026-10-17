from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)  # saved hashed in the `password` column
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.ADMIN)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        TEACHER = "teacher", "Teacher"
        STUDENT = "student", "Student"

    name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)                      # UK in the ERD
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    managed_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="managed_users",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)

    # profile columns (available to admin, teacher and student)
    profile_image = models.URLField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    bio = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        db_table = "users"

    def __str__(self):
        return f"{self.name} <{self.email}>"

class Student(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile")
    student_number = models.CharField(max_length=30, unique=True)
    profile_picture_url = models.URLField(blank=True)
    bio = models.TextField(blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    grade_level = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "students"

    def __str__(self):
        return f"{self.student_number} - {self.user.name}"


class Teacher(models.Model):
    class VerificationStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="teacher_profile")
    employee_number = models.CharField(
        max_length=30,
        unique=True,
        null=True,
        blank=True,
    )
    full_legal_name = models.CharField(max_length=200, blank=True)
    display_name = models.CharField(max_length=150, blank=True)
    phone_number = models.CharField(max_length=30, blank=True)
    country = models.CharField(max_length=100, blank=True)
    legal_name_on_documents = models.CharField(max_length=200, blank=True)
    cv_url = models.URLField(blank=True)
    degree_certificate_url = models.URLField(blank=True)
    profile_picture_url = models.URLField(blank=True)
    headline = models.CharField(max_length=200, blank=True)
    years_of_experience = models.CharField(max_length=50, blank=True)
    bio = models.TextField(blank=True)
    subjects_expertise = models.JSONField(default=list, blank=True)
    education_level_taught = models.CharField(max_length=150, blank=True)
    languages = models.JSONField(default=list, blank=True)
    current_institution = models.CharField(max_length=200, blank=True)
    teaching_mode = models.CharField(max_length=100, blank=True)
    portfolio_url = models.URLField(blank=True)
    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
    )
    verified_by = models.ForeignKey(
        "AdminProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="verified_teachers",
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "teachers"

    def __str__(self):
        return f"{self.employee_number} - {self.user.name}"


class AdminProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="admin_profile",
    )
    profile_picture_url = models.URLField(blank=True)
    admin_level = models.CharField(max_length=50, default="standard")

    class Meta:
        db_table = "admin_profiles"

    def __str__(self):
        return f"{self.admin_level}: {self.user.email}"


@receiver(post_save, sender=User)
def create_admin_profile(sender, instance, **kwargs):
    if instance.role == User.Role.ADMIN:
        AdminProfile.objects.get_or_create(user=instance)