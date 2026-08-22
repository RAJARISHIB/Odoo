# Dayflow HRMS — Architecture

Dayflow is a multi-tenant HR management system: attendance, leave/time-off, employee
directory, teams, and organization administration, with a security architecture
(RBAC, MFA, audit logging, rate limiting) layered across all of it.

## 1. Stack

```
Angular 21 (standalone components, signals)
        │  HTTPS (REST, JSON envelope)
        ▼
Django 5.1 API  (no DRF — a small hand-rolled controller/decorator layer)
        │  mongoengine (ODM)
        ▼
MongoDB  (Atlas in production; one database per deployment, tenants share it)

        Django ──HTTP POST /internal/publish──▶ Express + ws hub ──WebSocket──▶ Angular
```

There is no relational database anywhere in this stack. `DATABASES = {}` in
Django settings; the Django ORM, migrations, `django.contrib.admin`,
`django.contrib.auth`, and sessions apps are deliberately not installed.
Password hashing still works because `django.contrib.auth.hashers` is a
standalone module that doesn't require the ORM.

A third small Node service (`realtime/`) holds the actual WebSocket
connections and fans out events Django tells it to publish; Django itself
never holds a live socket. It authenticates each incoming WS connection with
the same JWT `access_token` the Angular app already has.

## 2. Repository layout

```
backend/
  hrms/            settings.py, urls.py, wsgi/asgi
  core/            cross-cutting: middleware, base_controller, decorators,
                   security (JWT/password/TOTP), permissions (RBAC),
                   audit, ratelimit, mailer, storage, validators, responses
  apps/
    users/         accounts, auth, RBAC config, MFA, sessions, audit log
    organization/  tenant profile, departments
    attendance/    check-in/out, admin corrections, summaries
    leaves/        leave types, requests, holidays, allocation, carry-forward
    teams/         team hierarchy, membership, availability, birthdays
frontend/
  src/app/
    core/          services (Api, Auth, TokenStorage, Realtime, Toast, Users),
                   guards, interceptors, models
    features/      one folder per screen, grouped by audience:
                   auth/, user/ (self-service), admin/ (management),
                   employees/ (shared directory)
    shared/        shell (nav, topbar, punch widget), icon set
realtime/
  src/             Express + ws hub (Node, ESM)
```

## 3. Backend conventions

### 3.1 Request lifecycle

```
Request
  → CorsMiddleware / CommonMiddleware / SecurityMiddleware (Django/HSTS/redirect)
  → SecurityHeadersMiddleware   (CSP, Permissions-Policy, nosniff on every response)
  → RequestContextMiddleware    (resolves the bearer token → request.auth_user, live from Mongo)
  → ExceptionHandlerMiddleware  (turns any raised exception into the JSON error envelope;
                                 also writes an audit "access.denied" entry for 401/403-shaped codes)
  → urls.py → a thin view function → a Controller method
```

Every collection's authenticated identity is resolved **fresh from MongoDB on
every request** (`RequestContextMiddleware._resolve_user`) — the JWT's `role`
claim is informational only; `request.auth_user.role`, `.status`,
`.mfa_enabled` etc. are always the live document. This means a role change,
account suspension, or MFA change takes effect on the very next request, not
after token expiry.

### 3.2 `BaseController` (`core/base_controller.py`)

Every controller subclasses this. It supplies, per request:

- `self.data` / `self.field()` / `self.param()` — body/query access (JSON or multipart)
- `self.user`, `self.require_user()`, `self.require_roles(...)`, `self.require_admin()`
- `self.require_permission(*perms)` — fine-grained RBAC (see §5.2); also enforces
  the MFA-required-permission rule
