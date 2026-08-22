"""Leave views - thin wrappers around LeaveController."""
from apps.leaves.controllers import (
    HolidayAdminController,
    LeaveAdjustmentController,
    LeaveAdminRequestController,
    LeaveAllocationController,
    LeaveController,
    LeaveDashboardController,
    LeaveTypeController,
)
from core.decorators import admin_required, api_view, auth_required


@api_view("GET")
@auth_required
def calendar(request):
    return LeaveController(request).calendar()


@api_view("GET")
@auth_required
def holidays(request):
    return LeaveController(request).holidays()


@api_view("GET")
@auth_required
def balance(request):
    return LeaveController(request).balance()


@api_view("GET", "POST")
@auth_required
def requests(request):
    controller = LeaveController(request)
    if request.method == "POST":
        return controller.create_request()
    return controller.my_requests()


@api_view("POST")
@auth_required
def cancel_request(request, request_id):
    return LeaveController(request).cancel_request(request_id)


# =============================================================================
# Admin leave module - additive.  Everything above is unchanged.
# =============================================================================
# -- shared (visible to any signed-in user; writes are role-checked inside) --
@api_view("GET", "POST")
@auth_required
def leave_type_collection(request):
    controller = LeaveTypeController(request)
    return controller.list() if request.method == "GET" else controller.create()


@api_view("PUT")
@auth_required
def leave_type_detail(request, type_id):
    return LeaveTypeController(request).update(type_id)


@api_view("POST")
@auth_required
def leave_type_activate(request, type_id):
    return LeaveTypeController(request).set_active(type_id, True)


@api_view("POST")
@auth_required
def leave_type_deactivate(request, type_id):
    return LeaveTypeController(request).set_active(type_id, False)


@api_view("POST")
@auth_required
def holiday_admin_collection(request):
    return HolidayAdminController(request).create()


@api_view("PUT")
@auth_required
def holiday_admin_detail(request, holiday_id):
    return HolidayAdminController(request).update(holiday_id)


# -- admin panel --------------------------------------------------------
@api_view("GET")
@admin_required
def admin_leave_request_collection(request):
    return LeaveAdminRequestController(request).list()


@api_view("GET")
@admin_required
def admin_leave_request_detail(request, request_id):
    return LeaveAdminRequestController(request).retrieve(request_id)


@api_view("POST")
@admin_required
def admin_leave_request_approve(request, request_id):
    return LeaveAdminRequestController(request).approve(request_id)


@api_view("POST")
@admin_required
def admin_leave_request_reject(request, request_id):
    return LeaveAdminRequestController(request).reject(request_id)


@api_view("GET", "POST")
@admin_required
def allocation_rule_collection(request):
    controller = LeaveAllocationController(request)
    return controller.list() if request.method == "GET" else controller.create()


@api_view("PUT")
@admin_required
def allocation_rule_detail(request, rule_id):
    return LeaveAllocationController(request).update(rule_id)


@api_view("POST")
@admin_required
def allocation_generate(request):
    return LeaveAllocationController(request).generate()


@api_view("GET", "POST")
@admin_required
def adjustment_collection(request):
    controller = LeaveAdjustmentController(request)
    return controller.list() if request.method == "GET" else controller.create()


@api_view("GET")
@admin_required
def admin_leave_balances(request):
    return LeaveDashboardController(request).admin_balances()


@api_view("GET")
@admin_required
def admin_leave_dashboard(request):
    return LeaveDashboardController(request).dashboard()


@api_view("GET")
@admin_required
def admin_leave_employee_summary(request, user_id):
    return LeaveDashboardController(request).employee_summary(user_id)

