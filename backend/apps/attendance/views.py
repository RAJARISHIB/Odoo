"""Attendance views - thin wrappers over the controllers."""
from apps.attendance.controllers import AttendanceAdminController, AttendanceController
from core.decorators import admin_required, api_view, auth_required, permissions_required
from core.constants import Permissions


# ---------------------------------------------------------------------------
# Employee (user panel)
# ---------------------------------------------------------------------------
@api_view("GET")
@auth_required
def attendance_status(request):
    return AttendanceController(request).status()


@api_view("POST")
@auth_required
def check_in(request):
    return AttendanceController(request).check_in()


@api_view("POST")
@auth_required
def check_out(request):
    return AttendanceController(request).check_out()


@api_view("GET")
@auth_required
def my_attendance(request):
    return AttendanceController(request).my_records()


@api_view("GET")
@auth_required
def my_summary(request):
    return AttendanceController(request).my_summary()


# ---------------------------------------------------------------------------
# Admin panel
# ---------------------------------------------------------------------------
@api_view("GET", "POST")
@admin_required
def admin_attendance_collection(request):
    controller = AttendanceAdminController(request)
    return controller.list() if request.method == "GET" else controller.manual_entry()


@api_view("GET", "DELETE")
@admin_required
def admin_attendance_detail(request, record_id):
    controller = AttendanceAdminController(request)
    if request.method == "DELETE":
        return controller.destroy(record_id)
    return controller.retrieve(record_id)


@api_view("GET")
@admin_required
def admin_attendance_overview(request):
    return AttendanceAdminController(request).overview()


@api_view("GET")
@admin_required
def admin_user_summary(request, user_id):
    return AttendanceAdminController(request).user_summary(user_id)
