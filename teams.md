# Teams & Organizational Hierarchy Module

The **Teams & Organizational Hierarchy Module** provides full support for creating teams, managing team members, setting up custom team hierarchy ranks, moving employees between teams, and visualizing team structures.

---

## Architecture & Data Models

### 1. Data Models (`apps/teams/models.py`)

- **`Team`**:
  - `organization`: Reference to `Organization`.
  - `name`: Team name (e.g., "Core Engineering").
  - `code`: Unique code per organization.
  - `description`: Team purpose / description.
  - `manager`: Reference to `User` assigned as team lead.
  - `is_active`: Boolean status flag.

- **`TeamHierarchyLevel`**:
  - `organization`: Reference to `Organization`.
  - `team`: Reference to `Team`.
  - `name`: Level name (e.g., "Engineering Director", "Lead Architect", "Senior Developer", "Intern").
  - `rank`: Integer rank ordering (`1`, `2`, `3`...). Lower numbers indicate higher seniority.
  - `description`: Role responsibilities.

- **`TeamMember`**:
  - `organization`: Reference to `Organization`.
  - `team`: Reference to `Team`.
  - `user`: Reference to `User`.
  - `hierarchy_level`: Reference to `TeamHierarchyLevel`.
  - `role_title`: Custom title within the team.
  - `joined_at`: Assignment timestamp.

---

## Business Logic & Services (`apps/teams/services.py`)

- **Team Management**:
  - `create_team(organization, data)`
  - `update_team(organization, team_id, data)`
  - `deactivate_team(organization, team_id)`
  - `list_teams(organization)`

- **Member & Hierarchy Assignment**:
  - `add_team_member(organization, team_id, user_id, hierarchy_level_id)`: Updates existing member document in-place if member already belongs to the team.
  - `remove_team_member(organization, team_id, user_id)`
  - `move_team_member(organization, from_team_id, to_team_id, user_id, new_hierarchy_level_id)`: Safely transfers an employee between teams and updates hierarchy level.
  - `assign_hierarchy_level(organization, team_id, user_id, hierarchy_level_id)`: In-place hierarchy level update with rank validation.

- **Hierarchy Structure & Tree API**:
  - `get_team_hierarchy_tree(organization, team_id)`: Groups team members by hierarchy rank order (`Rank 1`, `Rank 2`...) and returns serialized nodes for visualization.

---

## Backend API Endpoints (`apps/teams/urls.py`)

### Employee Endpoints
- `GET /api/v1/teams/my-team`: Get signed-in employee's team details and teammates.
- `GET /api/v1/teams/availability`: Get team availability status.
- `GET /api/v1/teams/birthdays`: Get upcoming team birthdays.

### Admin Endpoints
- `GET /api/v1/admin/teams`: List all teams in organization.
- `POST /api/v1/admin/teams`: Create a new team.
- `GET /api/v1/admin/teams/<team_id>`: Get team details.
- `PATCH /api/v1/admin/teams/<team_id>`: Update team details.
- `DELETE /api/v1/admin/teams/<team_id>`: Deactivate team.
- `GET /api/v1/admin/teams/<team_id>/members`: List team members.
- `POST /api/v1/admin/teams/<team_id>/members`: Add employee to team.
- `DELETE /api/v1/admin/teams/<team_id>/members/<user_id>`: Remove employee from team.
- `POST /api/v1/admin/teams/<team_id>/move-member`: Transfer employee to another team.
- `GET /api/v1/admin/teams/<team_id>/hierarchy`: List team hierarchy levels.
- `POST /api/v1/admin/teams/<team_id>/hierarchy`: Create hierarchy level.
- `PATCH /api/v1/admin/teams/<team_id>/members/<user_id>/hierarchy`: Update employee hierarchy level.

---

## Frontend Angular Implementation

- **My Team (`/teams`)** ([`my-team.ts`](file:///d:/ODOO/frontend/src/app/features/teams/my-team/my-team.ts)): Employee team view displaying team lead, hierarchy breakdown, team availability, and teammate list.
- **Manage Teams (`/settings/teams`)** ([`manage-teams.html`](file:///d:/ODOO/frontend/src/app/features/admin/teams/manage-teams.html)): Admin interface to create teams, configure hierarchy ranks with `.order-badge` single-line Rank labels, assign/move members, and view team hierarchy trees.