- `self.require_step_up()` — demands a recently-proven session (see §5.4)
- `self.assert_self_or_admin(user_id)`, `self.assert_same_organization(doc)` — object-level checks
- `self.scoped(Model)` / `self.get_or_404(Model, id)` — tenant-scoped queries
  (every query is filtered to the caller's `organization`, except `SUPER_ADMIN`)
- `self.ok()/.created()/.paginated()/.deleted()` — the standard response envelope
- `self.emit_to_user/_org/_admins()` — fire-and-forget realtime notifications
- `self.audit(action, ...)` — writes a `core.audit.AuditLog` entry

Decorators in `core/decorators.py` (`@api_view`, `@auth_required`,
`@roles_required`, `@admin_required`, `@permission_required`,
`@step_up_required`, `@internal_only`) apply the same rules at the view-function
level for routes that don't need controller-level nuance.

### 3.3 Response envelope

```json
// success
{"success": true, "data": {...}, "message": "...", "meta": {...}}
// error
{"success": false, "error": {"code": "...", "message": "...", "details": {...}}}
```

Every `ApiError` subclass (`core/exceptions.py`) maps to a fixed HTTP status
and machine-readable `code` (`validation_error` 422, `unauthenticated` 401,
`permission_denied` 403, `not_found` 404, `conflict` 409, `too_many_requests`
429, `mfa_setup_required` 403, `step_up_required` 401, ...). Unhandled
exceptions become a generic `internal_error` 500 with no detail unless
`DEBUG=True`.

### 3.4 Tenancy

Every domain document carries an `organization` reference. `BaseController.scoped()`
filters every list/lookup by the caller's organization automatically; only
`SUPER_ADMIN` bypasses this. There is currently one organization per signed-up
company, created via `POST /api/v1/auth/register` (which also creates that
org's first `SUPER_ADMIN`).

## 4. Domain apps

### 4.1 `apps.users` — accounts, auth, RBAC, security

**Collections:** `users`, `refresh_tokens`, `password_reset_tokens`,
`email_verification_tokens`, `role_permissions`, `throttle_buckets`, `audit_logs`.

| Model | Purpose |
|---|---|
| `User` | Login identity + HR profile in one document: `login_id` (system-generated, e.g. `OIJODO20220001`), `email`, `password_hash`, `role`, `status`, `department`, `reporting_to`, `mfa_enabled`/`mfa_secret`/`mfa_recovery_codes` (hidden fields), `email_verified`, `failed_login_attempts`/`locked_until`, `must_change_password`. |
| `RefreshToken` | One document per active session; stores only the `jti` (never the raw token), `expires_at` (TTL-indexed), `reauth_at` (when the credentials were last *fully* proven — carried forward across silent refreshes, reset only by a real login/MFA verify). |
| `PasswordResetToken` / `EmailVerificationToken` | Same pattern: only a SHA-256 hash of the token is stored, single-use (`used_at`), TTL-indexed expiry. |
| `RolePermission` | Per-organization override of a role's permission set — see §5.2. |
| `ThrottleBucket` (`core/ratelimit.py`) | `(scope, key)` sliding-window counter with a TTL index — the rate-limit primitive. |
| `AuditLog` (`core/audit.py`) | Append-only security event record — see §5.5. |

Routes: `/api/v1/auth/*` (register, login, mfa/verify, refresh, logout,
forgot/reset-password, verify-email, resend-verification, me, sessions,
change-password), `/api/v1/profile`, `/api/v1/users*` (directory/admin),
`/api/v1/security/mfa/*` (self-service enrollment), `/api/v1/admin/roles/*`
(RBAC config), `/api/v1/admin/audit-logs` (read-only).

### 4.2 `apps.organization` — tenant profile

**Collections:** `organizations`, `departments`.

`Organization` holds identity (name/slug/code/logo/email/address), timezone,
and the **attendance policy** every check-in reads: `work_start_time`,
`work_end_time`, `late_grace_minutes`, `full_day_hours`, `half_day_hours`,
`working_days`. `Department` is a simple org sub-unit with an optional `head`.

Routes: `/api/v1/organization*` (retrieve/update/logo/overview, `SUPER_ADMIN`/`ADMIN`
for writes), `/api/v1/departments*` (create/update by `HR`+, delete by `ADMIN`+).

### 4.3 `apps.attendance` — punches and corrections

**Collections:** `attendance` (one doc per user per day), `attendance_summaries`.

`Attendance.sessions` is a list of embedded `WorkSession`s (`check_in`,
`check_out`, `source`, IP/UA, note) — multiple sessions per day support lunch
breaks. On the **first** punch of the day, `services.check_in()` compares the
timestamp against the org's `work_start_time + late_grace_minutes` to decide
`present` vs `late`. On check-out, `_apply_day_status()` compares total
worked hours against `full_day_hours`/`half_day_hours` to arrive at
`present`/`half_day` (and computes `overtime_seconds`). Admins can create or
overwrite a day's record wholesale via `upsert_manual_entry` (flagged
`is_manual=True`, records `approved_by`) — the only edit path; there's no
partial-session edit.

Routes: `/api/v1/attendance/*` (status, check-in, check-out, me, me/summary)
for any signed-in user; `/api/v1/admin/attendance/*` (list, overview,
detail, manual entry, delete, user summary) for `SUPER_ADMIN`/`ADMIN`/`HR`/`MANAGER`.

### 4.4 `apps.leaves` — the largest domain app

**Collections:** `holidays`, `leave_requests`, `leave_types`,
`leave_allocation_rules`, `leave_allocations`, `leave_adjustments`.

- **`LeaveType`** — a configurable leave category (`name`, `code`, `is_paid`,
  `allow_fractional`, `min_unit`, `max_days_per_request`, `requires_approval`,
  `color`) plus carry-forward config (`allow_carry_forward`,
  `carry_forward_percentage`, `carry_forward_frequency`).
- **`LeaveAllocationRule`** — how much of a leave type a role accrues, and how
  often (`monthly`/`yearly`), effective-dated (`effective_from`/`effective_to`);
  superseding a rule closes the old one rather than deleting it, preserving history.
- **`LeaveAllocation`** — the accrual ledger. `generate_allocations(year, month?)`
  is idempotent: it creates one allocation per `(user, leave_type, period_key)`
  and skips anything already credited, so it's safe to re-run.
- **`LeaveAdjustment`** — an audited, signed manual balance correction
  (used both for ad-hoc HR corrections and for carry-forward credits).
- **`LeaveRequest`** — lifecycle `PENDING → APPROVED/REJECTED`, or
  `CANCELLED` by the employee from either PENDING or APPROVED. Now carries an
  explicit `leave_type` (nullable for legacy rows), which is validated at
  submission time.

**Balance model.** `get_balance(org, user, leave_type, year)` is the single
source of truth: `allocated` = sum of that year's `LeaveAllocation` +
`LeaveAdjustment` rows; `used`/`pending` = sum of `APPROVED`/`PENDING`
requests tagged with that type in that year; `remaining = allocated - used`.
`create_leave_request()` enforces this balance for paid leave types (unpaid
types are exempt — nothing to run out of), plus a per-type max-days-per-request
cap and no-overlap-with-holidays/other-requests checks. `carry_forward()`
credits a configurable percentage of a period's unused balance into the next
period as a `LeaveAdjustment`, idempotent via a marker string in the reason field.

Routes: `/api/v1/leaves/*` (calendar, holidays, balance, type-balances,
requests CRUD+cancel, types read) for any signed-in user; type/holiday writes
gated to `HR`+; `/api/v1/admin/leaves/*` (requests list/approve/reject,
allocation-rules CRUD/generate/carry-forward, adjustments, balances,
dashboard, per-employee summary) for `SUPER_ADMIN`/`ADMIN`/`HR` (approve/reject
open to any admin-panel role).

### 4.5 `apps.teams` — hierarchy and availability

**Collections:** `teams`, `team_hierarchy_levels`, `team_members`.

A `Team` has configurable `TeamHierarchyLevel`s (e.g. Director → Manager →
Lead → Developer, ordered). `TeamMember` links one user to one team + level;
adding a member to a team **automatically deactivates their membership in any
other team** — an employee belongs to at most one active team.
`get_team_availability()` builds a Mon–Fri grid per member, resolving each
day to holiday / on-leave (from approved `LeaveRequest`s) / attendance status
/ absent / scheduled. `get_team_birthdays()` surfaces today's + next-7-days
birthdays, leap-year-safe.

Routes: `/api/v1/teams/*` (my-team, availability, birthdays — any signed-in
user) and `/api/v1/admin/teams/*` (team/hierarchy CRUD for `HR`+, membership
add/remove/move/hierarchy-assignment additionally open to `MANAGER`).
There is currently no dedicated frontend page for team administration — this
API surface exists but isn't yet exposed as an admin UI screen (department
management, under Organization Settings, is the closest surfaced concept).

