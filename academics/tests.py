from datetime import timedelta
from unittest.mock import Mock, patch

import jwt
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Student, Teacher, User

from .services.hms_service import create_hms_room
from .models import Attendance, Enrollment, LiveSession, SchoolClass


class HMSServiceTests(TestCase):
    @override_settings(
        HMS_ENABLED=True,
        HMS_ACCESS_KEY="test-access-key",
        HMS_APP_SECRET="test-app-secret-that-is-at-least-32-bytes",
        HMS_TEMPLATE_ID="test-template",
        HMS_WEBHOOK_URL="https://example.com/api/live-sessions/webhook/",
        HMS_WEBHOOK_SECRET="test-webhook-secret",
    )
    @patch("academics.services.hms_service.requests.post")
    def test_room_creation_uses_management_token_and_private_webhook_header(
        self,
        post,
    ):
        response = Mock()
        response.json.return_value = {"id": "room-200"}
        post.return_value = response

        room = create_hms_room(name="konnect-session-200", description="Class")

        self.assertEqual(room["id"], "room-200")
        request = post.call_args.kwargs
        management_token = request["headers"]["Authorization"].removeprefix("Bearer ")
        claims = jwt.decode(
            management_token,
            "test-app-secret-that-is-at-least-32-bytes",
            algorithms=["HS256"],
        )
        self.assertEqual(claims["type"], "management")
        self.assertEqual(claims["access_key"], "test-access-key")
        self.assertEqual(
            request["json"]["webhook"]["headers"]["X-KONNECT-Webhook-Secret"],
            "test-webhook-secret",
        )


