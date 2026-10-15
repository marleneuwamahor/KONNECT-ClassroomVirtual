# School Management Backend (Django + DRF)

Backend for the school ERD: users, students, teachers, classes, enrollments, attendance,
assignments, submissions, live sessions, announcements, notifications, payments and audit logs.

## Quick start (Windows PowerShell)
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
python manage.py test tests
```

## API (all under /api/, JWT bearer auth)
- `POST auth/register/` (creates a student), `POST auth/token/`, `POST auth/token/refresh/`
- `users/` (admin), `users/me/` (GET, PATCH with profile image upload), `students/`, `teachers/`
- `classes/`, `enrollments/`, `attendance/`, `live-sessions/`
- `assignments/`, `submissions/`, `submissions/{id}/grade/`
- `announcements/`, `notifications/`, `notifications/{id}/read/`, `notifications/read-all/`
- `payments/`, `payments/{id}/mark-paid/`
- `audit-logs/` (admin, read-only)

## Roles
- **admin**: full access
- **teacher**: manages their own classes, assignments, attendance and grading
- **student**: sees only their own or enrolled data, and submits assignments