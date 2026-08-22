# HRMS Portal

Human-resource management portal built on four moving parts:

| Service     | Stack                        | Port  | Responsibility                                    |
| ----------- | ---------------------------- | ----- | ------------------------------------------------- |
| `backend/`  | Django 5 + mongoengine       | 8000  | REST API, authentication, all business rules      |
| `realtime/` | Express 4 + `ws`             | 4000  | Websocket hub - relays messages to connected UIs  |
| `frontend/` | Angular 21 (standalone)      | 4200  | Admin panel and employee panel                    |
| MongoDB     | Mongo 7 (docker-compose)     | 27017 | Every collection                                  |

```
                    HTTP  /api/v1/*
   Angular  ─────────────────────────────►  Django  ──────►  MongoDB
      │                                        │
      │  WS  ws://…/ws?token=…                 │  POST /internal/publish
      └──────────────►  Express hub  ◄─────────┘        (x-internal-key)
```

Django never holds a socket. When something happens that an open screen should
know about, it POSTs to the hub, and the hub fans the message out to the sockets
subscribed to that channel. Both services verify the **same** JWT, so the token
the browser uses for the API is the token it opens the socket with.

---

## Quick start

Prerequisites: Python 3.11+, Node 20+, Docker (for Mongo).

```bash
docker compose up -d
```

**1. API** (`backend/`)

```bash
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
```

```bash
cd backend && cp .env.example .env && .venv/Scripts/python manage.py seed_demo && .venv/Scripts/python manage.py runserver 8000
```

**2. Websocket hub** (`realtime/`)

```bash
cd realtime && npm install && cp .env.example .env && npm start
```

**3. UI** (`frontend/`)

```bash
cd frontend && npm install && npm start
```

Open http://localhost:4200 and sign in with a seeded account - either the login
ID or the email works, password `Password123` for all of them:

| Login ID           | Email                | Role          | Lands on     |
| ------------------ | -------------------- | ------------- | ------------ |
| `ACOWAC20240001`   | `owner@acme.test`    | `super_admin` | Admin panel  |
| `ACAIKA20260001`   | `admin@acme.test`    | `admin`       | Admin panel  |
| `ACRAME20260002`   | `hr@acme.test`       | `hr`          | Admin panel  |
| `ACSAIY20260003`   | `manager@acme.test`  | `manager`     | Admin panel  |
| `ACVIRA20260004`   | `dev@acme.test`      | `employee`    | User panel   |
| `ACNESH20260005`   | `designer@acme.test` | `employee`    | User panel   |

`python manage.py seed_demo --reset` rebuilds the demo organization from scratch
and prints the login IDs it issued.

Browsing to **http://localhost:8000** (the API host) redirects to the sign-in
page, so neither port shows a 404.

---

## Login IDs

Nobody chooses a username. Every account - the founder who signs up and every
employee an admin adds afterwards - is issued one by the system:

```
O I J O D O 2 0 2 2 0 0 0 1
└┬┘ └──┬──┘ └──┬──┘ └──┬──┘
 │     │       │       └──── 0001  serial number of joining, per org and year
 │     │       └──────────── 2022  year of joining
 │     └──────────────────── JODO  first two letters of first and last name
 └────────────────────────── OI    organization code

OIJODO20220001  =  Odoo India / John Doe / joined 2022 / first joiner of 2022
```

The organization code comes from the company name at signup: initials of the
first two words ("Odoo India" -> `OI`), or the first two letters of a one-word
name ("Acme" -> `AC`). It is fixed once issued, because every login ID in that
organization is built on it.

The serial restarts each year and is unique per organization, so the second
person to join in 2022 is `0002`. `core/identifiers.py` holds the whole rule,
and both creation paths call it.

**Signing in** accepts the login ID *or* the email - one field, the API decides
which it received.

### How accounts come into existence

| Path                     | Who does it        | Login ID  | Password              |
| ------------------------ | ------------------ | --------- | --------------------- |
| `POST /auth/register`    | A new organization | Generated | Chosen on the form    |
| `POST /users`            | HR officer / admin | Generated | Generated, unless set |

A normal employee cannot register themselves. When HR adds them, the API returns
the login ID and a one-time password (shown once in the admin panel, never
retrievable afterwards) and flags the account `must_change_password`. At their
first sign-in the UI routes them to `/change-password` and nothing else opens
until they have set their own password.

### Existing databases

A database seeded before this scheme has no codes or login IDs, and both are
required and unique:

```bash
cd backend && .venv/Scripts/python manage.py backfill_login_ids --dry-run
```

Drop `--dry-run` to apply. It is safe to re-run and skips records that already
have the fields.

---

## File store

Company logos are uploaded at signup (multipart, field `logo`) or later via
`POST /organization/logo`. Files are written to `MEDIA_ROOT` (default
`backend/media/`) - a plain directory, so it can be a Docker volume; see the
commented `api` service in `docker-compose.yml`.

Only the path is stored in Mongo, and it is served back as an absolute URL built
from `API_PUBLIC_URL` so the Angular app on another origin can load it. Uploads
are validated by magic bytes rather than by the filename or the declared content
type, and capped at 2 MB.

---

## Verifying the wiring

```bash
cd realtime && npm run test:e2e
```

