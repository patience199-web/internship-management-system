# Attachly — Internship Management System

A full-stack internship / industrial attachment management system for universities and colleges. It includes a React application, Django REST API, PostgreSQL configuration, role-based permissions, document uploads, weighted assessment results, notifications, exports, seed data and workflow tests.

## What is included

- **Student workspace:** profile, placement registration and approval tracking, assessment calendar, weekly logbook drafts/submissions, revision history, lecturer feedback, notifications and published results.
- **Lecturer workspace:** assigned student list, assessment scheduling and student reschedule requests with overlap checks, logbook review/feedback, assessment marks with draft/final state, and results for assigned placements.
- **Coordinator workspace:** user/profile management, placement approvals, period-specific lecturer assignments, academic setup, configurable assessment criteria/weightings and grading bands, result finalization/publication, CSV/PDF exports and an audit trail.
- **Backend:** Django REST Framework API, JWT access/refresh tokens, role-based queryset scoping, server validation, protected media endpoint, audit logging, PostgreSQL support and SQLite fallback for quick local setup.
- **UI:** responsive blue-and-white dashboard with collapsible sidebar, status tags, cards, charts, list/calendar views, modals, toasts and mobile layouts.

## Project structure

```text
internship-management-system/
├── backend/
│   ├── accounts/                 # Custom user and role-specific profiles
│   ├── config/                   # Django settings and root URLs
│   ├── core/                     # Domain models, API, permissions and tests
│   ├── requirements.txt
│   └── manage.py
├── frontend/
│   ├── src/components/           # Shared shell and UI primitives
│   ├── src/pages/                # Role-specific workflows
│   ├── src/lib/api.js            # JWT-aware REST client
│   └── package.json
├── docker-compose.yml
└── README.md
```

## Option A: Run with Docker (PostgreSQL)

Install Docker Desktop / Docker Engine with the Compose plugin, then from the project root:

```bash
docker compose up --build
```

The services start PostgreSQL, apply the included migrations, insert local demonstration records and start both development servers.

- Frontend: http://localhost:5173
- API: http://localhost:8000/api/
- Django admin site: http://localhost:8000/admin/

For first-time use, Compose uses a deliberately simple local database password. Set `POSTGRES_PASSWORD` and `DJANGO_SECRET_KEY` in a root `.env` file before using the setup outside a private development machine. Do not expose Django's development server or `DEBUG=True` to the public internet.

## Option B: Run locally

Requirements: Python 3.12, Node.js 20+, npm and PostgreSQL 14+ if using PostgreSQL. Python 3.12 is the recommended local version for compatibility with the pinned Django 5.2 series. The project can use SQLite during initial exploration if `DATABASE_URL` is omitted.

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cp .env.example .env             # SQLite is used unless DATABASE_URL is uncommented
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

The checked-in migrations define the database schema. If you change the models while developing, create and commit new migration files with:

```bash
python manage.py makemigrations accounts core
python manage.py migrate
```

To run with PostgreSQL, create a database and user, set `DATABASE_URL` in `backend/.env`, and use credentials with the least privilege needed for the application. Example:

```env
DATABASE_URL=postgresql://ims_user:your-password@localhost:5432/internship_management
DJANGO_SECRET_KEY=replace-with-a-long-random-secret
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:5173
TIME_ZONE=Africa/Harare
```

Run the API test suite:

```bash
python manage.py test core.tests
```

Create a privileged Django admin-site superuser if you need the separate Django Admin interface:

```bash
python manage.py createsuperuser
```

An application coordinator account is not required to be a Django superuser; the coordinator role is enforced in the Attachly interface and API.

### 2. Frontend

In a second terminal:

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open http://localhost:5173. `VITE_API_BASE_URL` should point to the Django API prefix (default `http://127.0.0.1:8000/api`). To create a production bundle, run `npm run build`; Vite writes it to `frontend/dist/`.

## Local demo accounts

The `seed_demo` command is idempotent for its standard usernames and creates these development-only accounts:

