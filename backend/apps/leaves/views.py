"""Leave views - thin wrappers around LeaveController."""
from apps.leaves.controllers import LeaveController
from core.decorators import api_view, auth_required


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

