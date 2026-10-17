from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from academics.models import Course, Enrollment
from accounts.models import Student, Teacher, User
from audit.models import AuditLog


class BaseAPITest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin@x.com", "pass12345!", name="Admin")
        self.t_user = User.objects.create_user("t@x.com", "pass12345!", name="Teacher", role="teacher")
        self.teacher = Teacher.objects.create(user=self.t_user, employee_number="E1")
        self.s_user = User.objects.create_user("s@x.com", "pass12345!", name="Stu", role="student")
        self.student = Student.objects.create(user=self.s_user, student_number="S1")
        self.s2_user = User.objects.create_user("s2@x.com", "pass12345!", name="Stu2", role="student")
        self.student2 = Student.objects.create(user=self.s2_user, student_number="S2")
        self.klass = Course.objects.create(
            title="Math",
            grade="5",
            teacher=self.teacher,
            status=Course.Status.APPROVED,
        )
        Enrollment.objects.create(student=self.student, course=self.klass)

    def login(self, user):
        self.client.force_authenticate(user)


class AuthTests(APITestCase):
    def test_register_and_login(self):
        res = self.client.post("/api/auth/register/", {
            "name": "New", "email": "new@x.com",
            "password": "Str0ng-pass-123", "student_number": "S99",
        })
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["role"], "student")
        tok = self.client.post("/api/auth/token/", {"email": "new@x.com", "password": "Str0ng-pass-123"})
        self.assertEqual(tok.status_code, 200)
        self.assertIn("access", tok.data)

    def test_requires_authentication(self):
        self.assertEqual(self.client.get("/api/classes/").status_code, 401)


