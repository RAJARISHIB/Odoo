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

Bootstrap: creates an organization plus its first `super_admin`, and signs them in.

```json
{
  "organization_name": "Acme Corp",
  "email": "owner@acme.test",
  "password": "Password123",
  "first_name": "Owner",
  "last_name": "Acme"
}
```

Returns `{ user, organization, tokens }`.

### `POST /auth/login` — public

```json
{ "email": "admin@acme.test", "password": "Password123" }
```

```jsonc
{
  "success": true,
  "data": {
    "user": { "id": "…", "full_name": "Aisha Kapoor", "role": "admin", "panel": "admin", … },
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
the capability flags the UI menus and guards read.

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

`POST /users`:

```json
{
  "email": "new@acme.test",
  "first_name": "Riya",
  "last_name": "Nair",
  "role": "employee",
  "designation": "Software Engineer",
  "employee_id": "EMP007"
}
```

Omit `password` and the API generates one, returning it **once** as
`data.temporary_password`. Nobody can change their own role, and nobody can
delete their own account.

---

## Organization

| Method        | Path                       | Role                    |
| ------------- | -------------------------- | ----------------------- |
| `GET`         | `/organization`            | Any signed-in user      |
| `PATCH`/`PUT` | `/organization`            | `super_admin`, `admin`  |
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
| `GET`  | `/`                                 | Public - route map |
| `GET`  | `/health`                           | Public - Mongo + hub status (503 when Mongo is down) |
| `POST` | `/internal/realtime/presence`       | `x-internal-key` - the hub reports connect/disconnect |
