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
- `users/` (admin), `users/me/`, `users/me/profile-image/`, `students/`, `students/me/`, `teachers/`, `teachers/me/`,
  `admin-profiles/`, `teachers/{id}/verify/`, `teachers/{id}/reject/`
- `courses/`, legacy `classes/`, `enrollments/`, `attendance/`, `live-sessions/`
- `assignments/`, `submissions/`, `submissions/{id}/grade/`, `exams/`, `grades/`,
  `student-flags/`
- `announcements/`, `notifications/`, `notifications/{id}/read/`, `notifications/read-all/`,
  `system-settings/`
- `payments/`, `payments/{id}/mark-paid/`
- `audit-logs/` (admin, read-only)

The generated OpenAPI schema and Swagger UI include descriptions for every API operation. APIs
use JSON and return paginated collections unless described otherwise, and require
`Authorization: Bearer <access-token>` unless described as public below. Profile and document
image fields are URLs, not binary uploads. IDs remain
integer primary keys to preserve existing data; they are not UUIDs as shown in the proposed ERD.

## Accounts and profiles

### Users and sign-up

- `POST /api/auth/register/` — public student sign-up. Send `full_name`, `email`, `password`, and
  `username`; optional `date_of_birth` is accepted. Legacy clients may send `name` and
  `student_number` instead. Returns `201` with the created user's profile. Duplicate email or
  username and invalid passwords return `400`.
- `POST /api/auth/token/` and `POST /api/auth/token/refresh/` — exchange credentials for JWT
  access/refresh tokens and refresh an access token.
- `/api/users/` — admin-only user CRUD. `full_name` and `status` (`active`/`inactive`) are the
  ERD-facing names; legacy `name` and `is_active` remain in responses. New users record the
  managing admin in `managed_by`. Passwords are write-only and stored hashed.
- `GET/PATCH /api/users/me/` — any authenticated user reads or updates their own name, profile
  image URL, phone, and bio. Email, role, and account status cannot be changed here.
- `POST /api/users/me/profile-image/` — any authenticated user uploads their profile photo as
  multipart form data using the `image` field. Accepts JPEG, PNG, or WebP images up to 5 MB.
  Returns `profile_image` and `profile_picture_url` as the Cloudinary URL and updates the user's
  role-specific profile photo as well. Returns `400` for an invalid/oversized image and `503` if
  Cloudinary is not configured or cannot accept the upload.

Example upload from Windows PowerShell with `curl.exe`:

```powershell
curl.exe -X POST "$apiBase/api/users/me/profile-image/" `
  -H "Authorization: Bearer $accessToken" `
  -F "image=@C:\path\to\profile.png"
```

Example student registration:

```json
{
  "full_name": "Amina Example",
  "email": "amina@example.com",
  "password": "Use-a-strong-password-123",
  "username": "STU-0001",
  "date_of_birth": "2012-05-20"
}
```

### Student profiles

- `/api/students/` — administrators manage profiles; teachers and admins can list/retrieve
  profiles, while students are restricted to their own profile.
- `GET/PATCH /api/students/me/` — students read or update their own `profile_picture_url`, `bio`,
  `date_of_birth`, and `grade_level`. `username` is the canonical profile identifier;
  `student_number` remains in responses for backwards compatibility.

### Teacher profiles and verification

- `/api/teachers/` — admins manage full profiles. Students see only verified teacher directory
  fields; a teacher can access their own directory entry. Private legal/document fields are not
  included in the student directory. The legacy `employee_number` field is optional for new
  profiles because it is not part of the ERD.
- `GET/PATCH /api/teachers/me/` — teachers read/update their own professional and document URL
  fields. Verification state and verifier are read-only to teachers.
- `POST /api/teachers/{id}/verify/` and `POST /api/teachers/{id}/reject/` — admin-only actions.
  They return the updated profile and record/clear `verified_by`.
- `GET/PATCH /api/admin-profiles/` and `/api/admin-profiles/{id}/` — administrator-only profile
  access. Profiles are created automatically with admin accounts; the API can update
  `profile_picture_url` and `admin_level`.

