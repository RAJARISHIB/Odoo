"""Claims, Fines, and Employee Requests controllers."""
from django.http import FileResponse

from apps.claims import services
from core.base_controller import BaseController
from core.constants import Permissions, RealtimeEvent


class ExpenseClaimsController(BaseController):
    """Claims controller: /api/v1/claims/* and /api/v1/admin/claims/*"""

    def list(self):
        user = self.require_user()
        queryset = services.list_employee_claims(user.organization, user)
        return self.paginated(queryset)

    def create(self):
        user = self.require_user()
        receipt = self.file("receipt", required=False)
        claim = services.create_claim(user.organization, user, self.data, receipt_file=receipt)
        payload = {"claim": claim.to_dict(), "user": {"id": str(user.id), "name": user.full_name, "email": user.email}}
        self.emit_to_user(user.id, RealtimeEvent.CLAIM_CREATED, payload)
        self.notify_relevant(RealtimeEvent.CLAIM_CREATED, payload, subject_user=user)
        return self.created(claim.to_dict(), "Expense claim submitted successfully.")

    def download_attachment(self, claim_id: str):
        user = self.require_user()
        file_path, filename = services.get_claim_attachment(user.organization, user, claim_id)
        response = FileResponse(open(file_path, "rb"), as_attachment=True, filename=filename)
        return response

    # Admin actions
    def admin_list(self):
        self.require_permissions(Permissions.CLAIMS_VIEW_ALL)
        queryset = services.list_admin_claims(self.user.organization, status=self.param("status"))
        return self.paginated(queryset)

    def approve(self, claim_id: str):
        self.require_permissions(Permissions.CLAIMS_MANAGE)
        claim = services.approve_claim(
            self.user.organization, claim_id, admin_user=self.user, comment=self.field("comment", "")
        )
        self._announce_claim(claim)
        return self.ok(claim.to_dict(), "Expense claim approved.")

    def reject(self, claim_id: str):
        self.require_permissions(Permissions.CLAIMS_MANAGE)
        claim = services.reject_claim(
            self.user.organization, claim_id, admin_user=self.user, comment=self.field("comment", "")
        )
        self._announce_claim(claim)
        return self.ok(claim.to_dict(), "Expense claim rejected.")

    def _announce_claim(self, claim):
        payload = {
            "claim": claim.to_dict(),
            "user": {"id": str(claim.employee.id), "name": claim.employee.full_name, "email": claim.employee.email},
        }
        self.emit_to_user(claim.employee.id, RealtimeEvent.CLAIM_UPDATED, payload)
        self.notify_relevant(RealtimeEvent.CLAIM_UPDATED, payload, subject_user=claim.employee)


class FinesController(BaseController):
    """Fines controller: /api/v1/fines/* and /api/v1/admin/fines/*"""

    def list(self):
        user = self.require_user()
        queryset = services.list_employee_fines(user.organization, user)
        return self.paginated(queryset)

    # Admin actions
    def admin_list(self):
        self.require_permissions(Permissions.CLAIMS_VIEW_ALL)
        queryset = services.list_admin_fines(self.user.organization, employee_id=self.param("employee_id"))
        return self.paginated(queryset)

    def create(self):
        self.require_permissions(Permissions.CLAIMS_MANAGE)
        fine = services.create_fine(self.user.organization, admin_user=self.user, data=self.data)
        self._announce_fine(fine, RealtimeEvent.FINE_CREATED)
        return self.created(fine.to_dict(), "Fine applied successfully.")

    def update(self, fine_id: str):
        self.require_permissions(Permissions.CLAIMS_MANAGE)
        status = self.field("status", "CANCELLED")
        fine = services.update_fine_status(self.user.organization, fine_id, status)
        self._announce_fine(fine, RealtimeEvent.FINE_UPDATED)
        return self.ok(fine.to_dict(), "Fine status updated.")

    def _announce_fine(self, fine, event: str):
        payload = {
            "fine": fine.to_dict(),
            "user": {"id": str(fine.employee.id), "name": fine.employee.full_name, "email": fine.employee.email},
        }
        self.emit_to_user(fine.employee.id, event, payload)
        self.notify_relevant(event, payload, subject_user=fine.employee)


class EmployeeRequestsController(BaseController):
    """Requests controller: /api/v1/requests/* and /api/v1/admin/requests/*"""

    def list(self):
        user = self.require_user()
        queryset = services.list_employee_requests(user.organization, user)
        return self.paginated(queryset)

    def create(self):
        user = self.require_user()
        attachment = self.file("attachment", required=False)
        req = services.create_request(user.organization, user, self.data, attachment_file=attachment)
        payload = {"request": req.to_dict(), "user": {"id": str(user.id), "name": user.full_name, "email": user.email}}
        self.emit_to_user(user.id, RealtimeEvent.REQUEST_CREATED, payload)
        self.notify_relevant(RealtimeEvent.REQUEST_CREATED, payload, subject_user=user)
        return self.created(req.to_dict(), "Employee request submitted successfully.")

    def download_attachment(self, request_id: str):
        user = self.require_user()
        file_path, filename = services.get_request_attachment(user.organization, user, request_id)
        response = FileResponse(open(file_path, "rb"), as_attachment=True, filename=filename)
        return response

    # Admin actions
    def admin_list(self):
        self.require_permissions(Permissions.CLAIMS_VIEW_ALL)
        queryset = services.list_admin_requests(
            self.user.organization,
            status=self.param("status"),
            request_type=self.param("request_type"),
        )
        return self.paginated(queryset)

    def approve(self, request_id: str):
        self.require_permissions(Permissions.CLAIMS_MANAGE)
        req = services.approve_request(self.user.organization, request_id, admin_user=self.user)
        self._announce_request(req)
        return self.ok(req.to_dict(), "Employee request approved.")

    def reject(self, request_id: str):
        self.require_permissions(Permissions.CLAIMS_MANAGE)
        req = services.reject_request(
            self.user.organization,
            request_id,
            admin_user=self.user,
            rejection_reason=self.field("rejection_reason", ""),
        )
        self._announce_request(req)
        return self.ok(req.to_dict(), "Employee request rejected.")

    def _announce_request(self, req):
        payload = {
            "request": req.to_dict(),
            "user": {"id": str(req.employee.id), "name": req.employee.full_name, "email": req.employee.email},
        }
        self.emit_to_user(req.employee.id, RealtimeEvent.REQUEST_UPDATED, payload)
        self.notify_relevant(RealtimeEvent.REQUEST_UPDATED, payload, subject_user=req.employee)