## 5. Security architecture

### 5.1 Authentication

JWT bearer tokens, hand-issued/verified in `core/security.py` (no external
auth library). An **access token** (60 min default) carries `sub`, `email`,
`role`, `org_id`, `reauth_at`, and `sid` (the paired refresh token's `jti`, so
"is this my current session" can be answered without decoding two tokens). A
**refresh token** (7 days default) carries only `sub` + `jti`; the server
stores the `jti` (not the raw token) in `RefreshToken` so any session can be
revoked server-side. Refreshing **rotates**: the presented refresh token is
revoked and a new pair issued, single-use.

Passwords are hashed with Django's `django.contrib.auth.hashers`
(PBKDF2-SHA256 by default) — never stored or logged in clear. A temporary
password (admin-issued) forces `must_change_password=True`, which the
frontend redirects on until cleared.

### 5.2 RBAC

Two layers, deliberately not merged:

1. **Role** (`core/constants.Role`: `super_admin`, `admin`, `hr`, `manager`,
   `employee`) — the coarse "which endpoints/panels can this user reach at
   all" gate, checked via `require_roles`/`roles_required` at ~50+ call
   sites across every app. This layer was not rewritten.
2. **Permission** (`core/permissions.py`) — a fine-grained
   `resource.action` catalogue (`employee.view`, `leave.approve`,
   `payroll.export`, `audit.view`, `role.manage`, ...) with a default
   least-privilege matrix per role, **overridable per organization** via
   `RolePermission` documents — editable through
   `GET/PUT /api/v1/admin/roles/<role>/permissions` (gated by `role.manage`).
   `SUPER_ADMIN` always has every permission and is never stored/editable.
   `has_permission(user, perm)` is the single check function; applied via
   `require_permission`/`@permission_required` at the highest-value spots
   (RBAC config, audit log, leave approval/config) alongside the existing
   role gates, not as a wholesale replacement.

