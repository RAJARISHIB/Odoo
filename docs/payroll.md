# HRMS Payroll Module

The **HRMS Payroll Module** provides end-to-end salary management, role-level salary templates, employee payroll assignment (`ROLE` vs `MANUAL` sources), backend salary calculation & dependency resolution, Provident Fund (PF) calculations, Professional Tax, and secure payslip/document management.

---

## Key Features

1. **Role Salary Templates**:
   - Define prefilled salary structures per Role (`Software Developer`, `Head of Engineering`, `HR Manager`, etc.).
   - Configurable monthly wage, automatic annual CTC (`monthly × 12`), salary component rules, Employee/Employer PF rates, PF base component, and Professional Tax.

2. **Employee Payroll Assignments (`ROLE` vs `MANUAL`)**:
   - `ROLE` source: Inherits and pre-fills the role's salary structure. When the role template is updated, `ROLE` employees update automatically.
   - `MANUAL` source: Independent custom salary structure for an employee. Manual employee salaries are **never silently overwritten** when role templates change.
   - Effective date support (`effective_from`).

3. **Backend Salary Calculation Engine (`apps/payroll/calculator.py`)**:
   - Resolves component dependency chains (e.g., Basic Salary = 50% of Wage, HRA = 50% of Basic, Standard Allowance = 16.67%, Performance Bonus = 8.33%, LTA = 8.33%, Fixed Allowance = remainder).
   - Automatically recalculates all dependent components when wage/base changes.
   - Detects and rejects circular component dependencies.
   - Computes Gross Salary, Employee/Employer PF, Professional Tax, Total Deductions, and Net Take-Home Pay.

4. **Payroll Documents & Payslip Uploads**:
   - Admins can upload monthly payslips, offer letters, annual CTC documents, and salary revision letters for employees.
   - Files land in `attachment_assets/` and are protected with authorization checks so employees can only access **their own authorized documents**.
   - Serves `FileResponse` with explicit MIME `Content-Type: application/pdf` and binary header preservation.

---

## Domain Models (`apps/payroll/models.py`)

- **`SalaryComponent`**: Embedded document (`name`, `calculation_type` [`PERCENTAGE` / `FIXED_AMOUNT`], `value`, `depends_on`, `is_fixed_allowance_remainder`, `calculated_amount`).
- **`RoleSalaryTemplate`**: Salary template per role/designation (`monthly_wage`, `yearly_wage`, `components`, `employee_pf_rate`, `employer_pf_rate`, `pf_base_component`, `professional_tax`, `working_days_per_week`).
- **`EmployeePayroll`**: Assigned payroll record per employee (`salary_source` [`ROLE` / `MANUAL`], `role_template`, `monthly_wage`, `yearly_wage`, `components`, `gross_salary`, `total_deductions`, `net_salary`, `effective_from`).
- **`PayrollDocument`**: Employee payslips and CTC files (`document_type` [`PAYSLIP`, `OFFER_LETTER`, `CTC_DETAILS`, `REVISION_LETTER`, `OTHER`], `payroll_month`, `payroll_year`, `filename`, `original_filename`, `uploaded_by`).

---

## Backend API Endpoints (`apps/payroll/urls.py`)

### Employee Endpoints
- `GET /api/v1/payroll/me`: Get signed-in employee's payroll & itemized salary breakdown.
- `GET /api/v1/payroll/me/documents`: Get signed-in employee's payslips and CTC documents.
- `GET /api/v1/payroll/documents/<document_id>/download`: Secure document file download.

### Admin Endpoints
- `GET /api/v1/admin/payroll/templates`: List role salary templates.
- `POST /api/v1/admin/payroll/templates`: Create/update role salary template (cascades to `ROLE` employees).
- `GET /api/v1/admin/payroll/templates/<id>`: Get role salary template details.
- `POST /api/v1/admin/payroll/preview`: Live calculation preview endpoint.
- `GET /api/v1/admin/payroll/employees`: List all employee payroll assignments.
- `GET /api/v1/admin/payroll/employees/<user_id>`: Get specific employee payroll.
- `POST /api/v1/admin/payroll/employees`: Assign/update employee payroll (`ROLE` vs `MANUAL`).
- `GET /api/v1/admin/payroll/documents`: List payroll documents.
- `POST /api/v1/admin/payroll/documents`: Upload employee payslip/document.
- `DELETE /api/v1/admin/payroll/documents/<id>`: Delete payroll document.

---

## Frontend Angular Implementation

- **My Payroll (`/payroll`)**: Employee dashboard with Monthly/Yearly Wage, Gross Earnings, Net Take-Home Pay, itemized earnings breakdown table, deductions summary, and payslip download history.
- **Role Salary Templates (`/settings/payroll-templates`)**: Admin template manager with component rule editor and live salary preview sidebar.
- **Employee Payroll (`/settings/payroll-assignments`)**: Admin assignment modal with `ROLE` vs `MANUAL` source toggle, custom component editor, effective date picker, and live calculation preview.
- **Payroll Documents (`/settings/payroll-documents`)**: Admin document uploader with employee selector, document type picker, month/year picker, and file table.
