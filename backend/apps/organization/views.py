"""Organization + department views - thin wrappers over the controllers."""
from apps.organization.controllers import DepartmentController, OrganizationController
from core.decorators import admin_required, api_view, auth_required


@api_view("GET", "PATCH", "PUT")
@auth_required
def organization(request):
    controller = OrganizationController(request)
    if request.method == "GET":
        return controller.retrieve()
    return controller.update()


@api_view("POST")
@admin_required
def organization_logo(request):
    return OrganizationController(request).upload_logo()


@api_view("GET")
@admin_required
def organization_overview(request):
    return OrganizationController(request).overview()


@api_view("GET", "POST")
@auth_required
def department_collection(request):
    controller = DepartmentController(request)
    return controller.list() if request.method == "GET" else controller.create()


@api_view("GET", "PATCH", "PUT", "DELETE")
@auth_required
def department_detail(request, department_id):
    controller = DepartmentController(request)
    if request.method == "GET":
        return controller.retrieve(department_id)
    if request.method == "DELETE":
        return controller.destroy(department_id)
    return controller.update(department_id)
