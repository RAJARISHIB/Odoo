"""Users + auth views.

Deliberately thin: declare the method and access rule, hand the request to a
controller.  Anything longer than one line belongs in `controllers.py`.
"""
from apps.users.controllers import AuthController, ProfileController, UserController, RoleController
from core.decorators import admin_required, api_view, auth_required, permissions_required
from core.constants import Permissions


# ---------------------------------------------------------------------------
# Auth (public)
# ---------------------------------------------------------------------------
@api_view("POST")
def register(request):
    return AuthController(request).register()


@api_view("POST")
def login(request):
    return AuthController(request).login()


@api_view("POST")
def refresh(request):
    return AuthController(request).refresh()


# ---------------------------------------------------------------------------
# Auth (authenticated)
# ---------------------------------------------------------------------------
@api_view("POST")
def logout(request):
    # No @auth_required: signing out with an expired access token must still work.
    return AuthController(request).logout()


@api_view("GET")
@auth_required
def me(request):
    return AuthController(request).me()


@api_view("GET")
@auth_required
def sessions(request):
    return AuthController(request).sessions()


@api_view("POST")
@auth_required
def change_password(request):
    return AuthController(request).change_password()


# ---------------------------------------------------------------------------
# Profile (self-service)
# ---------------------------------------------------------------------------
@api_view("GET", "PATCH", "PUT")
@auth_required
def profile(request):
    controller = ProfileController(request)
    if request.method == "GET":
        return controller.retrieve()
    return controller.update()


# ---------------------------------------------------------------------------
# Employee directory (admin panel)
# ---------------------------------------------------------------------------
@api_view("GET", "POST")
@auth_required
def user_collection(request):
    controller = UserController(request)
    return controller.list() if request.method == "GET" else controller.create()


@api_view("GET", "PATCH", "PUT", "DELETE")
@auth_required
def user_detail(request, user_id):
    controller = UserController(request)
    if request.method == "GET":
        return controller.retrieve(user_id)
    if request.method == "DELETE":
        return controller.destroy(user_id)
    return controller.update(user_id)


@api_view("POST")
@auth_required
def user_reset_password(request, user_id):
    return UserController(request).reset_password(user_id)


@api_view("GET")
@permissions_required(Permissions.USERS_VIEW)
def user_stats(request):
    return UserController(request).stats()


# ---------------------------------------------------------------------------
# Roles & Permissions
# ---------------------------------------------------------------------------
@api_view("GET")
@permissions_required(Permissions.ROLES_VIEW)
def permissions_catalog(request):
    return RoleController(request).catalog()


@api_view("GET", "POST")
def role_collection(request):
    controller = RoleController(request)
    if request.method == "GET":
        # Using manual decorator call to allow either roles.view or roles.manage
        return permissions_required(Permissions.ROLES_VIEW)(controller.list)(request)
    return permissions_required(Permissions.ROLES_MANAGE)(controller.create)(request)


@api_view("GET", "PATCH", "PUT", "DELETE")
def role_detail(request, role_id):
    controller = RoleController(request)
    if request.method == "GET":
        return permissions_required(Permissions.ROLES_VIEW)(controller.retrieve)(request, role_id)
    if request.method == "DELETE":
        return permissions_required(Permissions.ROLES_MANAGE)(controller.destroy)(request, role_id)
    return permissions_required(Permissions.ROLES_MANAGE)(controller.update)(request, role_id)


@api_view("POST")
@permissions_required(Permissions.ROLES_ASSIGN)
def role_assign(request, role_id):
    return RoleController(request).assign(role_id)