class LiveSessionAPITests(APITestCase):
    def setUp(self):
        self.teacher_user = User.objects.create_user(
            email="teacher@example.com",
            password="test-password",
            name="Teacher",
            role=User.Role.TEACHER,
        )
        self.teacher = Teacher.objects.create(
            user=self.teacher_user,
            employee_number="T-100",
        )
        self.student_user = User.objects.create_user(
            email="student@example.com",
            password="test-password",
            name="Student",
            role=User.Role.STUDENT,
        )
        self.student = Student.objects.create(
            user=self.student_user,
            student_number="S-100",
        )
        self.other_student_user = User.objects.create_user(
            email="other@example.com",
            password="test-password",
            name="Other Student",
            role=User.Role.STUDENT,
        )
        self.other_student = Student.objects.create(
            user=self.other_student_user,
            student_number="S-101",
        )
        self.school_class = SchoolClass.objects.create(
            name="Science",
            grade="7",
            teacher=self.teacher,
        )
        Enrollment.objects.create(student=self.student, school_class=self.school_class)

        self.start_time = timezone.now() + timedelta(hours=1)
        self.end_time = self.start_time + timedelta(hours=1)
        self.session = LiveSession.objects.create(
            school_class=self.school_class,
            teacher=self.teacher,
            title="Science lesson",
            start_time=self.start_time,
            end_time=self.end_time,
            hms_room_id="room-100",
        )

    @override_settings(
        HMS_ENABLED=True,
        HMS_ACCESS_KEY="test-access-key",
        HMS_APP_SECRET="test-app-secret-that-is-at-least-32-bytes",
        HMS_STUDENT_ROLE="student",
        HMS_TEACHER_ROLE="host",
    )
    def test_enrolled_student_receives_a_room_scoped_token(self):
        self.client.force_authenticate(self.student_user)

        response = self.client.post(
            reverse("live-session-join", args=[self.session.pk]),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["room_id"], self.session.hms_room_id)
        self.assertEqual(response.data["role"], "student")
        claims = jwt.decode(
            response.data["token"],
            "test-app-secret-that-is-at-least-32-bytes",
            algorithms=["HS256"],
        )
        self.assertEqual(claims["room_id"], self.session.hms_room_id)
        self.assertEqual(claims["user_id"], str(self.student_user.pk))
        self.assertLessEqual(claims["exp"], int(self.session.join_deadline.timestamp()))
        self.assertNotIn("test-app-secret-that-is-at-least-32-bytes", response.data["token"])

    @override_settings(
        HMS_ENABLED=True,
        HMS_ACCESS_KEY="test-access-key",
        HMS_APP_SECRET="test-app-secret-that-is-at-least-32-bytes",
    )
    def test_unenrolled_student_cannot_get_a_session_token(self):
        self.client.force_authenticate(self.other_student_user)

        response = self.client.post(
            reverse("live-session-join", args=[self.session.pk]),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @override_settings(
        HMS_ENABLED=True,
        HMS_ACCESS_KEY="test-access-key",
        HMS_APP_SECRET="test-app-secret-that-is-at-least-32-bytes",
        HMS_TEACHER_ROLE="host",
    )
    def test_assigned_teacher_can_get_a_teacher_token(self):
        self.client.force_authenticate(self.teacher_user)

        response = self.client.post(
            reverse("live-session-join", args=[self.session.pk]),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], "host")

    @override_settings(
        HMS_ENABLED=True,
        HMS_ACCESS_KEY="test-access-key",
        HMS_APP_SECRET="test-app-secret-that-is-at-least-32-bytes",
        HMS_TEMPLATE_ID="test-template",
        HMS_WEBHOOK_URL="https://example.com/api/live-sessions/webhook/",
        HMS_WEBHOOK_SECRET="test-webhook-secret",
    )
    @patch("academics.views.create_hms_room", return_value={"id": "new-room"})
    def test_teacher_creates_room_for_assigned_class(self, create_room):
        self.client.force_authenticate(self.teacher_user)
        response = self.client.post(
            reverse("live-session-list"),
            {
                "school_class": self.school_class.pk,
                "title": "New lesson",
                "start_time": self.start_time.isoformat(),
                "end_time": self.end_time.isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["teacher"], self.teacher.pk)
        self.assertEqual(response.data["hms_room_id"], "new-room")
        create_room.assert_called_once()

    @override_settings(HMS_ENABLED=False)
    @patch("academics.views.create_hms_room")
    def test_session_creation_keeps_the_existing_non_100ms_path(self, create_room):
        self.client.force_authenticate(self.teacher_user)
        response = self.client.post(
            reverse("live-session-list"),
            {
                "school_class": self.school_class.pk,
                "title": "Manual meeting",
                "start_time": self.start_time.isoformat(),
                "end_time": self.end_time.isoformat(),
                "meeting_url": "https://example.com/meeting",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["hms_room_id"], "")
        self.assertEqual(response.data["meeting_url"], "https://example.com/meeting")
        create_room.assert_not_called()

    @override_settings(
        HMS_ENABLED=True,
        HMS_ACCESS_KEY="test-access-key",
        HMS_APP_SECRET="test-app-secret-that-is-at-least-32-bytes",
        HMS_TEMPLATE_ID="test-template",
        HMS_WEBHOOK_URL="https://example.com/api/live-sessions/webhook/",
        HMS_WEBHOOK_SECRET="test-webhook-secret",
    )
    @patch(
        "academics.views.create_hms_room",
        side_effect=ImproperlyConfigured("missing 100ms configuration"),
    )
    def test_room_provisioning_failure_does_not_create_session(self, create_room):
        self.client.force_authenticate(self.teacher_user)
        response = self.client.post(
            reverse("live-session-list"),
            {
                "school_class": self.school_class.pk,
                "title": "Unavailable lesson",
                "start_time": self.start_time.isoformat(),
                "end_time": self.end_time.isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertFalse(
            LiveSession.objects.filter(title="Unavailable lesson").exists()
        )
        create_room.assert_called_once()

    @override_settings(HMS_WEBHOOK_SECRET="test-webhook-secret")
    def test_webhook_uses_join_and_leave_events_to_mark_attendance(self):
        webhook_url = reverse("live-session-webhook")
        self.client.credentials(HTTP_X_KONNECT_WEBHOOK_SECRET="wrong-secret")
        response = self.client.post(webhook_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.credentials(HTTP_X_KONNECT_WEBHOOK_SECRET="test-webhook-secret")
        joined_at = self.start_time - timedelta(minutes=5)
        response = self.client.post(
            webhook_url,
            {
                "id": "event-join-1",
                "type": "peer.join.success",
                "data": {
                    "room_id": self.session.hms_room_id,
                    "user_id": str(self.student_user.pk),
                    "joined_at": joined_at.isoformat(),
                    "type": "regular",
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.post(
            webhook_url,
            {
                "id": "event-join-1",
                "type": "peer.join.success",
                "data": {
                    "room_id": self.session.hms_room_id,
                    "user_id": str(self.student_user.pk),
                    "joined_at": joined_at.isoformat(),
                    "type": "regular",
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(
            webhook_url,
            {
                "id": "event-leave-1",
                "type": "peer.leave.success",
                "data": {
                    "room_id": self.session.hms_room_id,
                    "user_id": str(self.student_user.pk),
                    "joined_at": joined_at.isoformat(),
                    "left_at": self.end_time - timedelta(minutes=5),
                    "type": "regular",
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        attendance = Attendance.objects.get(
            student=self.student,
            live_session=self.session,
        )
        self.assertEqual(attendance.status, Attendance.Status.PRESENT)
        self.assertTrue(attendance.auto_marked)
        self.assertEqual(attendance.joined_at, joined_at)
        self.assertEqual(attendance.left_at, self.end_time - timedelta(minutes=5))

    @override_settings(HMS_WEBHOOK_SECRET="test-webhook-secret")
    def test_session_close_marks_enrolled_nonparticipants_absent(self):
        Enrollment.objects.create(
            student=self.other_student,
            school_class=self.school_class,
        )
        self.client.credentials(HTTP_X_KONNECT_WEBHOOK_SECRET="test-webhook-secret")
        response = self.client.post(
            reverse("live-session-webhook"),
            {
                "id": "event-close-1",
                "type": "session.close.success",
                "data": {
                    "room_id": self.session.hms_room_id,
                    "session_stopped_at": self.end_time.isoformat(),
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        attendance = Attendance.objects.get(
            student=self.student,
            live_session=self.session,
        )
        self.assertEqual(attendance.status, Attendance.Status.ABSENT)
        self.assertTrue(attendance.auto_marked)
        no_show_attendance = Attendance.objects.get(
            student=self.other_student,
            live_session=self.session,
        )
        self.assertEqual(no_show_attendance.status, Attendance.Status.ABSENT)
        self.assertIsNone(no_show_attendance.joined_at)

    @override_settings(
        HMS_ACCESS_KEY="test-access-key",
        HMS_APP_SECRET="test-app-secret",
    )
    def test_student_cannot_join_after_session_deadline(self):
        self.session.start_time = timezone.now() - timedelta(minutes=16)
        self.session.end_time = timezone.now() + timedelta(minutes=44)
        self.session.save(update_fields=["start_time", "end_time"])
        self.client.force_authenticate(self.student_user)

        response = self.client.post(
            reverse("live-session-join", args=[self.session.pk]),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
