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

Open http://localhost:4200 and sign in with a seeded account (password
`Password123` for all of them):

| Email                | Role          | Lands on     |
| -------------------- | ------------- | ------------ |
| `owner@acme.test`    | `super_admin` | Admin panel  |
| `admin@acme.test`    | `admin`       | Admin panel  |
| `hr@acme.test`       | `hr`          | Admin panel  |
| `manager@acme.test`  | `manager`     | Admin panel  |
| `dev@acme.test`      | `employee`    | User panel   |
| `designer@acme.test` | `employee`    | User panel   |

`python manage.py seed_demo --reset` rebuilds the demo organization from scratch.

### Verifying the wiring

```bash
cd realtime && npm run test:e2e
```

Runs 30 checks across all three services with everything running: login, role
gates, token refresh and rotation, check-in/check-out, and that a Django-side
event actually arrives over a websocket. `npm run smoke` tests the hub alone,
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

## Documentation

- [`docs/api.md`](docs/api.md) - every endpoint, with request/response examples
- [`docs/realtime.md`](docs/realtime.md) - websocket protocol, channels, and the
  planned messaging paths

---

## Current scope

Implemented: authentication (login, organization signup, refresh rotation,
logout, sessions, password change/reset), the employee directory, organization
and department management, attendance (check-in/out, history, summaries, admin
corrections, daily overview), and realtime delivery of all of it.

Deliberately left for later: leave management, payroll, file uploads, email
delivery for invites (the temporary password is returned in the API response
instead), and a Redis-backed hub for running more than one websocket node.
