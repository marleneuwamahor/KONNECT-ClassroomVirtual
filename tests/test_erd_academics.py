from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from academics.models import Course, Enrollment, Exam, Grade, LiveSession, StudentFlag
from accounts.models import Student, Teacher, User


class ERDAcademicAPITests(APITestCase):
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
        self.other_student_user = User.objects.create_user(
            "other@example.com",
            "pass12345!",
            name="Other Student",
            role=User.Role.STUDENT,
        )
        self.other_student = Student.objects.create(
            user=self.other_student_user,
            student_number="S-101",
        )
        self.course = Course.objects.create(
            title="Science",
            grade="8",
            teacher=self.teacher,
            status=Course.Status.APPROVED,
        )
        Enrollment.objects.create(student=self.student, course=self.course)

    def test_teacher_can_schedule_exam_and_grade_active_student(self):
        self.client.force_authenticate(self.teacher_user)
        response = self.client.post(
            "/api/exams/",
            {
                "course": self.course.pk,
                "title": "Midterm",
                "exam_date": (timezone.now() + timedelta(days=1)).isoformat(),
                "duration_minutes": 60,
                "total_marks": 40,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        exam = Exam.objects.get(pk=response.data["id"])

        response = self.client.post(
            "/api/grades/",
            {
                "exam": exam.pk,
                "student": self.student.pk,
                "score": "35",
                "grade_letter": "A",
                "teacher_feedback": "Good work",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        grade = Grade.objects.get(pk=response.data["id"])
        self.assertEqual(grade.graded_by, self.teacher)
        self.assertEqual(grade.score, 35)

        response = self.client.post(
            "/api/grades/",
            {
                "exam": exam.pk,
                "student": self.other_student.pk,
                "score": "20",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

        self.client.force_authenticate(self.student_user)
        response = self.client.get("/api/grades/")
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["exam"], exam.pk)

        self.client.force_authenticate(self.other_student_user)
        self.assertEqual(self.client.get("/api/grades/").data["count"], 0)

    def test_score_cannot_exceed_exam_marks(self):
        exam = Exam.objects.create(
            course=self.course,
            title="Quiz",
            exam_date=timezone.now() + timedelta(days=1),
            duration_minutes=30,
            total_marks=10,
        )
        self.client.force_authenticate(self.teacher_user)
        response = self.client.post(
            "/api/grades/",
            {
                "exam": exam.pk,
                "student": self.student.pk,
                "score": "11",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_live_session_accepts_erd_field_names(self):
        self.client.force_authenticate(self.teacher_user)
        starts_at = timezone.now() + timedelta(days=1)
        ends_at = starts_at + timedelta(hours=1)

        response = self.client.post(
            "/api/live-sessions/",
            {
                "course": self.course.pk,
                "title": "Science lesson",
                "starts_at": starts_at.isoformat(),
                "ends_at": ends_at.isoformat(),
                "join_link": "https://example.com/session",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        session = LiveSession.objects.get(pk=response.data["id"])
        self.assertEqual(session.course, self.course)
        self.assertEqual(session.teacher, self.teacher)
        self.assertEqual(session.meeting_url, "https://example.com/session")
        self.assertEqual(response.data["starts_at"], response.data["start_time"])
        self.assertEqual(response.data["ends_at"], response.data["end_time"])
        self.assertEqual(response.data["join_link"], response.data["meeting_url"])
        self.assertEqual(
            response.data["join_deadline"],
            (starts_at + timedelta(minutes=15)).isoformat().replace("+00:00", "Z"),
        )

    @override_settings(HMS_ENABLED=True)
    def test_join_token_is_denied_at_exact_join_deadline(self):
        starts_at = timezone.now() + timedelta(hours=1)
        session = LiveSession.objects.create(
            course=self.course,
            teacher=self.teacher,
            title="Deadline test",
            start_time=starts_at,
            end_time=starts_at + timedelta(hours=1),
            hms_room_id="room-deadline-test",
        )
        self.client.force_authenticate(self.teacher_user)

        with patch(
            "academics.views.timezone.now",
            return_value=session.join_deadline,
        ), patch("academics.views.generate_hms_auth_token") as generate_token:
            response = self.client.post(
                f"/api/live-sessions/{session.pk}/join/",
                {},
                format="json",
            )

        self.assertEqual(response.status_code, 403)
        generate_token.assert_not_called()

    def test_teacher_can_flag_only_an_active_student_in_own_course(self):
        self.client.force_authenticate(self.teacher_user)
        response = self.client.post(
            "/api/student-flags/",
            {
                "student": self.student.pk,
                "course": self.course.pk,
                "reason": "Needs additional support",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        flag = StudentFlag.objects.get(pk=response.data["id"])
        self.assertEqual(flag.flagged_by, self.teacher)

        response = self.client.post(
            "/api/student-flags/",
            {
                "student": self.other_student.pk,
                "course": self.course.pk,
                "reason": "Not enrolled",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

        self.client.force_authenticate(self.student_user)
        self.assertEqual(self.client.get("/api/student-flags/").data["count"], 1)
        self.client.force_authenticate(self.other_student_user)
        self.assertEqual(self.client.get("/api/student-flags/").data["count"], 0)