`assert_can_assign_role()` enforces a **rank rule** on who may grant which
role: `SUPER_ADMIN` → anyone; `ADMIN` → anyone but `SUPER_ADMIN`/`ADMIN`;
`HR` → only `MANAGER`/`EMPLOYEE`. This closes what was previously a real gap
(an HR account could provision a new `SUPER_ADMIN` through the ordinary
"add employee" form).

Object-level authorization is separate from both of the above:
`assert_self_or_admin(user_id)` / `assert_same_organization(doc)` on
`BaseController` — a permission answers "can this role ever do X", not "can
this user do X to this specific record."

### 5.3 MFA

TOTP (RFC 6238), hand-rolled over stdlib `hmac`/`hashlib`/`base64` — no auth
library dependency. Enrollment (`POST /api/v1/security/mfa/enroll/start` →
`/confirm`) generates a secret, renders it as a scannable QR (`qrcode`
package, SVG output — the one new backend dependency), and on confirmation
issues 10 one-time recovery codes (shown once, stored only as password-hashed
values). Login for an MFA-enabled account is two steps: `POST /auth/login`
returns a narrow `mfa_pending_token` (5-minute TTL, unusable for anything but
the next call) instead of a session; `POST /auth/mfa/verify` exchanges a
TOTP or recovery code for the real token pair. A handful of high-risk
permissions (`role.manage`, `security.manage`, `audit.view`,
`payroll.view_all`, `payroll.export`) additionally require `mfa_enabled=True`
regardless of role — including `SUPER_ADMIN`.

### 5.4 Sessions & step-up

`GET /api/v1/auth/sessions` lists active `RefreshToken`s with an `is_current`
flag; `DELETE /api/v1/auth/sessions/<id>` revokes one specific other device.
Password change, MFA disable, and moving an account out of `active` status
all revoke every other session server-side (not just a client-side token
delete). **Step-up** (`require_step_up`, 15-minute default window) demands
the access token's `reauth_at` claim be recent — set at login/MFA-verify,
*not* reset by silent refreshes — before role changes or MFA-disable/
recovery-code-regeneration are allowed, even within an otherwise-valid
session.

### 5.5 Audit logging

