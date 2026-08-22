# Claims, Fines, and Employee Requests Module

The **Claims, Fines, and Employee Requests Module** provides an end-to-end management system for employee expense reimbursements, administrative fines, and hardware/ID card service requests.

---

## Architecture & Data Models (`apps/claims/models.py`)

### 1. `ExpenseClaim`
- `organization`: Reference to `Organization`.
- `employee`: Reference to `User`.
- `expense_type`: Choice field (`Travel`, `Food`, `Accommodation`, `Transportation`, `Other`).
- `custom_expense_type`: Description when type is `Other`.
- `amount`: Claim amount in INR (must be > 0).
- `expense_date`: Date expense was incurred.
- `description`: Business purpose explanation.
- `receipt_filename`: Stored file name inside `attachment_assets/`.
- `original_filename`: Original uploaded filename.
- `status`: Status choice (`PENDING`, `APPROVED`, `REJECTED`).
- `reviewed_by`: Reference to admin reviewer.
- `review_comment`: Admin comment upon approval/rejection.

### 2. `Fine`
- `organization`: Reference to `Organization`.
- `employee`: Reference to `User`.
- `amount`: Fine amount in INR.
- `reason`: Administrative justification for fine.
- `date`: Fine issue date.
- `status`: Status choice (`ACTIVE`, `CANCELLED`).
- `applied_by`: Admin who issued fine.

### 3. `EmployeeRequest`
- `organization`: Reference to `Organization`.
- `employee`: Reference to `User`.
- `request_type`: Single-select choice (`id_card`, `laptop`, `other`).
- `description`: Details of request.
- `attachment_filename`: Optional uploaded attachment inside `attachment_assets/`.
- `status`: Status choice (`PENDING`, `APPROVED`, `REJECTED`).
- `rejection_reason`: Admin rejection comment.

---

## Storage & Access Security

- Uploaded receipts and document attachments are stored strictly inside the `attachment_assets/` directory at project root.
- Path `attachment_assets/` is added to `.gitignore`.
- Served via secure API endpoints (`/api/v1/claims/<id>/attachment` & `/api/v1/requests/<id>/attachment`).
- Enforces strict authorization checks: only the employee owner or authorized administrators can access attachments.

---

## Backend API Endpoints (`apps/claims/urls.py`)

### Employee Endpoints
- `GET /api/v1/claims`: List employee's expense claims.
- `POST /api/v1/claims`: Submit new claim with receipt file.
- `GET /api/v1/claims/<id>/attachment`: Secure receipt download.
- `GET /api/v1/fines`: Read-only list of fines applied to employee.
- `GET /api/v1/requests`: List employee requests.
- `POST /api/v1/requests`: Submit request with single request type validation and optional attachment.
- `GET /api/v1/requests/<id>/attachment`: Secure request attachment download.

### Admin Endpoints
- `GET /api/v1/admin/claims`: List incoming claims queue (filterable by status).
- `POST /api/v1/admin/claims/<id>/approve`: Approve claim with comment.
- `POST /api/v1/admin/claims/<id>/reject`: Reject claim with comment.
- `GET /api/v1/admin/fines`: List issued fines.
- `POST /api/v1/admin/fines`: Apply fine to employee.
- `PATCH /api/v1/admin/fines/<id>`: Update fine status (`ACTIVE` / `CANCELLED`).
- `GET /api/v1/admin/requests`: List incoming employee requests.
- `POST /api/v1/admin/requests/<id>/approve`: Approve request.
- `POST /api/v1/admin/requests/<id>/reject`: Reject request with rejection reason.

---

## Frontend Angular Implementation

- **Expense Claims (`/claims`)**: Submit claim modal with receipt file upload, claim history table, and status badges.
- **My Fines (`/fines`)**: Read-only dashboard of active fines.
- **Employee Requests (`/requests`)**: Single-select request type form (`ID Card`, `Laptop`, `Other`), description, attachment upload, and status tracker.
- **Claim Approvals (`/settings/claims-approvals`)**: Admin claim queue, receipt viewer, and approve/reject modal.
- **Fines Management (`/settings/fines-management`)**: Admin fine issuer and status toggler.
- **Incoming Requests (`/settings/incoming-requests`)**: Admin incoming request queue, filter by type/status, attachment downloader, and approve/reject modal.
