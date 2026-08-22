"""Teams views - thin wrappers around TeamAdminController and TeamEmployeeController."""
from apps.teams.controllers import TeamAdminController, TeamEmployeeController
from core.decorators import admin_required, api_view, auth_required


# ---------------------------------------------------------------------------
# Employee Views (/api/v1/teams/*)
# ---------------------------------------------------------------------------
@api_view("GET")
@auth_required
def my_team(request):
    return TeamEmployeeController(request).my_team()


@api_view("GET")
@auth_required
def availability(request):
    return TeamEmployeeController(request).availability()


@api_view("GET")
@auth_required
def birthdays(request):
    return TeamEmployeeController(request).birthdays()


# ---------------------------------------------------------------------------
# Admin Views (/api/v1/admin/teams/*)
# ---------------------------------------------------------------------------
@api_view("GET", "POST")
@admin_required
def admin_teams_collection(request):
    controller = TeamAdminController(request)
    if request.method == "POST":
        return controller.create()
    return controller.list()


@api_view("GET", "PATCH", "DELETE")
@admin_required
def admin_team_detail(request, team_id):
    controller = TeamAdminController(request)
    if request.method == "PATCH":
        return controller.update(team_id)
    elif request.method == "DELETE":
        return controller.destroy(team_id)
    return controller.retrieve(team_id)


@api_view("GET", "POST")
@admin_required
def admin_team_hierarchy_collection(request, team_id):
    controller = TeamAdminController(request)
    if request.method == "POST":
        return controller.create_hierarchy(team_id)
    return controller.list_hierarchy(team_id)


@api_view("PATCH", "DELETE")
@admin_required
def admin_team_hierarchy_detail(request, team_id, level_id):
    controller = TeamAdminController(request)
    if request.method == "DELETE":
        return controller.delete_hierarchy(team_id, level_id)
    return controller.update_hierarchy(team_id, level_id)


@api_view("PATCH")
@admin_required
def admin_team_hierarchy_reorder(request, team_id):
    return TeamAdminController(request).reorder_hierarchy(team_id)


@api_view("GET", "POST")
@admin_required
def admin_team_members_collection(request, team_id):
    controller = TeamAdminController(request)
    if request.method == "POST":
        return controller.add_member(team_id)
    return controller.list_members(team_id)


@api_view("DELETE")
@admin_required
def admin_team_member_detail(request, team_id, user_id):
    return TeamAdminController(request).remove_member(team_id, user_id)


@api_view("POST")
@admin_required
def admin_team_members_move(request):
    return TeamAdminController(request).move_member()


@api_view("PATCH")
@admin_required
def admin_team_member_hierarchy(request, team_id, user_id):
    return TeamAdminController(request).assign_hierarchy(team_id, user_id)
