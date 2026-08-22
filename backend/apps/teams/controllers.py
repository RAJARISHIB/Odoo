"""Teams controllers."""
from apps.teams import services
from core.base_controller import BaseController
from core.constants import Role


class TeamAdminController(BaseController):
    """Admin-facing teams controller: /api/v1/admin/teams/*"""

    def list(self):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR, Role.MANAGER)
        queryset = services.list_teams(self.user.organization, status=self.param("status"))
        return self.paginated(queryset)

    def create(self):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR)
        team = services.create_team(self.user.organization, self.data)
        return self.created(team.to_dict(), "Team created successfully.")

    def retrieve(self, team_id: str):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR, Role.MANAGER)
        team = services.get_team(self.user.organization, team_id)
        return self.ok(team.to_dict())

    def update(self, team_id: str):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR)
        team = services.update_team(self.user.organization, team_id, self.data)
        return self.ok(team.to_dict(), "Team updated successfully.")

    def destroy(self, team_id: str):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR)
        services.delete_team(self.user.organization, team_id)
        return self.deleted("Team deactivated successfully.")

    # Hierarchy
    def list_hierarchy(self, team_id: str):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR, Role.MANAGER)
        team = services.get_team(self.user.organization, team_id)
        levels = services.list_hierarchy_levels(team)
        return self.ok([l.to_dict() for l in levels])

    def create_hierarchy(self, team_id: str):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR)
        team = services.get_team(self.user.organization, team_id)
        level = services.create_hierarchy_level(team, self.data)
        return self.created(level.to_dict(), "Hierarchy level created.")

    def update_hierarchy(self, team_id: str, level_id: str):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR)
        team = services.get_team(self.user.organization, team_id)
        level = services.update_hierarchy_level(team, level_id, self.data)
        return self.ok(level.to_dict(), "Hierarchy level updated.")

    def reorder_hierarchy(self, team_id: str):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR)
        team = services.get_team(self.user.organization, team_id)
        levels = services.reorder_hierarchy_levels(team, self.field("levels") or self.data)
        return self.ok([l.to_dict() for l in levels], "Hierarchy reordered.")

    def delete_hierarchy(self, team_id: str, level_id: str):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR)
        team = services.get_team(self.user.organization, team_id)
        services.delete_hierarchy_level(team, level_id)
        return self.deleted("Hierarchy level removed.")

    # Members
    def list_members(self, team_id: str):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR, Role.MANAGER)
        team = services.get_team(self.user.organization, team_id)
        members = services.list_team_members(team)
        return self.ok([m.to_dict() for m in members])

    def add_member(self, team_id: str):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR, Role.MANAGER)
        team = services.get_team(self.user.organization, team_id)
        self.require("user_id")
        member = services.add_team_member(
            self.user.organization,
            team,
            user_id=self.field("user_id"),
            hierarchy_level_id=self.field("hierarchy_level_id"),
        )
        return self.created(member.to_dict(), "Employee added to team.")

    def remove_member(self, team_id: str, user_id: str):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR, Role.MANAGER)
        team = services.get_team(self.user.organization, team_id)
        services.remove_team_member(self.user.organization, team, user_id)
        return self.deleted("Employee removed from team.")

    def move_member(self):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR, Role.MANAGER)
        self.require("user_id", "target_team_id")
        member = services.move_team_member(
            self.user.organization,
            user_id=self.field("user_id"),
            target_team_id=self.field("target_team_id"),
            target_hierarchy_level_id=self.field("hierarchy_level_id"),
        )
        return self.ok(member.to_dict(), "Employee moved to new team.")

    def assign_hierarchy(self, team_id: str, user_id: str):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR, Role.MANAGER)
        team = services.get_team(self.user.organization, team_id)
        member = services.assign_hierarchy_level(
            team,
            user_id=user_id,
            hierarchy_level_id=self.field("hierarchy_level_id"),
        )
        return self.ok(member.to_dict(), "Hierarchy level assigned.")


class TeamEmployeeController(BaseController):
    """Employee-facing teams controller: /api/v1/teams/*"""

    def my_team(self):
        user = self.require_user()
        data = services.get_my_team(user.organization, user)
        return self.ok(data)

    def availability(self):
        user = self.require_user()
        data = services.get_team_availability(
            user.organization,
            user,
            target_date_str=self.param("date"),
        )
        return self.ok(data)

    def birthdays(self):
        user = self.require_user()
        data = services.get_team_birthdays(
            user.organization,
            user,
            ref_date_str=self.param("date"),
        )
        return self.ok(data)
