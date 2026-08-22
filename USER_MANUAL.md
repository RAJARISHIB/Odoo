# Dayflow HRMS — User Manual

Dayflow is one app for everyone in an organization — there's no separate
admin site. What you can do depends on your role and the permissions your
organization has granted it; extra controls simply appear (or don't) on the
same screens everyone else uses.

## 1. Getting started

### Creating an organization

The very first account for a company is created at **Create an organization**
(`/auth/register`): company name, your name, email, and a password. This
creates your company's workspace and makes you its **Super Admin**. You're
issued a system-generated **login ID** (e.g. `OIJODO20220001|`) — that, or
your email, is how you'll sign in from now on. Because you just proved
control of that email by completing signup with it, your account starts
already email-verified.

Nobody else can self-register. Every other person in the organization is
created by an admin/HR user from **Settings → People** — see §7.

### Signing in

Go to **Sign in**, enter your login ID or email plus your password. If your
account was just created by an admin, you'll be prompted to set your own
password before you can do anything else (see §3.1).

### Forgot your password?

Click **Forgot password?** on the sign-in page, enter your login ID or
email, and submit. You'll always see the same confirmation message —
*"If an account exists for that email or login ID, a reset link has been
sent"* — whether or not it actually matched an account, so this page can't be
used to check who has an account. If it matched, check your email for a
reset link (valid for 1 hour, usable once).

## 2. Signing in with two-factor authentication (MFA)

If you've turned on MFA (§3.2), signing in takes one extra step: after your
password is accepted, you'll land on a **Two-factor verification** screen.
Enter the 6-digit code from your authenticator app, or one of your saved
recovery codes, and submit. Until that second step succeeds, no session has
actually been created — closing or refreshing this page abandons the
sign-in attempt and sends you back to the login form.

## 3. Your profile & account security (`/me`)

Everyone reaches their own **Profile** page from the sidebar (bottom user
chip). Three things live here:

### 3.1 Personal details & password

Edit your name, phone, and designation; your login ID, email, and role are
shown read-only underneath (contact an admin to change those). A separate
**Change password** panel asks for your current password plus a new one —
changing it **signs you out of every other device**, so you'll need to sign
in again there too.

### 3.2 Two-factor authentication (MFA)

If MFA isn't on yet, click **Enable MFA**. You'll get a QR code — scan it
with an authenticator app (Google Authenticator, Microsoft Authenticator,
Authy, or similar); if you can't scan, the same secret is shown as text to
enter manually. Enter the 6-digit code your app now shows to confirm.

Once confirmed, you'll see **10 recovery codes** — save them somewhere safe
right now. They're shown exactly once and let you sign in if you ever lose
your authenticator device; each code works only once.

With MFA already on, this card instead shows **Regenerate recovery codes**
and **Disable MFA** — both ask you to re-enter your current password plus a
valid code before doing anything, and disabling signs you out of every other
device.

> Some administrative actions (see §8) require MFA to be turned on,
> regardless of your role — including for Super Admins.

### 3.3 Active sessions

A list of every device currently signed in to your account, each with its
browser/device string, IP address, and sign-in time; the one you're using
right now is marked **This device**. Sign out any other device individually,
or use **Sign out all other sessions** to clear every one of them at once.

## 4. Employee directory (`/employees`)

A searchable card grid of everyone in the organization — search by name,
email, or employee ID, and filter by department or role. If you can see
organization-wide attendance, each card also shows a live presence marker
(in office / checked out / on leave / absent). Click a card to see someone's
detail page: contact info, department, join date, last sign-in, and (if
you have attendance visibility) their last-30-days attendance summary. This
page is read-only everywhere except your own profile, which links to
**Edit my profile** instead.

## 5. Attendance

### 5.1 Checking in and out

A small widget lives in the top bar on every page — a status dot, an elapsed
timer once you're checked in, and a single **Check in** / **Check out**
button. That's the only place punching happens; there's no separate button
on the attendance page itself.

Your **Attendance** page shows your own history: total days, hours, present/
late/absent counts, and a filterable table (date range, status) of every
day recorded, including first-in/last-out times and whether a session is
still open.

### 5.2 Lateness and half-days

Your organization sets a shift start time and a grace period; check in after
grace and that day is marked **Late**. Your organization also sets full-day
and half-day hour thresholds — work fewer hours than the half-day threshold
and the day may be adjusted accordingly once you check out.

### 5.3 Team attendance board (admin/manager)

At **Attendance → Team**, see everyone's attendance for a given period, with
filters by employee/date/status. **+ Manual entry** lets you record or
correct a day for someone directly (employee, date, status, check-in/out
times, and a reason) — useful for forgotten punches or corrections. Rows can
also be removed if entered in error.

## 6. Time off (leave)

### 6.1 Applying for leave

At **Time off**, you'll see your balance at a glance (entitlement, used,
pending, remaining) and a month calendar marking holidays and your own leave
requests. Click **+ Apply for Leave** (or click a day on the calendar), pick
a **leave type**, start and end dates, and a reason. As you fill this in,
you'll see a live line telling you how many days remain of that specific
leave type and whether this request would exceed what's left — the submit
button disables itself if it would. Below the calendar, a table of your
submitted requests lets you cancel anything not yet cancelled.