`core/audit.py`'s `AuditLog` is append-only by construction: no
update/delete path exists anywhere in the codebase or its read-only
controller (`GET /api/v1/admin/audit-logs`, gated by `audit.view`). Each
entry: actor, actor's role *at write time*, action, resource type/id, result,
IP/user-agent, and a small metadata dict — never a password, token, or MFA
secret. Wired into login success/failure/lockout, logout, password
change/reset, email verification, MFA enable/disable/failure/regenerate, role
and permission changes, user create/update/delete, session revocation, leave
approve/reject/balance-adjustment, and holiday changes; a centralized hook in
`ExceptionHandlerMiddleware` also logs every `permission_denied`,
`account_locked`, `invalid_mfa_code`, `mfa_setup_required`,
`step_up_required`, and `rate_limited` response as an `access.denied` event.

### 5.6 Rate limiting & lockout

`core/ratelimit.py`'s `ThrottleBucket` (Mongo, TTL-indexed — no Redis) backs
per-`(scope, key)` sliding-window limits: login (10/15min per IP+identifier),
forgot-password (5/15min), resend-verification (3/15min), MFA-verify
(10/15min per IP). Independently, `User.failed_login_attempts` triggers a
15-minute `locked_until` cooldown after 5 consecutive failures — cleared on
next success.

### 5.7 Transport & headers

`django.middleware.security.SecurityMiddleware` + a custom
`SecurityHeadersMiddleware` set `Content-Security-Policy`,
`Permissions-Policy`, `X-Content-Type-Options: nosniff`,
`Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY`
on every API response; `SECURE_SSL_REDIRECT`/`SECURE_HSTS_*` activate
automatically once `DJANGO_DEBUG=False`. The Angular app itself carries its
own CSP via a `<meta>` tag in `index.html` (the API's headers don't reach the
SPA's own document, since Django doesn't serve it). `CoreConfig.ready()`
refuses to boot with `DEBUG=False` if any secret (`DJANGO_SECRET_KEY`,
`JWT_SECRET`, `INTERNAL_API_KEY`) still equals its insecure placeholder.

### 5.8 Input validation & MongoDB safety

`core/validators.py` centralizes field validation (email/phone/password/date/
choice/ObjectId); every free-text search that flows into a MongoDB `$regex`
is wrapped in `re.escape()` (three sites, across `users` and `leaves`) so a
search term can never widen into a wildcard or cause a ReDoS. No endpoint
spreads a raw client dict into a Mongo query — query construction is always
explicit, field-by-field. MongoDB credentials live only in backend
environment variables, never reach Angular, and (Atlas-hosted) enforce
TLS + authentication at the connection level.

## 6. Frontend architecture

**Shell:** one login, one shell (`shared/shell/app-shell`) — there is no
separate admin panel; admin capability shows up as extra nav items (gated by
permission flags) and inline actions on the same pages everyone uses.
`nav-config.ts` defines two sections — *Workspace* (Employees, Attendance,
Time off, Approvals) and *Administration* (Overview, Leave insights, People,
Leave policy, Holidays, Organization) — each item optionally `requires` a
capability flag from `/auth/me`'s `permissions` object; a section with no
visible items is dropped entirely.

**Core services** (`core/services/`):
- `Api` — thin HTTP wrapper unwrapping the `{success, data}` envelope.
- `Auth` — session state as signals (`user`, `organization`, `permissions`,
  `isAuthenticated`, `mfaPending`); owns login/MFA-verify/logout/refresh,
  password reset/verification, MFA enrollment/disable, and session listing/
  revocation.
- `TokenStorage` — the only code touching `localStorage` (access/refresh
  token + cached user object); MFA secrets/recovery codes are never
  persisted there, only held in-memory during enrollment.
- `Realtime` — WebSocket client, connects with the access token on login,
  subscribes to the channels `/auth/me` hints at.
- `Toast` — transient notifications.

**Guards** (`core/guards/auth.guard.ts`): `authGuard` (must be signed in),
`guestGuard` (bounce signed-in users off `/auth/*`), `passwordChangeGuard`
(forces `/change-password` while `must_change_password`), and
`capabilityGuard(flag)` — the primary route protection, reading a permission
flag straight from the server-returned `/auth/me` response. `roleGuard`/
`adminGuard` still exist but are unused in current routing (`capabilityGuard`
is used exclusively) — kept as documented legacy utilities, not wired to
anything. **These guards are UX only**; every one of them has a
server-side equivalent that is the actual enforcement point.

