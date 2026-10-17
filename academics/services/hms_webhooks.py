from datetime import timezone as datetime_timezone

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from accounts.models import Student

from academics.models import Attendance, Enrollment, HMSWebhookEvent, LiveSession


def _parse_timestamp(value, field_name):
    if not isinstance(value, str):
        raise ValueError(f"Webhook field '{field_name}' must be a timestamp.")

    parsed = parse_datetime(value)
    if parsed is None:
        raise ValueError(f"Webhook field '{field_name}' is not a valid timestamp.")
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, datetime_timezone.utc)
    return parsed


def _attendance_for_peer(session, student, joined_at):
    attendance_date = timezone.localtime(joined_at).date()
    attendance, created = Attendance.objects.get_or_create(
        student=student,
        live_session=session,
        defaults={
            "course": session.course,
            "attendance_date": attendance_date,
            "status": Attendance.Status.ABSENT,
            "auto_marked": True,
            "marked_at": timezone.now(),
        },
    )

    if created:
        attendance.joined_at = joined_at
    elif attendance.joined_at is None or joined_at < attendance.joined_at:
        attendance.joined_at = joined_at
    elif attendance.left_at and joined_at > attendance.left_at:
        attendance.left_at = None

    attendance.attendance_date = attendance_date
    attendance.auto_marked = True
    attendance.marked_at = timezone.now()
    attendance.status = Attendance.Status.ABSENT
    if (
        attendance.joined_at <= session.join_deadline
        and attendance.left_at is not None
        and attendance.left_at >= session.attendance_cutoff
    ):
        attendance.status = Attendance.Status.PRESENT
    attendance.save(
        update_fields=[
            "joined_at",
            "left_at",
            "attendance_date",
            "auto_marked",
            "marked_at",
            "status",
        ]
    )
    return attendance


def _record_peer_event(session, event_type, data):
    if data.get("type") == "sip":
        return

    try:
        user_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return

    enrollment = Enrollment.objects.filter(
        student__user_id=user_id,
        course=session.course,
        status=Enrollment.Status.ACTIVE,
    ).select_related("student").first()
    if enrollment is None:
        return

    joined_at = _parse_timestamp(data.get("joined_at"), "data.joined_at")
    attendance = _attendance_for_peer(session, enrollment.student, joined_at)

    if event_type == "peer.leave.success":
        left_at = _parse_timestamp(data.get("left_at"), "data.left_at")
        if attendance.left_at is None or left_at > attendance.left_at:
            attendance.left_at = left_at
        attendance.status = (
            Attendance.Status.PRESENT
            if (
                attendance.joined_at <= session.join_deadline
                and attendance.left_at >= session.attendance_cutoff
            )
            else Attendance.Status.ABSENT
        )
        attendance.marked_at = timezone.now()
        attendance.save(update_fields=["left_at", "status", "marked_at"])


def _close_session_attendance(session, data):
    stopped_at = _parse_timestamp(
        data.get("session_stopped_at"),
        "data.session_stopped_at",
    )
    open_attendance = Attendance.objects.filter(
        live_session=session,
        joined_at__isnull=False,
        left_at__isnull=True,
    )
    for attendance in open_attendance:
        attendance.left_at = stopped_at
        attendance.status = (
            Attendance.Status.PRESENT
            if (
                attendance.joined_at <= session.join_deadline
                and stopped_at >= session.attendance_cutoff
            )
            else Attendance.Status.ABSENT
        )
        attendance.marked_at = timezone.now()
        attendance.save(update_fields=["left_at", "status", "marked_at"])

    enrolled_students = Student.objects.filter(
        enrollments__course=session.course,
        enrollments__status=Enrollment.Status.ACTIVE,
    ).distinct()
    attendance_date = timezone.localtime(session.start_time).date()
    for student in enrolled_students:
        Attendance.objects.get_or_create(
            student=student,
            live_session=session,
            defaults={
                "course": session.course,
                "attendance_date": attendance_date,
                "status": Attendance.Status.ABSENT,
                "auto_marked": True,
                "marked_at": timezone.now(),
            },
        )


@transaction.atomic
def process_hms_webhook(payload):
    """Record verified 100ms participant events once, preserving provider times."""
    if not isinstance(payload, dict):
        raise ValueError("Webhook payload must be a JSON object.")

    event_id = payload.get("id")
    event_type = payload.get("type")
    data = payload.get("data")
    if not isinstance(event_id, str) or not event_id:
        raise ValueError("Webhook payload is missing its event ID.")
    if not isinstance(event_type, str) or not isinstance(data, dict):
        raise ValueError("Webhook payload is missing its event type or data.")

    _, created = HMSWebhookEvent.objects.get_or_create(event_id=event_id)
    if not created:
        return False

    room_id = data.get("room_id")
    if not isinstance(room_id, str) or not room_id:
        raise ValueError("Webhook data is missing its room ID.")
    session = LiveSession.objects.filter(hms_room_id=room_id).select_related(
        "course"
    ).first()
    if session is None:
        return True

    if event_type in ("peer.join.success", "peer.leave.success"):
        _record_peer_event(session, event_type, data)
    elif event_type == "session.close.success":
        _close_session_attendance(session, data)
    return True
