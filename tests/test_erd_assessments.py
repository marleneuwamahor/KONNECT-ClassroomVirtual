from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Student, Teacher, User
from academics.models import Course, Enrollment
from assessments.models import Assignment, Submission


class ERDAssessmentAPITests(APITestCase):
    def setUp(self):
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
        Enrollment.objects.create(student=self.student, course=self.course)

    def test_quiz_submission_answers_and_max_score_grading(self):
        self.client.force_authenticate(self.teacher_user)
        response = self.client.post(
            "/api/assignments/",
            {
                "course": self.course.pk,
                "title": "Cell quiz",
                "type": "quiz",
                "due_at": (timezone.now() + timedelta(days=1)).isoformat(),
                "max_score": 20,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        assignment = Assignment.objects.get(pk=response.data["id"])
        self.assertEqual(assignment.type, Assignment.Type.QUIZ)
        self.assertEqual(assignment.max_score, 20)

        self.client.force_authenticate(self.student_user)
        response = self.client.post(
            "/api/submissions/",
            {
                "assignment": assignment.pk,
                "answers": {"q1": "mitochondria"},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        submission = Submission.objects.get(pk=response.data["id"])
        self.assertEqual(submission.answers, {"q1": "mitochondria"})

        self.client.force_authenticate(self.teacher_user)
        response = self.client.patch(
            f"/api/submissions/{submission.pk}/grade/",
            {"score": "18", "teacher_feedback": "Good"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        submission.refresh_from_db()
        self.assertEqual(submission.score, 18)
        self.assertEqual(submission.teacher_feedback, "Good")

        response = self.client.patch(
            f"/api/submissions/{submission.pk}/grade/",
            {"score": "21"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
