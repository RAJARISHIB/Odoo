"""Claims, Fines, and Employee Requests controllers."""
from django.http import FileResponse

from apps.claims import services
from core.base_controller import BaseController
from core.constants import Permissions


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
        return self.ok(claim.to_dict(), "Expense claim approved.")

    def reject(self, claim_id: str):
        self.require_permissions(Permissions.CLAIMS_MANAGE)
        claim = services.reject_claim(
            self.user.organization, claim_id, admin_user=self.user, comment=self.field("comment", "")
        )
        return self.ok(claim.to_dict(), "Expense claim rejected.")


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
        return self.created(fine.to_dict(), "Fine applied successfully.")

    def update(self, fine_id: str):
        self.require_permissions(Permissions.CLAIMS_MANAGE)
        status = self.field("status", "CANCELLED")
        fine = services.update_fine_status(self.user.organization, fine_id, status)
        return self.ok(fine.to_dict(), "Fine status updated.")


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
        return self.ok(req.to_dict(), "Employee request approved.")

    def reject(self, request_id: str):
        self.require_permissions(Permissions.CLAIMS_MANAGE)
        req = services.reject_request(
            self.user.organization,
            request_id,
            admin_user=self.user,
            rejection_reason=self.field("rejection_reason", ""),
        )
        return self.ok(req.to_dict(), "Employee request rejected.")
