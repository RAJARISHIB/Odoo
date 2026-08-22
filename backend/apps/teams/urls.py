"""Teams routes, split into employee and admin surfaces."""
from django.urls import path

from apps.teams import views

urlpatterns = [
    path("teams/my-team", views.my_team, name="teams-my-team"),
    path("teams/availability", views.availability, name="teams-availability"),
    path("teams/birthdays", views.birthdays, name="teams-birthdays"),
]

admin_urlpatterns = [
    path("teams", views.admin_teams_collection, name="admin-teams-collection"),
    path("teams/members/move", views.admin_team_members_move, name="admin-teams-members-move"),
    path("teams/<str:team_id>", views.admin_team_detail, name="admin-teams-detail"),
    path("teams/<str:team_id>/hierarchy", views.admin_team_hierarchy_collection, name="admin-teams-hierarchy-collection"),
    path("teams/<str:team_id>/hierarchy/reorder", views.admin_team_hierarchy_reorder, name="admin-teams-hierarchy-reorder"),
    path("teams/<str:team_id>/hierarchy/<str:level_id>", views.admin_team_hierarchy_detail, name="admin-teams-hierarchy-detail"),
    path("teams/<str:team_id>/members", views.admin_team_members_collection, name="admin-teams-members-collection"),
    path("teams/<str:team_id>/members/<str:user_id>", views.admin_team_member_detail, name="admin-teams-member-detail"),
    path("teams/<str:team_id>/members/<str:user_id>/hierarchy", views.admin_team_member_hierarchy, name="admin-teams-member-hierarchy"),
]
