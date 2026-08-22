"""Payroll views - thin wrappers routing HTTP calls to PayrollController."""
from apps.payroll.controllers import PayrollController
from core.decorators import admin_required, api_view, auth_required


# ---------------------------------------------------------------------------
# Employee Views
# ---------------------------------------------------------------------------
@api_view("GET")
@auth_required
def my_payroll(request):
    return PayrollController(request).my_payroll()


@api_view("GET")
@auth_required
def my_payroll_documents(request):
    return PayrollController(request).my_documents()


@api_view("GET")
@auth_required
def download_payroll_document(request, document_id):
    return PayrollController(request).download_document(document_id)


# ---------------------------------------------------------------------------
# Admin Views
# ---------------------------------------------------------------------------
@api_view("GET", "POST")
@admin_required
def admin_role_templates(request):
    controller = PayrollController(request)
    if request.method == "POST":
        return controller.upsert_template()
    return controller.list_templates()


@api_view("GET")
@admin_required
def admin_role_template_detail(request, template_id):
    return PayrollController(request).get_template(template_id)


@api_view("POST")
@admin_required
def admin_preview_calculation(request):
    return PayrollController(request).preview_calculation()


@api_view("GET", "POST")
@admin_required
def admin_employee_payrolls(request):
    controller = PayrollController(request)
    if request.method == "POST":
        return controller.assign_employee_payroll()
    return controller.list_employee_payrolls()


@api_view("GET")
@admin_required
def admin_employee_payroll_detail(request, user_id):
    return PayrollController(request).get_employee_payroll_admin(user_id)


@api_view("GET", "POST")
@admin_required
def admin_payroll_documents(request):
    controller = PayrollController(request)
    if request.method == "POST":
        return controller.upload_document_admin()
    return controller.list_documents_admin()


@api_view("DELETE")
@admin_required
def admin_payroll_document_detail(request, document_id):
    return PayrollController(request).delete_document_admin(document_id)