| Role | Username | Password |
|---|---|---|
| Coordinator | `admin` | `DemoAdmin123!` |
| Lecturer | `lecturer` | `DemoLecturer123!` |
| Student | `student` | `DemoStudent123!` |
| Student | `student2` | `DemoStudent123!` |

Change or delete demo accounts before deploying anywhere shared or public. These sample records are only for local testing; live dashboards load from the database and API rather than fixed frontend arrays.

## Main API routes

All application API routes are under `/api/`. JWT login is `POST /api/auth/token/` with `username` and `password`, refresh is `POST /api/auth/token/refresh/`, and the current authenticated user is returned from `/api/auth/me/`.

| Area | Routes |
|---|---|
| Dashboard | `GET /api/dashboard/` |
| User and academic setup | `/api/users/`, `/api/student-profiles/`, `/api/lecturer-profiles/`, `/api/departments/`, `/api/programmes/`, `/api/academic-years/`, `/api/attachment-periods/` |
| Placements | `/api/placements/`, `POST /api/placements/{id}/submit/`, `POST /api/placements/{id}/review/`, `POST /api/placements/{id}/transition/` |
| Lecturer assignments | `/api/assignments/` |
| Assessments | `/api/assessments/`, `POST /api/assessments/{id}/request-reschedule/` |
| Logbooks and feedback | `/api/logbooks/`, `POST /api/logbooks/{id}/submit/`, `POST /api/logbooks/{id}/revise/`, `POST /api/logbooks/{id}/feedback/`, `/api/logbook-feedback/` |
| Scoring | `/api/assessment-categories/`, `/api/assessment-criteria/`, `/api/grading-scales/`, `/api/assessment-marks/`, `/api/final-results/`, `POST /api/final-results/{id}/finalize/`, `POST /api/final-results/{id}/publish/` |
| Notifications and audit | `/api/notifications/`, `/api/audit-logs/` |
| Reports | `/api/reports/placements/?format=csv` (also `assessments`, `logbooks`, `results`, `students`; use `format=pdf` for PDF exports) |

JWT access tokens expire after 30 minutes, with a refresh token for session renewal. API permissions and queryset scoping are the security boundary; hiding a button in React is not treated as authorization.

## Assessment scoring rules

The administrator configures active criteria with a maximum mark and weighting. For a criterion with multiple final marks, the application averages its normalized marks, then applies its configured weighting. The active criteria must total exactly 100% before finalization, and every required criterion must have a final mark. The calculated score is rounded to two decimal places. An active grading band is matched to the calculated score when one applies; otherwise the grade stays blank. Official results remain hidden from students until a coordinator publishes them. Finalized marks/results are locked for ordinary lecturer edits and sensitive actions are written to the audit log.

No institution-specific weighting or grading scale is assumed as policy; the seeded weights and grade bands are illustrative development values and should be replaced with the institution's approved scheme.

## File uploads and production deployment

Placement letters, logbook attachments and documents are stored under `MEDIA_ROOT` (default `backend/media`). They are not configured as a public static-media directory; uploaded file URLs resolve through an authenticated API endpoint which checks authorization against the related record. Keep the upload directory private and persistent in deployment. Apply HTTPS, production `ALLOWED_HOSTS`, a strong secret key, `DEBUG=False`, secure cookies, a managed database, backups, log monitoring, and a production WSGI/ASGI server before public use. Configure allowed origins explicitly. Email delivery is not enabled; notification events currently appear in the in-app notification centre, and an email provider can be connected later.

## Development notes

- Frontend data is fetched through the API. Sample data exists only in the `seed_demo` management command.
- Authentication is JWT-based. Frontend tokens are held in `sessionStorage` and refreshed where possible; backend authorization remains authoritative.
- Uploaded-file validation allows PDF, DOC, DOCX, PNG and JPG/JPEG up to 10 MB. Extend the policy deliberately if more formats are required.
- Report exports use user-scoped querysets so student and lecturer exports do not cross role boundaries.
- Automated tests cover student record isolation, lecturer assignment scoping, blocked student assessment creation, result visibility, configured score calculation and logbook revision preservation.
