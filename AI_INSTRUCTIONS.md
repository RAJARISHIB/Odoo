# HRMS Portal - AI Context & Development Guidelines

This file is a living document intended for AI assistants and developers contributing to this HRMS portal. It outlines the current state of the project, architectural rules, and implementation patterns.

## Current Project Scope & Implemented Modules

1. **Authentication & Identity**: JWT-based login, signup, refresh rotation, organization multi-tenancy.
2. **Employee Directory**: Profile viewing, user data structures, departments.
3. **Attendance Tracking**: Clock in/out, view team logs, edit work sessions.
4. **Calendar & Leaves**: Leave requests, balances, approvals workflow, and leave types.
5. **Roles & Access Control (RBAC)**: 
   - **Per-Organization Custom Roles**: Organizations can create custom roles or modify default system roles.
   - **Granular Permissions Catalog**: Permissions are formatted as `module.action` (e.g., `users.view`, `leaves.approve`).
   - **Decorator Guard**: Endpoints are protected via `@permissions_required(Permissions.XYZ)` instead of legacy hardcoded role string checks.
6. **Realtime WebSocket Hub**: An Express server broadcasts system events (like `user.updated` or `attendance.punch`) to subscribed Angular clients to update the UI instantly without polling.

## Architectural Rules

### 1. Backend (Django + MongoEngine)
- **Thin Views, Thick Controllers**: `views.py` must only contain method mapping and decorators (e.g. `@permissions_required`). All business logic belongs in `services.py`, and request validation/HTTP response mapping belongs in `controllers.py` (subclassing `BaseController`).
- **Response Envelope**: Every API endpoint MUST return a consistent JSON shape. Do not throw raw 500s or mismatched JSON. Use `controller.success()` or raise `ValidationError` which the middleware catches.
  - Success: `{ "success": true, "data": {...}, "message": "..." }`
  - Failure: `{ "success": false, "error": { "code": "...", "message": "..." } }`
- **Granular Permissions**: Do not use `@admin_required` or check `user.role == 'hr'`. Always use `@permissions_required` and query `user.has_permission(Permissions.XYZ)`.

### 2. Realtime Layer (Express)
- **No Direct Sockets from Django**: Django is synchronous and never holds a WebSocket. When Django needs to notify the UI, it sends a POST to the Express hub (`/internal/publish`) using the shared `INTERNAL_API_KEY`.
- **Shared Token**: The Express hub parses and verifies the exact same JWT `ACCESS_TOKEN` issued by Django.

### 3. Frontend (Angular)
- **Standalone Components**: The UI uses Angular 21 Standalone components (no `NgModule`).
- **Permission Guards**: UI elements and router paths should check against the `permissions: string[]` array delivered inside the auth payload `data.user.permissions`. Use `*ngIf="hasPermission('leaves.approve')"` instead of checking `role === 'admin'`.

## Pending Roadmap
- Payroll & Compensation module
- File/Document uploads (e.g., offer letters, medical certificates)
- System email delivery (currently passwords and invites are just returned in the HTTP response for dev simplicity)


### 4. Dynamic Role-Based Access Control (RBAC) & Team Filtering
- **Database Model**: `Role` is a MongoEngine document assigned per organization. `user.role` is a `ReferenceField`, so legacy code using `user.role == 'manager'` string comparisons is strictly prohibited.
- **Granular Checks**: Use `user.has_permission(Permissions.LEAVES_APPROVE)` inside services. Controllers use the decorators `@permissions_required(...)` or the helper `self.require_any_permission(...)` instead of `@roles_required`.
- **Manager Delegation (Hierarchy Filtering)**: By default, users with `Permissions.ORG_MANAGE` can perform administrative actions (e.g. approve leaves) for the *entire* organization. Users with only module-specific approval permissions (e.g., `Permissions.LEAVES_APPROVE`) act as "Managers".
- **Subordinate Resolution**: To prevent cross-team leaking, Manager endpoints must filter database queries using `apps.teams.services.get_subordinate_ids(organization, user)`. This function resolves direct and indirect subordinates by checking the `TeamHierarchyLevel` order inside the `TeamMember` assignments (where a lower order number means higher rank, e.g. 1 = Lead, 2 = Developer).
- **Frontend Compatibility**: The Angular client currently expects legacy boolean capability flags (`can_manage_users`, etc.). To maintain compatibility, `AuthController._permissions(user)` acts as an adapter, translating the granular database permissions into the boolean flags the UI `capabilityGuard` requires.
