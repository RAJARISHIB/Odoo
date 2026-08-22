# API reference

Base URL: `http://localhost:8000/api/v1`

All requests and responses are JSON. Authenticated calls send
`Authorization: Bearer <access_token>`.

Every response uses the same envelope:

```jsonc
{ "success": true,  "data": …, "message": "…", "meta": { … } }
{ "success": false, "error": { "code": "…", "message": "…", "details": { … } } }
```

| Status | Meaning                                      |
| ------ | -------------------------------------------- |
| 200    | OK                                           |
| 201    | Created                                      |
| 401    | Missing, invalid or expired access token     |
| 403    | Authenticated but not allowed (role/tenant)  |
| 404    | Not found, or not in your organization       |
| 409    | Conflict (duplicate email, double check-in)  |
| 422    | Validation failed - see `error.details`      |

List endpoints accept `?page=` and `?page_size=` (max 100) and return
`meta: { page, page_size, total, total_pages, has_next, has_previous }`.

---

## Authentication

### `POST /auth/register` — public

Bootstrap: creates an organization plus its first `super_admin`, and signs them
in. The owner is issued a login ID like everybody else.

```json
{
  "organization_name": "Odoo India",
  "name": "John Doe",
  "email": "john@odooindia.test",
  "phone": "+91 90000 11111",
  "password": "Password123",
  "confirm_password": "Password123"
}
```

`name` is split into first and last name (both halves feed the login ID);
`first_name` / `last_name` are accepted instead. `confirm_password` is checked
only when sent.

**With a company logo**, post the same fields as `multipart/form-data` with the
file under `logo` (PNG/JPEG/GIF/WebP/SVG, max 2 MB):

```bash
curl -X POST http://localhost:8000/api/v1/auth/register -F "organization_name=Odoo India" -F "name=John Doe" -F "email=john@odooindia.test" -F "password=Password123" -F "logo=@logo.png"
```

Returns `{ user, organization, tokens }`, where `user.login_id` is the generated
ID (`OIJODO20260001`) and `organization.code` its two-letter prefix (`OI`).

### `POST /auth/login` — public

One field takes either the login ID or the email address:

```json
{ "identifier": "OIJODO20220001", "password": "Password123" }
{ "identifier": "admin@acme.test", "password": "Password123" }
```

`login_id` and `email` are accepted as aliases for `identifier`.

```jsonc
{
  "success": true,
  "data": {
    "user": {
      "id": "…",
      "login_id": "ACAIKA20260001",
      "full_name": "Aisha Kapoor",
      "role": "admin",
      "panel": "admin",
      "must_change_password": false
    },
    "tokens": {
      "access_token": "eyJ…",
      "refresh_token": "eyJ…",
      "token_type": "Bearer",
      "expires_at": "2026-08-22T05:22:00+00:00",
      "expires_in": 3600
    },
    "realtime": { "channels": ["user:…", "org:…:panel:admin"] }
  }
}
```

`user.panel` (`admin` | `user`) is what the UI routes on.

### `POST /auth/refresh` — public

`{ "refresh_token": "…" }` → a new pair. **Rotation is single-use:** the
presented token is revoked, so replaying it returns 401 `refresh_revoked`.

### `POST /auth/logout`

`{ "refresh_token": "…" }`, or `?all=true` with an access token to end every
session. Succeeds even with an expired access token.

### `GET /auth/me`

Returns `{ user, organization, permissions, realtime }`. `permissions` carries
the capability flags the UI menus and guards read, including
`must_change_password` - true while the user is still on a system-generated
password, which is what sends them to the forced change-password screen.

### `GET /auth/sessions`

Active refresh sessions with IP and user agent — a "signed-in devices" list.

### `POST /auth/change-password`

`{ "current_password": "…", "new_password": "…" }`. Revokes every session on
success, so the user must sign in again everywhere.

---

## Profile (self-service)

| Method       | Path       | Notes                                              |
| ------------ | ---------- | -------------------------------------------------- |
| `GET`        | `/profile` | The signed-in user's record                        |
| `PATCH`/`PUT`| `/profile` | Editable: names, phone, designation, avatar, prefs |

Role, status and department are silently stripped here — those are admin-only.

---

## Users (admin panel)

Requires an admin-panel role. Create/reset additionally require
`super_admin`, `admin` or `hr`.

| Method   | Path                          | Notes                                    |
| -------- | ----------------------------- | ---------------------------------------- |
| `GET`    | `/users`                      | `?search=&role=&status=&department_id=`  |
| `POST`   | `/users`                      | Create an employee                       |
| `GET`    | `/users/stats`                | Counters for the dashboard               |
| `GET`    | `/users/{id}`                 | Self or admin                            |
| `PATCH`  | `/users/{id}`                 | Self or admin; role/status are privileged |
| `DELETE` | `/users/{id}`                 | Soft delete; attendance history is kept  |
| `POST`   | `/users/{id}/reset-password`  | Returns a temporary password             |

