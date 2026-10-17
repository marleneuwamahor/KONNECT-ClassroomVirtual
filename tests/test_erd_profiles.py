from io import BytesIO
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APITestCase

from accounts.services.profile_image_storage import ProfileImageStorageError
from accounts.models import AdminProfile, Student, Teacher, User
from audit.models import AuditLog


class ERDProfileAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            "admin@example.com",
            "pass12345!",
            name="Admin",
        )
        self.admin_profile = AdminProfile.objects.get(user=self.admin)
        self.teacher_user = User.objects.create_user(
            "teacher@example.com",
            "pass12345!",
            name="Teacher",
            role=User.Role.TEACHER,
        )
        self.teacher = Teacher.objects.create(
            user=self.teacher_user,
            employee_number="T-100",
        )
        self.student_user = User.objects.create_user(
            "student@example.com",
            "pass12345!",
            name="Student",
            role=User.Role.STUDENT,
        )
        self.student = Student.objects.create(
            user=self.student_user,
            student_number="S-100",
        )

    def test_registration_accepts_erd_user_and_student_names(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "full_name": "New Student",
                "email": "new-student@example.com",
                "password": "Str0ng-pass-123",
                "username": "STU-0002",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["full_name"], "New Student")
        self.assertEqual(
            Student.objects.get(user__email="new-student@example.com").student_number,
            "STU-0002",
        )

    def test_admin_registration_tracks_manager_and_audit_entry(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            "/api/auth/register/",
            {
                "full_name": "Admin-created student",
                "email": "admin-created@example.com",
                "password": "Str0ng-pass-123",
                "username": "STU-ADMIN-1",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        created_user = User.objects.get(email="admin-created@example.com")
        self.assertEqual(created_user.managed_by, self.admin_profile)
        self.assertTrue(
            AuditLog.objects.filter(
                admin_profile=self.admin_profile,
                entity="user",
                entity_id=created_user.pk,
                action="register",
            ).exists()
        )

    def test_admin_user_api_accepts_full_name_and_status_and_tracks_manager(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/users/",
            {
                "full_name": "Managed User",
                "email": "managed@example.com",
                "role": "student",
                "status": "inactive",
                "password": "Str0ng-pass-123",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["name"], "Managed User")
        self.assertEqual(response.data["status"], "inactive")
        managed_user = User.objects.get(email="managed@example.com")
        self.assertFalse(managed_user.is_active)
        self.assertEqual(managed_user.managed_by, self.admin_profile)
        self.assertEqual(
            AuditLog.objects.filter(
                admin_profile=self.admin_profile,
                entity="user",
                entity_id=managed_user.pk,
                action="create",
            ).count(),
            1,
        )

    def test_student_can_read_and_update_own_profile(self):
        self.client.force_authenticate(self.student_user)
        response = self.client.get("/api/students/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["username"], "S-100")

        response = self.client.patch(
            "/api/students/me/",
            {"bio": "Learner", "grade_level": "Grade 8"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.bio, "Learner")
        self.assertEqual(self.student.grade_level, "Grade 8")

    @patch(
        "accounts.views.upload_profile_image",
        return_value="https://res.cloudinary.com/example/profile.png",
    )
    def test_profile_image_upload_updates_user_and_student_profile(self, upload):
        image_bytes = BytesIO()
        Image.new("RGB", (2, 2), color="blue").save(image_bytes, format="PNG")
        image = SimpleUploadedFile(
            "profile.png",
            image_bytes.getvalue(),
            content_type="image/png",
        )
        self.client.force_authenticate(self.student_user)

        response = self.client.post(
            "/api/users/me/profile-image/",
            {"image": image},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            response.data["profile_image"],
            "https://res.cloudinary.com/example/profile.png",
        )
        upload.assert_called_once()
        self.student_user.refresh_from_db()
        self.student.refresh_from_db()
        self.assertEqual(
            self.student_user.profile_image,
            "https://res.cloudinary.com/example/profile.png",
        )
        self.assertEqual(
            self.student.profile_picture_url,
            "https://res.cloudinary.com/example/profile.png",
        )

    def test_profile_image_upload_reports_unavailable_storage(self):
        image_bytes = BytesIO()
        Image.new("RGB", (2, 2), color="green").save(image_bytes, format="PNG")
        image = SimpleUploadedFile(
            "profile.png",
            image_bytes.getvalue(),
            content_type="image/png",
        )
        self.client.force_authenticate(self.student_user)

        with patch(
            "accounts.views.upload_profile_image",
            side_effect=ProfileImageStorageError,
        ):
            response = self.client.post(
                "/api/users/me/profile-image/",
                {"image": image},
                format="multipart",
            )

        self.assertEqual(response.status_code, 503)

    def test_profile_image_upload_rejects_non_image_file(self):
        self.client.force_authenticate(self.student_user)

        response = self.client.post(
            "/api/users/me/profile-image/",
            {
                "image": SimpleUploadedFile(
                    "not-an-image.txt",
                    b"not an image",
                    content_type="text/plain",
                )
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)

    def test_teacher_profile_is_private_until_admin_verifies_it(self):
        self.client.force_authenticate(self.student_user)
        self.assertEqual(self.client.get("/api/teachers/").data["count"], 0)

        self.client.force_authenticate(self.teacher_user)
        response = self.client.patch(
            "/api/teachers/me/",
            {
                "display_name": "Science Teacher",
                "subjects_expertise": ["Science"],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["display_name"], "Science Teacher")

        self.client.force_authenticate(self.admin)
        response = self.client.post(f"/api/teachers/{self.teacher.pk}/verify/")
        self.assertEqual(response.status_code, 200)
        self.teacher.refresh_from_db()
        self.assertEqual(
            self.teacher.verification_status,
            Teacher.VerificationStatus.VERIFIED,
        )
        self.assertEqual(self.teacher.verified_by, self.admin_profile)
        self.assertTrue(
            AuditLog.objects.filter(
                admin_profile=self.admin_profile,
                entity="teacher",
                entity_id=self.teacher.pk,
                action="verify",
            ).exists()
        )

        self.client.force_authenticate(self.student_user)
        response = self.client.get("/api/teachers/")
        self.assertEqual(response.data["count"], 1)
        self.assertNotIn("cv_url", response.data["results"][0])

    def test_admin_can_create_teacher_profile_with_erd_fields_only(self):
        new_teacher_user = User.objects.create_user(
            "new-teacher@example.com",
            "pass12345!",
            name="New Teacher",
            role=User.Role.TEACHER,
        )
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            "/api/teachers/",
            {
                "user": new_teacher_user.pk,
                "full_legal_name": "New Teacher Legal Name",
                "display_name": "Teacher Display",
                "subjects_expertise": ["Science"],
                "languages": ["English"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        teacher = Teacher.objects.get(user=new_teacher_user)
        self.assertIsNone(teacher.employee_number)
        self.assertEqual(teacher.full_legal_name, "New Teacher Legal Name")
        self.assertEqual(teacher.verification_status, Teacher.VerificationStatus.PENDING)

    def test_admin_profile_is_created_and_admin_can_update_it(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/admin-profiles/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

        response = self.client.patch(
            f"/api/admin-profiles/{self.admin_profile.pk}/",
            {"admin_level": "senior"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.admin_profile.refresh_from_db()
        self.assertEqual(self.admin_profile.admin_level, "senior")
