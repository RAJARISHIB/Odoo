"""Claims, Fines, and Employee Requests views - thin wrappers around controllers."""
from apps.claims.controllers import EmployeeRequestsController, ExpenseClaimsController, FinesController
from core.decorators import admin_required, api_view, auth_required


# ---------------------------------------------------------------------------
# Employee Views
# ---------------------------------------------------------------------------
@api_view("GET", "POST")
@auth_required
def claims_collection(request):
    controller = ExpenseClaimsController(request)
    if request.method == "POST":
        return controller.create()
    return controller.list()


@api_view("GET")
@auth_required
def claim_attachment_download(request, claim_id):
    return ExpenseClaimsController(request).download_attachment(claim_id)


@api_view("GET")
@auth_required
def fines_collection(request):
    return FinesController(request).list()


@api_view("GET", "POST")
@auth_required
def requests_collection(request):
    controller = EmployeeRequestsController(request)
    if request.method == "POST":
        return controller.create()
    return controller.list()


@api_view("GET")
@auth_required
def request_attachment_download(request, request_id):
    return EmployeeRequestsController(request).download_attachment(request_id)


# ---------------------------------------------------------------------------
# Admin Views
# ---------------------------------------------------------------------------
@api_view("GET")
@admin_required
def admin_claims_collection(request):
    return ExpenseClaimsController(request).admin_list()


@api_view("POST")
@admin_required
def admin_claim_approve(request, claim_id):
    return ExpenseClaimsController(request).approve(claim_id)


@api_view("POST")
@admin_required
def admin_claim_reject(request, claim_id):
    return ExpenseClaimsController(request).reject(claim_id)


@api_view("GET", "POST")
@admin_required
def admin_fines_collection(request):
    controller = FinesController(request)
    if request.method == "POST":
        return controller.create()
    return controller.admin_list()


@api_view("PATCH")
@admin_required
def admin_fine_detail(request, fine_id):
    return FinesController(request).update(fine_id)


@api_view("GET")
@admin_required
def admin_requests_collection(request):
    return EmployeeRequestsController(request).admin_list()


@api_view("POST")
@admin_required
def admin_request_approve(request, request_id):
    return EmployeeRequestsController(request).approve(request_id)


@api_view("POST")
@admin_required
def admin_request_reject(request, request_id):
    return EmployeeRequestsController(request).reject(request_id)