**HTTP interceptor** (`core/interceptors/auth.interceptor.ts`): attaches
`Authorization: Bearer <token>`, and on a 401 does a single-flight refresh
(queuing concurrent requests behind one `/auth/refresh` call) before retrying
— falls back to logout if the refresh itself fails.

**Feature areas**, grouped by audience under `features/`:
- `auth/` — login, register, MFA-verify, forgot/reset-password, change-password.
- `employees/` — read-only directory + detail (presence, last-30-days stats).
- `user/attendance`, `user/calendar`, `user/profile` — self-service: personal
  attendance history, the leave calendar + apply flow with a live per-type
  balance preview, and the profile page (personal details, password, MFA
  enrollment/disable, active sessions).
- `admin/employees` — the management console (create/edit, role assignment,
  reset password, suspend/activate) distinct from the read-only directory.
- `admin/attendance`, `admin/leave/*`, `admin/organization`, `admin/dashboard`
  — team attendance board + manual corrections; leave approvals, insights
  dashboard, holiday calendar, and leave-type/allocation-rule/carry-forward
  configuration; organization profile + working-hours policy + departments;
  the "today at a glance" admin overview.
- `shared/shell/punch-widget` — the persistent check-in/out control in the
  topbar (present on every page, not just the attendance screens).

## 7. Realtime service (`realtime/`)

A small Express + `ws` Node app (ESM, Node ≥ 20). Django never holds a
socket; instead `core/realtime.py`'s `publish()` POSTs to the hub's internal
`/internal/publish` endpoint (authenticated with `x-internal-key`, matching
`INTERNAL_API_KEY`), and the hub fans the message out to whichever
subscribed sockets match the target channel (`user:<id>`, `org:<id>`,
`org:<id>:panel:<admin|user>`, or `broadcast`). Delivery is best-effort by
design — a hub outage never blocks or fails the API write that triggered the
notification, only logs a warning. The Angular client authenticates its
WebSocket handshake with the same JWT access token it already holds, which is
why `JWT_SECRET` must be identical between Django and the Node hub.

## 8. Environment reference

See `backend/.env.example` for the authoritative list. Summary:

| Variable | Purpose |
|---|---|
| `MONGO_URI`, `MONGO_DB_NAME` | Database connection (Atlas in production) |
| `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_ACCESS_TTL_MIN`, `JWT_REFRESH_TTL_DAYS` | Token signing — `JWT_SECRET` must match the realtime hub |
| `INTERNAL_API_KEY` | Django ↔ realtime-hub service key |
| `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` | Core Django |
| `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_HSTS_SECONDS` | Optional HTTPS overrides (default on once `DEBUG=False`) |
| `CORS_ALLOWED_ORIGINS` | Explicit allow-list, no wildcard |
| `EMAIL_HOST` (+ port/user/password/TLS) | Unset → console backend (dev); set → real SMTP |
| `API_PUBLIC_URL`, `FRONTEND_URL`, `FRONTEND_LOGIN_PATH` | Cross-origin URL building |
| `MEDIA_ROOT`, `MAX_UPLOAD_BYTES` | Local file storage (logos/avatars) |
| `REALTIME_HTTP_URL`, `REALTIME_WS_URL`, `REALTIME_PORT` | Realtime hub addresses |

Secrets are never committed (`.env` is gitignored and untracked); only
`.env.example` (placeholders) is in the repository.

## 9. Testing

`backend/apps/users/tests.py` — an integration-style suite (`django.test.Client`
against real URLs, exercising the full middleware/decorator/controller stack)
covering authentication, lockout, session invalidation, object-level
authorization, privilege-escalation prevention, MFA (TOTP + recovery codes),
RBAC/MFA-gating, and input validation. Deliberately run against a disposable
database (name must end `_test`) — `core/testing.py`'s `ApiTestCase` base and
a `setUpClass` guard in `apps/users/tests.py` refuse to run otherwise:

```
MONGO_DB_NAME=hrms_test ./.venv/Scripts/python.exe manage.py test apps.users
```