### 6.2 Approvals (admin/manager)

At **Time off → Approvals**, review every pending request org-wide (filter
by employee/status/type). Each row lets you optionally correct/assign the
leave type before deciding, then **Approve** or **Reject** (rejecting asks
for an optional comment) — both update instantly for everyone watching that
request.

### 6.3 Leave insights (admin)

At **Settings → Leave insights**, see org-wide totals (allocated, used,
pending) and a per-employee utilization table for a chosen year and leave
type. Click any employee row to drill into their per-type breakdown, full
leave history, and to make a manual **balance adjustment** (a signed amount
with a required reason) — used for corrections or one-off credits.

### 6.4 Holidays (admin)

At **Settings → Holidays**, browse and add holidays by year (name, date,
type: government/festival/organization/optional, description). Holidays
already in the past are **locked** — they can no longer be edited, only
future/current ones can.

### 6.5 Leave policy configuration (admin)

At **Settings → Leave policy**, two tabs:

- **Leave types** — define what kinds of leave exist (paid or unpaid,
  fractional half-days allowed, a maximum days-per-request cap, whether
  approval is required, and an optional **carry-forward** rule — a
  percentage of unused balance rolled into the next month or year).
  Types aren't deleted, only activated/deactivated.
- **Allocation rules** — how much of a leave type each role accrues, and how
  often. **Generate accrual** runs the actual crediting for a chosen
  period (safe to re-run — it only credits what hasn't already been
  credited). **Carry forward** runs the configured rollover for a chosen
  leave type and period.

## 7. People management (admin)

At **Settings → People**, manage everyone's account (separate from the
read-only Employee Directory in §4):

- **Add employee** — name, email, designation, employee ID, role; leave
  the password field blank to have one generated automatically.
- Whenever an account is created or its password reset, a **Sign-in
  details** banner shows the login ID and password once — share it with
  the employee securely; they must change it on first sign-in.
- Per-row actions: **Reset** (issues a new temporary password), **Suspend/
  Activate**, and **Remove** (keeps their attendance/leave history, just
  disables the account — you can't remove your own account this way).

> You can only assign a role ranked at or below your own — an HR account,
> for example, cannot create an Admin or Super Admin account, and nobody
> can change their own role. This is enforced by the server regardless of
> what the interface shows.

## 8. Organization settings (admin)

At **Settings → Organization**: company profile (name, email, phone,
address, timezone) and the **working-hours policy** that attendance grading
uses (shift start/end, late grace minutes, full/half-day hour thresholds,
working days of the week). A separate **Departments** panel lets you add or
remove departments.

## 9. Security administration

A few controls are for whoever holds the relevant permission (by default,
Admins and Super Admins for most of these — organizations can adjust who
holds what, see §10):

- **Role permissions** — `PUT /api/v1/admin/roles/<role>/permissions` lets
  an authorized admin change exactly what a role can do, rather than being
  stuck with fixed Admin/HR/Employee behavior. (No dedicated screen exists
  for this yet — it's reachable via the API today.)
- **Audit log** — `GET /api/v1/admin/audit-logs` is a read-only, tamper-proof
  record of security-relevant events: sign-ins and failures, password/MFA
  changes, role changes, user creation/removal, leave approvals and balance
  adjustments, holiday changes, and denied access attempts. Nobody — including
  admins — can edit or delete an entry through the app.
- Accessing the audit log, editing role permissions, or exporting bulk
  payroll data all require **MFA to be turned on** for your account first,
  regardless of role.

## 10. Roles reference

| Role | Typical access |
|---|---|
| **Employee** | Own profile, attendance, leave, and (once built) payroll/documents. Nothing about anyone else by default. |
| **Manager** | Same baseline as Employee. Broader visibility (team attendance, leave approval) is granted per-organization, not automatic. |
| **HR** | Employee directory management, leave approval/configuration, attendance visibility. Payroll and audit-log access are opt-in, not automatic. |
| **Admin** | Everything HR has, plus user/role management, security settings, and audit-log access — but even Admin does **not** automatically see bulk salary data; that stays a separate, explicit grant. |
| **Super Admin** | Full access to everything, always — the only role whose permission set can't be edited down. |

Whatever your role, remember: what an admin *can* see or do is decided by
the server on every request, not by what a screen happens to show — hiding
a button in the interface is a convenience, not the actual boundary.

## 11. Troubleshooting

- **"Too many attempts, try again later"** — your account (or your network)
  hit the sign-in attempt limit. Wait a few minutes and try again, or use
  **Forgot password?** if you're unsure of your password.
- **Locked out after enabling MFA and losing your device** — use one of your
  10 recovery codes on the two-factor screen instead of a TOTP code. If
  you've used all of them, ask an admin to reset your account.
- **"Please re-enter your password to continue"** — a handful of sensitive
  actions (changing a role, disabling MFA) need proof you signed in
  recently, even if your session is technically still valid. Re-enter your
  password (and MFA code, if enabled) to proceed.
- **A reset/verification email never arrives** — check spam first; if your
  organization hasn't configured outgoing email yet, ask your administrator
  — in that case the email is only logged to the server console, not
  actually delivered.
