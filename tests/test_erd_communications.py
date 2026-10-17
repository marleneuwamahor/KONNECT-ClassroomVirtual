from rest_framework.test import APITestCase

from accounts.models import AdminProfile, Student, Teacher, User
from academics.models import Course
from communications.models import Announcement, Notification, SystemSetting


class ERDCommunicationAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            "admin@example.com",
            "pass12345!",
            name="Admin",
        )
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
        self.course = Course.objects.create(
            title="Science",
            grade="8",
            teacher=self.teacher,
            status=Course.Status.APPROVED,
        )

    def test_admin_can_create_and_update_system_settings(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/system-settings/",
            {"key": "registration_open", "value": "true"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        setting = SystemSetting.objects.get(pk="registration_open")
        self.assertEqual(setting.updated_by, AdminProfile.objects.get(user=self.admin))

        response = self.client.patch(
            "/api/system-settings/registration_open/",
            {"value": "false"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        setting.refresh_from_db()
        self.assertEqual(setting.value, "false")

        self.client.force_authenticate(self.student_user)
        self.assertEqual(self.client.get("/api/system-settings/").status_code, 403)

    def test_notification_type_and_teacher_announcement_relation(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/notifications/",
            {
                "user": self.student_user.pk,
                "title": "Exam scheduled",
                "message": "Review the exam details.",
                "type": "exam",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Notification.objects.get(pk=response.data["id"]).type, "exam")

        self.client.force_authenticate(self.teacher_user)
        response = self.client.post(
            "/api/announcements/",
            {
                "course": self.course.pk,
                "title": "Welcome",
                "content": "Welcome to class.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            Announcement.objects.get(pk=response.data["id"]).teacher,
            self.teacher,
        )