Runs 45 checks across all three services with everything running: login by ID
and by email, role gates, login-ID generation and the first-time password flow,
token refresh and rotation, check-in/check-out, the root redirect, and that a
Django-side event actually arrives over a websocket. `npm run smoke` tests the hub alone,
without Django or Mongo.

---

## Environment

The values that **must** match across services are marked. `.env.example` in the
root, `backend/` and `realtime/` carry the full list.

| Variable           | Used by            | Note                                    |
| ------------------ | ------------------ | --------------------------------------- |
| `JWT_SECRET`       | Django + Express   | **Must match** - the hub verifies Django's tokens |
| `JWT_ISSUER`       | Django + Express   | **Must match** (`hrms-api`)             |
| `INTERNAL_API_KEY` | Django + Express   | **Must match** - guards `/internal/*`   |
| `MONGO_URI`        | Django             | `mongodb://localhost:27017`             |
| `MEDIA_ROOT`       | Django             | Upload directory (Docker volume)        |
| `API_PUBLIC_URL`   | Django             | Origin used to build media URLs         |
| `FRONTEND_URL`     | Django             | Where `localhost:8000` redirects        |
| `REALTIME_HTTP_URL`| Django             | Where to publish events                 |
| `DJANGO_API_URL`   | Express            | Where to report presence                |

Frontend endpoints live in `frontend/src/environments/environment.ts`.

---

## Backend layout

```
backend/
├── hrms/                 project config (settings, root urls, wsgi/asgi)
├── core/                 everything shared - start here
│   ├── base_controller.py  BaseController: request access, auth, tenancy, responses
│   ├── base_model.py       BaseDocument: timestamps, soft delete, to_dict()
│   ├── decorators.py       @api_view, @auth_required, @roles_required, @internal_only
│   ├── middleware.py       resolves the bearer token; turns exceptions into JSON
│   ├── responses.py        the one response envelope
│   ├── exceptions.py       ApiError hierarchy -> HTTP status codes
│   ├── security.py         password hashing + JWT issue/verify
│   ├── validators.py       field validation, all raising 422s
│   ├── pagination.py       uniform list pagination
│   ├── identifiers.py      login ID generation (the OIJODO20220001 rule)
│   ├── storage.py          uploaded-file store (logos), magic-byte validated
│   ├── realtime.py         Django -> hub publisher + channel names
│   ├── mongo.py            connection lifecycle
│   └── views.py            /health, / index, internal presence callback
└── apps/
    ├── users/            User, RefreshToken + auth/profile/directory
    ├── organization/     Organization, Department
    └── attendance/       Attendance, WorkSession, AttendanceSummary
```

Each app follows the same four files:

- **`models.py`** - mongoengine documents, one per Mongo collection
- **`services.py`** - business logic; no HTTP, reusable from commands and jobs
- **`controllers.py`** - one class per resource, subclassing `BaseController`
- **`views.py`** / **`urls.py`** - thin: declare method + access rule, delegate

Adding an endpoint is: a service function, a controller method, a one-line view,
a URL entry.

### Response envelope

Every endpoint answers the same shape, so the Angular client has one contract:

```jsonc
// success
{ "success": true, "data": { … }, "message": "…", "meta": { "page": 1, "total": 42 } }
// failure
{ "success": false, "error": { "code": "validation_error", "message": "…",
                               "details": { "email": "Enter a valid email address." } } }
```

`details` is keyed by form-control name, so a 422 binds straight onto the form.

### Roles

`super_admin` › `admin` › `hr` › `manager` › `employee`. The first four reach the
admin panel (`Role.ADMIN_PANEL`); everyone reaches the user panel. Every list
query is scoped to the caller's organization by `BaseController.scoped()`, and
cross-tenant access raises 403 — a super admin is the only exemption.

---

## Feature Documentation

- [`payroll.md`](payroll.md) / [`docs/payroll.md`](docs/payroll.md) — HRMS Payroll Module (Role templates, salary dependency engine, PF & Tax, payslips)
- [`teams.md`](teams.md) / [`docs/teams.md`](docs/teams.md) — Teams & Organizational Hierarchy Module (Teams, ranks, hierarchy tree, transfers)
- [`claims.md`](claims.md) / [`docs/claims.md`](docs/claims.md) — Expense Claims, Fines, and Employee Requests Module
- [`docs/api.md`](docs/api.md) — REST API reference and request/response envelope specs
- [`docs/realtime.md`](docs/realtime.md) — Websocket protocol, channels, and event hub specification

---

## Current scope

Implemented:
- Authentication & Sessions (Login ID / email, org registration, forced password change, refresh rotation, session revoking).
- Employee Directory & User Profile management.
- Teams & Organizational Hierarchy management (custom rank levels, hierarchy trees, employee transfers).
- Attendance System (check-in/out, work sessions, daily summaries, admin overview).
- Leave Management System (leave allocations, leave types, leave requests, approval workflow).
- Expense Claims, Fines, & Employee Requests System (reimbursement claims, administrative fines, hardware & ID card request queues).
- Full HRMS Payroll Module (role-level templates, employee payroll assignment with ROLE vs MANUAL protection, salary calculation dependency engine, PF & Tax deductions, payslips and CTC document management).
- Realtime WebSocket event hub for live UI synchronization.
