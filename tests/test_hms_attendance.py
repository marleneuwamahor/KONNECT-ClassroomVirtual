from datetime import timedelta

from django.utils import timezone
from django.test import TestCase

from accounts.models import Student, Teacher, User
from academics.models import Attendance, Course, Enrollment, LiveSession
from academics.services.hms_webhooks import process_hms_webhook


class HMSAttendanceTests(TestCase):
    def setUp(self):
        self.teacher_user = User.objects.create_user(
            "teacher@example.com",
            "pass12345!",
            name="Teacher",
            role=User.Role.TEACHER,
        )
        self.teacher = Teacher.objects.create(
            user=self.teacher_user,
            employee_number="T-ATTENDANCE",
        )
        self.student_user = User.objects.create_user(
            "student@example.com",
            "pass12345!",
            name="Student",
            role=User.Role.STUDENT,
        )
        self.student = Student.objects.create(
            user=self.student_user,
            student_number="S-ATTENDANCE",
        )
        self.course = Course.objects.create(
            title="Attendance",
            grade="8",
            teacher=self.teacher,
            status=Course.Status.APPROVED,
        )
        Enrollment.objects.create(student=self.student, course=self.course)
        self.starts_at = timezone.now() - timedelta(days=2)
        self.session = LiveSession.objects.create(
            course=self.course,
            teacher=self.teacher,
            title="Attendance session",
            start_time=self.starts_at,
            end_time=self.starts_at + timedelta(hours=1),
            hms_room_id="room-attendance-test",
        )

    def send_peer_event(self, event_id, event_type, joined_at, left_at=None):
        data = {
            "room_id": self.session.hms_room_id,
            "user_id": str(self.student_user.pk),
            "joined_at": joined_at.isoformat(),
        }
        if left_at is not None:
            data["left_at"] = left_at.isoformat()
        return process_hms_webhook(
            {
                "id": event_id,
                "type": event_type,
                "data": data,
            }
        )

    def test_student_is_not_present_until_leave_confirms_attendance_cutoff(self):
        joined_at = self.starts_at + timedelta(minutes=10)
        left_at = self.session.attendance_cutoff + timedelta(minutes=1)

        self.send_peer_event("join-before-cutoff", "peer.join.success", joined_at)
        attendance = Attendance.objects.get(
            student=self.student,
            live_session=self.session,
        )
        self.assertEqual(attendance.status, Attendance.Status.ABSENT)
        self.assertIsNone(attendance.left_at)

        self.send_peer_event(
            "leave-after-cutoff",
            "peer.leave.success",
            joined_at,
            left_at,
        )
        attendance.refresh_from_db()
        self.assertEqual(attendance.status, Attendance.Status.PRESENT)
        self.assertTrue(attendance.auto_marked)

    def test_student_joining_after_deadline_is_marked_absent(self):
        joined_at = self.session.join_deadline + timedelta(minutes=1)

        self.send_peer_event("late-join", "peer.join.success", joined_at)
        attendance = Attendance.objects.get(
            student=self.student,
            live_session=self.session,
        )

        self.assertEqual(attendance.status, Attendance.Status.ABSENT)

    def test_session_close_marks_connected_student_by_cutoff(self):
        joined_at = self.starts_at + timedelta(minutes=10)
        self.send_peer_event("join-for-close", "peer.join.success", joined_at)

        process_hms_webhook(
            {
                "id": "close-after-cutoff",
                "type": "session.close.success",
                "data": {
                    "room_id": self.session.hms_room_id,
                    "session_stopped_at": (
                        self.session.attendance_cutoff + timedelta(minutes=1)
                    ).isoformat(),
                },
            }
        )

        attendance = Attendance.objects.get(
            student=self.student,
            live_session=self.session,
        )
        self.assertEqual(attendance.status, Attendance.Status.PRESENT)
        self.assertTrue(attendance.auto_marked)
