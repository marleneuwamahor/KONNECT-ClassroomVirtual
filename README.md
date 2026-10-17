# School Management Backend (Django + DRF)

Backend for the school ERD: users, students, teachers, courses, enrollments, attendance,
assignments, submissions, live sessions, announcements, notifications, payments and audit logs.

## Quick start (Windows PowerShell)
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
python manage.py test
```

## API (all under /api/, JWT bearer auth)

The API root (`/`) returns service information and absolute links to the API documentation:
`/swagger/` (interactive Swagger UI), `/redoc/`, and `/api/schema/` (OpenAPI schema).

- `POST auth/register/` (creates a student), `POST auth/token/`, `POST auth/token/refresh/`
- `users/` (admin), `users/me/` (GET, PATCH with profile image upload), `students/`, `teachers/`
- `courses/`, legacy `classes/`, `enrollments/`, `attendance/`, `live-sessions/`
- `assignments/`, `submissions/`, `submissions/{id}/grade/`
- `announcements/`, `notifications/`, `notifications/{id}/read/`, `notifications/read-all/`
- `payments/`, `payments/{id}/mark-paid/`
- `audit-logs/` (admin, read-only)

## Courses and approval

Course endpoints use JSON and require `Authorization: Bearer <access-token>`. Authenticated users
can list courses according to their role and enrollment. Teachers see their courses; students see
approved public courses and approved private courses in which they are actively enrolled; admins
see all courses.

### Create a course

`POST /api/courses/` accepts `title`, optional `description`, `visibility` (`public` or `private`),
and optional `course_limit` (zero means unlimited). Teachers are assigned as the course teacher
automatically and their new courses start as `pending`. Admins must also provide `teacher` (the
teacher profile ID); courses created by admins are approved immediately.

```json
{
  "title": "Science",
  "description": "Grade 6 science",
  "visibility": "public",
  "course_limit": 30
}
```

Success (`201 Created`) returns a JSON object containing `id`, `title`, `teacher`, `description`,
`visibility`, `course_limit`, `status`, `approved_by`, and `created_at`.

### Approve or reject a course

- `POST /api/courses/{id}/approve/` — admin only; sets `status` to `approved` and records the
  approving user.
- `POST /api/courses/{id}/reject/` — admin only; sets `status` to `rejected`.

Both accept an empty JSON body and return the updated course (`200 OK`). A missing or invalid
course ID returns `404`; a non-admin caller receives `403`. Invalid course fields return `400`,
and missing or invalid authentication returns `401`.

For a quick PowerShell check, set `$apiBase` and `$accessToken` to your backend URL and JWT access
token, then run:

```powershell
$headers = @{ Authorization = "Bearer $accessToken" }
$body = @{ title = "Science"; description = "Grade 6 science"; visibility = "public"; course_limit = 30 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$apiBase/api/courses/" -Headers $headers -ContentType "application/json" -Body $body
```

`/api/classes/` remains available for existing clients. It uses the legacy `name` field and keeps
the prior student visibility behavior; new clients should use `/api/courses/`.

## Live sessions and 100ms

Live sessions belong to an approved course and use that course's assigned teacher. Only the assigned teacher,
an enrolled student with an active enrollment, or an admin can retrieve/join a session. Session
responses include the server-managed `hms_room_id`, `join_deadline` (start time + 15 minutes), and
`attendance_cutoff` (end time - 15 minutes). Do not send `hms_room_id` or 100ms credentials from the
client when creating a session.

Configure these server environment variables before creating sessions:

- `HMS_ENABLED=true` to provision 100ms rooms; it defaults to `false` so existing manually linked
  sessions continue to work until the integration is configured
- `HMS_ACCESS_KEY`, `HMS_APP_SECRET`, `HMS_TEMPLATE_ID`
- `HMS_TEACHER_ROLE` (defaults to `host`) and `HMS_STUDENT_ROLE` (defaults to `guest`)
- `HMS_WEBHOOK_URL` (public HTTPS URL for `/api/live-sessions/webhook/`)
- `HMS_WEBHOOK_SECRET` (a long, random secret; never expose it to the frontend)

### Schedule a session

`POST /api/live-sessions/` requires a JWT bearer token for an admin or teacher. The teacher field
is assigned from the course and cannot point to a different teacher.

```json
{
  "school_class": 12,
  "title": "Science lesson",
  "start_time": "2026-10-20T09:00:00Z",
  "end_time": "2026-10-20T10:00:00Z"
}
```

The response includes `hms_room_id`, `join_deadline`, and `attendance_cutoff`. If the room cannot
be created, the API returns `503 Service Unavailable` and does not create the local session.

### Join a session

`POST /api/live-sessions/{id}/join/` requires `Authorization: Bearer <access-token>` and an empty
JSON body. It returns a one-hour 100ms app token:

```json
{
  "token": "<short-lived-100ms-token>",
  "room_id": "<100ms-room-id>",
  "role": "guest",
  "expires_in": 3600
}
```

The endpoint returns `403` when the join deadline has passed and `404` when the session is outside
the caller's access scope. Missing 100ms configuration or a session without a room returns `503`.
Tokens are valid for up to one hour and never beyond the session's join deadline.
The app secret and management token are never returned.

### Automatic attendance

100ms sends room webhooks to `HMS_WEBHOOK_URL` with the `X-KONNECT-Webhook-Secret` header. The
backend uses `peer.join.success`, `peer.leave.success`, and `session.close.success` events to record
one attendance row per student and live session. Attendance is marked present only when the student
joined by the join deadline and is connected at or after the attendance cutoff. Enrolled students
without a join event are marked absent when the 100ms session closes. The webhook endpoint is
server-to-server only; do not call it from frontend code.

## Roles
- **admin**: full access
- **teacher**: manages their own classes, assignments, attendance and grading
- **student**: sees only their own or enrolled data, and submits assignments