class AcademicsTests(BaseAPITest):
    def test_student_sees_only_enrolled_classes(self):
        Course.objects.create(
            title="Art",
            grade="5",
            teacher=self.teacher,
            status=Course.Status.APPROVED,
        )
        self.login(self.s_user)
        res = self.client.get("/api/classes/")
        self.assertEqual([c["name"] for c in res.data["results"]], ["Math"])

    def test_student_cannot_create_class(self):
        self.login(self.s_user)
        res = self.client.post("/api/classes/", {"name": "X", "grade": "1"})
        self.assertEqual(res.status_code, 403)

    def test_teacher_creates_class_as_self(self):
        self.login(self.t_user)
        res = self.client.post("/api/classes/", {"name": "Science", "grade": "6"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["teacher"], self.teacher.id)

    def test_course_requires_admin_approval_before_students_can_see_it(self):
        other_user = User.objects.create_user(
            "other-teacher@x.com",
            "pass12345!",
            name="Other Teacher",
            role="teacher",
        )
        other_teacher = Teacher.objects.create(
            user=other_user,
            employee_number="E2",
        )
        self.login(self.t_user)
        response = self.client.post(
            "/api/courses/",
            {"title": "Science", "teacher": other_teacher.id},
        )
        self.assertEqual(response.status_code, 201)
        course = Course.objects.get(pk=response.data["id"])
        self.assertEqual(course.teacher, self.teacher)
        self.assertEqual(course.status, Course.Status.PENDING)

        self.login(self.s_user)
        self.assertNotIn(
            course.id,
            [item["id"] for item in self.client.get("/api/courses/").data["results"]],
        )

        self.login(self.admin)
        response = self.client.post(f"/api/courses/{course.id}/approve/")
        self.assertEqual(response.status_code, 200)
        course.refresh_from_db()
        self.assertEqual(course.status, Course.Status.APPROVED)
        self.assertEqual(course.approved_by, self.admin)

        self.login(self.s_user)
        self.assertIn(
            course.id,
            [item["id"] for item in self.client.get("/api/courses/").data["results"]],
        )

    def test_teacher_cannot_reassign_owned_course(self):
        other_user = User.objects.create_user(
            "other-teacher@x.com",
            "pass12345!",
            name="Other Teacher",
            role="teacher",
        )
        other_teacher = Teacher.objects.create(
            user=other_user,
            employee_number="E2",
        )
        self.login(self.t_user)
        response = self.client.patch(
            f"/api/courses/{self.klass.id}/",
            {"teacher": other_teacher.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.klass.refresh_from_db()
        self.assertEqual(self.klass.teacher, self.teacher)

    def test_only_admin_enrolls(self):
        payload = {"student": self.student2.id, "school_class": self.klass.id}
        self.login(self.t_user)
        self.assertEqual(self.client.post("/api/enrollments/", payload).status_code, 403)
        self.login(self.admin)
        self.assertEqual(self.client.post("/api/enrollments/", payload).status_code, 201)

    def test_teacher_records_attendance(self):
        self.login(self.t_user)
        res = self.client.post("/api/attendance/", {
            "student": self.student.id, "school_class": self.klass.id, "status": "late",
        })
        self.assertEqual(res.status_code, 201)

    def test_live_session_end_must_follow_start(self):
        self.login(self.t_user)
        now = timezone.now()
        res = self.client.post("/api/live-sessions/", {
            "school_class": self.klass.id, "title": "Live",
            "start_time": now.isoformat(),
            "end_time": (now - timedelta(hours=1)).isoformat(),
        })
        self.assertEqual(res.status_code, 400)


class AssessmentTests(BaseAPITest):
    def _assignment(self):
        self.login(self.t_user)
        res = self.client.post("/api/assignments/", {
            "school_class": self.klass.id, "title": "HW1",
            "due_date": (timezone.now() + timedelta(days=2)).isoformat(),
        })
        self.assertEqual(res.status_code, 201)
        return res.data["id"]

    def test_submit_and_grade_flow(self):
        aid = self._assignment()
        self.login(self.s_user)
        res = self.client.post("/api/submissions/", {"assignment": aid, "file_url": "https://f.io/a.pdf"})
        self.assertEqual(res.status_code, 201)
        sid = res.data["id"]
        self.assertEqual(self.client.post("/api/submissions/", {"assignment": aid}).status_code, 400)
        self.assertEqual(self.client.patch(f"/api/submissions/{sid}/grade/", {"grade": 90}).status_code, 403)
        self.login(self.t_user)
        res = self.client.patch(f"/api/submissions/{sid}/grade/", {"grade": "88.50", "feedback": "Good"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action="grade", entity_id=sid).exists())

    def test_unenrolled_student_cannot_submit(self):
        aid = self._assignment()
        self.login(self.s2_user)
        self.assertEqual(self.client.post("/api/submissions/", {"assignment": aid}).status_code, 403)

    def test_invalid_grade_rejected(self):
        aid = self._assignment()
        self.login(self.s_user)
        sid = self.client.post("/api/submissions/", {"assignment": aid}).data["id"]
        self.login(self.t_user)
        self.assertEqual(self.client.patch(f"/api/submissions/{sid}/grade/", {"grade": 150}).status_code, 400)


class CommunicationsBillingTests(BaseAPITest):
    def test_teacher_announces_only_to_own_class(self):
        other_t = User.objects.create_user("o@x.com", "pass12345!", name="O", role="teacher")
        Teacher.objects.create(user=other_t, employee_number="E2")
        body = {"school_class": self.klass.id, "title": "Hi", "content": "x"}
        self.login(other_t)
        self.assertEqual(self.client.post("/api/announcements/", body).status_code, 403)
        self.login(self.t_user)
        res = self.client.post("/api/announcements/", body)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["author"], self.t_user.id)

    def test_notifications_are_private_and_markable(self):
        from communications.models import Notification
        n = Notification.objects.create(user=self.s_user, title="t", message="m")
        self.login(self.s2_user)
        self.assertEqual(self.client.get("/api/notifications/").data["count"], 0)
        self.login(self.s_user)
        self.assertEqual(self.client.post(f"/api/notifications/{n.id}/read/").data["is_read"], True)

    def test_payments_admin_write_student_reads_own(self):
        body = {"student": self.student.id, "amount": "100.00", "transaction_ref": "T1"}
        self.login(self.s_user)
        self.assertEqual(self.client.post("/api/payments/", body).status_code, 403)
        self.login(self.admin)
        res = self.client.post("/api/payments/", body)
        self.assertEqual(res.status_code, 201)
        pid = res.data["id"]
        self.assertEqual(self.client.post(f"/api/payments/{pid}/mark-paid/").data["status"], "paid")
        self.client.post("/api/payments/", {"student": self.student2.id, "amount": "5", "transaction_ref": "T2"})
        self.login(self.s_user)
        self.assertEqual(self.client.get("/api/payments/").data["count"], 1)

    def test_audit_logs_admin_only(self):
        self.login(self.t_user)
        self.assertEqual(self.client.get("/api/audit-logs/").status_code, 403)
        self.login(self.admin)
        self.assertEqual(self.client.get("/api/audit-logs/").status_code, 200)