`POST /users` - the only way an employee account is created; they cannot
register themselves:

```json
{
  "email": "new@acme.test",
  "name": "Riya Nair",
  "role": "employee",
  "designation": "Software Engineer",
  "employee_id": "EMP007",
  "date_of_joining": "2026-04-01T00:00:00Z"
}
```

The response carries `login_id`, generated from the organization code, the
name, the joining year and that year's serial. Omit `password` and the API
generates one too, returning it **once** as `data.temporary_password` and
setting `must_change_password` - the employee signs in with those and is
required to choose their own password before anything else opens.

`name` may be sent as `first_name` / `last_name` instead. `date_of_joining`
defaults to now and decides the year segment of the ID. Nobody can change their
own role, and nobody can delete their own account.

`?search=` matches name, email, employee ID and login ID.

---

## Organization

| Method        | Path                       | Role                    |
| ------------- | -------------------------- | ----------------------- |
| `GET`         | `/organization`            | Any signed-in user      |
| `PATCH`/`PUT` | `/organization`            | `super_admin`, `admin`  |
| `POST`        | `/organization/logo`       | `super_admin`, `admin`  |
| `GET`         | `/organization/overview`   | Admin panel             |
| `GET`         | `/departments`             | Any signed-in user      |
| `POST`        | `/departments`             | `super_admin`/`admin`/`hr` |
| `GET`         | `/departments/{id}`        | Any signed-in user      |
| `PATCH`/`PUT` | `/departments/{id}`        | `super_admin`/`admin`/`hr` |
| `DELETE`      | `/departments/{id}`        | `super_admin`, `admin`  |

The working-hours fields drive attendance grading:

```json
{
  "work_start_time": "09:30",
  "work_end_time": "18:30",
  "late_grace_minutes": 15,
  "full_day_hours": 8,
  "half_day_hours": 4,
  "working_days": [0, 1, 2, 3, 4],
  "timezone": "Asia/Kolkata"
}
```

`settings` is merged, not replaced, so a partial update cannot wipe flags.

`POST /organization/logo` is `multipart/form-data` with the image under `logo`.
It replaces the previous file and returns `{ logo_url, organization }`.
`logo_url` is absolute (built from `API_PUBLIC_URL`) so the UI can load it from
its own origin. Read-only fields: `code` is fixed at signup, because every login
ID in the organization is built on it.

---

## Attendance (user panel)

| Method | Path                       | Notes                                       |
| ------ | -------------------------- | ------------------------------------------- |
| `GET`  | `/attendance/status`       | Today's punch state for the check-in widget |
| `POST` | `/attendance/check-in`     | 409 if already checked in                   |
| `POST` | `/attendance/check-out`    | 409 if not checked in                       |
| `GET`  | `/attendance/me`           | `?date_from=&date_to=&status=`              |
| `GET`  | `/attendance/me/summary`   | Defaults to the last 30 days                |

`POST /attendance/check-in` accepts `{ "source": "web", "note": "…", "location": {} }`.

One document holds one user's whole day; several check-in/check-out pairs live
in `sessions[]`, and `total_seconds` / `status` are recomputed on each punch.
Lateness is judged against the org's `work_start_time` plus the grace window,
in the org's own timezone.

---

## Attendance (admin panel)

Requires an admin-panel role.

| Method   | Path                                            | Notes                          |
| -------- | ----------------------------------------------- | ------------------------------ |
| `GET`    | `/admin/attendance`                             | `?user_id=&date_from=&date_to=&status=` |
| `POST`   | `/admin/attendance`                             | Manual entry / correction      |
| `GET`    | `/admin/attendance/overview`                    | Who is in today                |
| `GET`    | `/admin/attendance/{id}`                        | One record                     |
| `DELETE` | `/admin/attendance/{id}`                        | Soft delete                    |
| `GET`    | `/admin/attendance/users/{user_id}/summary`     | Per-employee totals            |

`POST /admin/attendance` (upsert — writing the same date twice replaces it):

```json
{
  "user_id": "…",
  "date": "2026-08-21",
  "check_in": "2026-08-21T04:00:00Z",
  "check_out": "2026-08-21T13:00:00Z",
  "status": "present",
  "note": "Forgot to punch in"
}
```

List rows inline the employee as `record.user`, so the table needs no second call.

---

## Platform

| Method | Path                                | Auth              |
| ------ | ----------------------------------- | ----------------- |
| `GET`  | `/` (API host root)                 | Public - redirects a browser to the sign-in page, returns the route map to JSON clients |
| `GET`  | `/api/v1/`                          | Public - route map |
| `GET`  | `/media/...`                        | Public - uploaded logos (dev; nginx or object storage in production) |
| `GET`  | `/health`                           | Public - Mongo + hub status (503 when Mongo is down) |
| `POST` | `/internal/realtime/presence`       | `x-internal-key` - the hub reports connect/disconnect |
