import logging

from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from audit.mixins import AuditAdminWritesMixin
from .models import AdminProfile, Student, Teacher, User
from .permissions import IsAdminRole, IsTeacherOrAdmin
from .serializers import (
    AdminProfileSerializer,
    MeSerializer,
    ProfileImageUploadResponseSerializer,
    ProfileImageUploadSerializer,
    RegisterSerializer,
    StudentSerializer,
    StudentProfileSerializer,
    TeacherDirectorySerializer,
    TeacherSerializer,
    UserSerializer,
)
from .services.profile_image_storage import (
    ProfileImageStorageError,
    upload_profile_image,
)
from audit.utils import log_action

logger = logging.getLogger(__name__)


class ProfileImageStorageUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Profile image storage is unavailable. Try again later."
    default_code = "profile_image_storage_unavailable"


class RegisterView(generics.CreateAPIView):
    """Create a student account and profile using username/student_number and credentials."""

    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            user = serializer.save()
            if getattr(request.user, "role", None) == User.Role.ADMIN:
                user.managed_by = request.user.admin_profile
                user.save(update_fields=["managed_by"])
                log_action(request, "register", "user", user.pk)
        return Response(MeSerializer(user, context={"request": request}).data, status=201)


class UserViewSet(AuditAdminWritesMixin, viewsets.ModelViewSet):
    """Admin user management plus the authenticated user's own profile endpoint."""

    queryset = User.objects.all().order_by("id")
    serializer_class = UserSerializer
    permission_classes = [IsAdminRole]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filterset_fields = ["role", "is_active"]
    search_fields = ["name", "email"]

    def perform_create(self, serializer):
        serializer.save(managed_by=self.request.user.admin_profile)

    @action(
        detail=False,
        methods=["get", "patch"],
        permission_classes=[permissions.IsAuthenticated],
        parser_classes=[MultiPartParser, FormParser, JSONParser],
    )
    def me(self, request):
        """Return or partially update the authenticated user's profile."""
        if request.method == "PATCH":
            serializer = MeSerializer(
                request.user, data=request.data, partial=True, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        return Response(MeSerializer(request.user, context={"request": request}).data)

    @extend_schema(
        request=ProfileImageUploadSerializer,
        responses={200: ProfileImageUploadResponseSerializer},
        description=(
            "Upload a JPEG, PNG, or WebP profile image (maximum 5 MB) as multipart "
            "form data. The image is stored in Cloudinary and its URL is applied to "
            "the signed-in user's profile and role-specific profile."
        ),
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="me/profile-image",
        permission_classes=[permissions.IsAuthenticated],
        parser_classes=[MultiPartParser],
    )
    def upload_profile_image(self, request):
        """Upload and save the authenticated user's profile photo."""
        serializer = ProfileImageUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            image_url = upload_profile_image(
                serializer.validated_data["image"],
                user_id=request.user.pk,
            )
        except (ProfileImageStorageError, ImproperlyConfigured) as exc:
            logger.error(
                "Profile image upload failed for user %s (%s).",
                request.user.pk,
                type(exc).__name__,
            )
            raise ProfileImageStorageUnavailable() from exc

        with transaction.atomic():
            User.objects.filter(pk=request.user.pk).update(profile_image=image_url)
            if request.user.role == User.Role.STUDENT:
                Student.objects.filter(user=request.user).update(
                    profile_picture_url=image_url
                )
            elif request.user.role == User.Role.TEACHER:
                Teacher.objects.filter(user=request.user).update(
                    profile_picture_url=image_url
                )
            elif request.user.role == User.Role.ADMIN:
                AdminProfile.objects.filter(user=request.user).update(
                    profile_picture_url=image_url
                )

        return Response(
            {
                "profile_image": image_url,
                "profile_picture_url": image_url,
            }
        )


class StudentViewSet(AuditAdminWritesMixin, viewsets.ModelViewSet):
    """Manage student profiles; students may read or edit only their own profile."""

    serializer_class = StudentSerializer
    search_fields = ["student_number", "user__name", "user__email", "grade_level"]

    def get_queryset(self):
        queryset = Student.objects.select_related("user").order_by("id")
        if self.request.user.role == User.Role.STUDENT:
            return queryset.filter(user=self.request.user)
        if self.request.user.role in (User.Role.TEACHER, User.Role.ADMIN):
            return queryset
        return queryset.none()

    def get_serializer_class(self):
        if self.action == "me":
            return StudentProfileSerializer
        return super().get_serializer_class()

    def get_permissions(self):
        if self.action == "me":
            return [permissions.IsAuthenticated()]
        if self.action in ("list", "retrieve"):
            return [IsTeacherOrAdmin()]
        return [IsAdminRole()]

    @action(detail=False, methods=["get", "patch"], url_path="me")
    def me(self, request):
        """Return or partially update the signed-in student's academic profile."""
        if request.user.role != User.Role.STUDENT:
            raise PermissionDenied("Only students have a student profile endpoint.")
        student = get_object_or_404(self.get_queryset(), user=request.user)
        if request.method == "PATCH":
            serializer = self.get_serializer(
                student,
                data=request.data,
                partial=True,
                context=self.get_serializer_context(),
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        return Response(self.get_serializer(student).data)


class TeacherViewSet(AuditAdminWritesMixin, viewsets.ModelViewSet):
    """Teacher directory, private profile management and admin verification workflow."""

    serializer_class = TeacherSerializer
    search_fields = ["employee_number", "display_name", "subjects_expertise"]

    def get_queryset(self):
        queryset = Teacher.objects.select_related(
            "user", "verified_by__user"
        ).order_by("id")
        if self.request.user.role == User.Role.ADMIN:
            return queryset
        if self.request.user.role == User.Role.TEACHER:
            return queryset.filter(user=self.request.user)
        if self.request.user.role == User.Role.STUDENT:
            return queryset.filter(
                verification_status=Teacher.VerificationStatus.VERIFIED
            )
        return queryset.none()

    def get_serializer_class(self):
        if (
            self.action in ("list", "retrieve")
            and getattr(self.request.user, "role", None) != User.Role.ADMIN
        ):
            return TeacherDirectorySerializer
        return super().get_serializer_class()

    def get_permissions(self):
        if self.action == "me":
            return [permissions.IsAuthenticated()]
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated()]
        return [IsAdminRole()]

    def perform_create(self, serializer):
        user = serializer.validated_data["user"]
        serializer.save(
            full_legal_name=(
                serializer.validated_data.get("full_legal_name") or user.name
            ),
            display_name=(
                serializer.validated_data.get("display_name") or user.name
            ),
            phone_number=(
                serializer.validated_data.get("phone_number") or user.phone
            ),
            profile_picture_url=(
                serializer.validated_data.get("profile_picture_url")
                or user.profile_image
            ),
            bio=serializer.validated_data.get("bio") or user.bio,
        )

    @action(detail=False, methods=["get", "patch"], url_path="me")
    def me(self, request):
        """Return or partially update the signed-in teacher's private profile."""
        if request.user.role != User.Role.TEACHER:
            raise PermissionDenied("Only teachers have a teacher profile endpoint.")
        teacher = get_object_or_404(self.get_queryset(), user=request.user)
        if request.method == "PATCH":
            serializer = self.get_serializer(
                teacher,
                data=request.data,
                partial=True,
                context=self.get_serializer_context(),
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        return Response(self.get_serializer(teacher).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAdminRole])
    def verify(self, request, pk=None):
        """Verify a teacher profile and record the admin who approved it."""
        teacher = self.get_object()
        teacher.verification_status = Teacher.VerificationStatus.VERIFIED
        teacher.verified_by = request.user.admin_profile
        teacher.save(update_fields=["verification_status", "verified_by"])
        return Response(TeacherSerializer(teacher, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAdminRole])
    def reject(self, request, pk=None):
        """Reject a teacher verification request."""
        teacher = self.get_object()
        teacher.verification_status = Teacher.VerificationStatus.REJECTED
        teacher.verified_by = None
        teacher.save(update_fields=["verification_status", "verified_by"])
        return Response(TeacherSerializer(teacher, context=self.get_serializer_context()).data)


class AdminProfileViewSet(
    AuditAdminWritesMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Admin-only profile list, detail and partial-update endpoints."""

    queryset = AdminProfile.objects.select_related("user").order_by("id")
    serializer_class = AdminProfileSerializer
    permission_classes = [IsAdminRole]