Profile photos can be uploaded using `POST /api/users/me/profile-image/`. Send the image as
multipart form data in the `image` field (JPEG, PNG, or WebP, up to 5 MB). The API stores it in
Cloudinary and returns its URL; it updates the signed-in user's profile and their student, teacher,
or admin profile photo. Set the Render environment variable `CLOUDINARY_URL` to the Cloudinary
connection string. Keep this credential on the server; never put it in frontend code.

CV and degree-certificate fields remain URLs. This backend does not currently provide document
uploads; the ERD's 10 MB and file-type limits for those documents must be enforced by an upload
service before its URL is saved.

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

### Exams and grades

- `/api/exams/` — teachers create/update/delete exams only for their own approved courses;
  authenticated students can list/retrieve exams for their active courses; admins can manage all
  exams. Send `course`, `title`, `exam_date`, positive `duration_minutes`, and positive
  `total_marks`.
- `/api/grades/` — teachers record/update/delete results for active students in their own course;
  admins can manage results; students can list/retrieve only their own results. Send `exam`,
  `student`, `score`, and optional `grade_letter`/`teacher_feedback`. Scores cannot exceed the
  exam's `total_marks`; grade letters are entered by the teacher and are not automatically
  converted from scores. A student can receive only one grade per exam.

Example:

```json
{
  "exam": 4,
  "student": 12,
  "score": "38.50",
  "grade_letter": "A",
  "teacher_feedback": "Strong work."
}
```

### Student flags

- `/api/student-flags/` — teachers can create/update/delete flags only for actively enrolled
  students in their own courses; admins can manage all flags. Authenticated students can read
  only flags about themselves. Create body: `student`, `course`, `reason`. The API sets
  `flagged_by` from the course's teacher so callers cannot impersonate another teacher.

### Assignments and submissions

- `/api/assignments/` — teachers create/manage `quiz` or `exercise` records for their own
  approved courses; students read assignments for enrolled courses. Fields include `course`,
  `type`, `title`, `description`, `due_at`, and positive `max_score`. Legacy `school_class` and
  `due_date` fields remain available.
- `/api/submissions/` — students submit JSON `answers` and/or `file_url` for an assignment while
  actively enrolled. A student can submit once per assignment and can read only their own work;
  course teachers and admins can read within their scope.
- `PATCH /api/submissions/{id}/grade/` — the course teacher or admin sets `score` and
  `teacher_feedback`. The score cannot exceed assignment `max_score`. Legacy `grade` and
  `feedback` input/output aliases are kept.

### Announcements, notifications and settings

- `/api/announcements/` — teachers post to their own courses; admins can manage announcements.
  The response includes both the author user and related teacher profile.
- `/api/notifications/` — users can list, retrieve and mark their own notifications read; admins
  create notifications with `user`, `title`, `message`, and optional string `type` (default
  `general`). `POST /api/notifications/{id}/read/` marks one notification read;
  `POST /api/notifications/read-all/` marks all of the caller's notifications read.
- `/api/system-settings/` — admin-only CRUD for key/value settings. Each create/update records the
  acting `updated_by` admin profile. Settings are not public.

### Audit logs and status codes

- `GET /api/audit-logs/` and `GET /api/audit-logs/{id}/` — admin-only, read-only audit history;
  `admin_id` identifies an administrator actor when applicable, and legacy `user` attribution is
  preserved.
- Protected routes return `401` for missing/invalid authentication and `403` when an authenticated
  caller lacks permission. Invalid fields or workflow rules return `400`, inaccessible/nonexistent
  records return `404`, and unexpected server/integration failures return `5xx`.
- To test an endpoint, sign in through `/api/auth/token/`, then use Swagger's **Authorize** button
  with the access token. Swagger sends `Authorization: Bearer <access-token>` for protected calls.

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
  "course": 12,
  "title": "Science lesson",
  "starts_at": "2026-10-20T09:00:00Z",
  "ends_at": "2026-10-20T10:00:00Z"
}
```

The response includes `hms_room_id`, `join_deadline`, `attendance_cutoff`, and `join_link`.
Legacy `school_class`, `start_time`, `end_time`, and `meeting_url` names remain accepted.
If the room cannot
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