import mimetypes

from django.http import FileResponse

from apps.payroll import services
from core.base_controller import BaseController
from core.constants import Role


class PayrollController(BaseController):
    """Controller handling /api/v1/payroll/* and /api/v1/admin/payroll/*"""

    # --- Employee Self-Service ---
    def my_payroll(self):
        user = self.require_user()
        payroll = services.get_employee_payroll(user.organization, user)
        return self.ok(payroll.to_dict())

    def my_documents(self):
        user = self.require_user()
        doc_type = self.param("document_type")
        queryset = services.list_employee_documents(user.organization, user, document_type=doc_type)
        return self.paginated(queryset)

    def download_document(self, document_id: str):
        user = self.require_user()
        file_path, filename = services.get_payroll_document_file(user.organization, user, document_id)
        content_type, _ = mimetypes.guess_type(filename)
        response = FileResponse(
            open(file_path, "rb"),
            as_attachment=True,
            filename=filename,
            content_type=content_type or "application/pdf",
        )
        return response

    # --- Admin Role Templates ---
    def list_templates(self):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR)
        queryset = services.list_role_templates(self.user.organization)
        return self.paginated(queryset)

    def get_template(self, template_id: str):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR)
        template = services.get_role_template(self.user.organization, template_id)
        return self.ok(template.to_dict())

    def upsert_template(self):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR)
        template = services.upsert_role_template(self.user.organization, self.data)
        return self.ok(template.to_dict(), "Role salary template saved successfully.")

    def preview_calculation(self):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR)
        res = services.preview_salary_calculation(self.data)
        return self.ok(res)

    # --- Admin Employee Payroll Assignments ---
    def list_employee_payrolls(self):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR)
        queryset = services.list_all_employee_payrolls(self.user.organization)
        return self.paginated(queryset)

    def get_employee_payroll_admin(self, user_id: str):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR)
        user = self.get_target_user(user_id)
        payroll = services.get_employee_payroll(self.user.organization, user)
        return self.ok(payroll.to_dict())

    def assign_employee_payroll(self):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR)
        payroll = services.assign_employee_payroll(self.user.organization, self.data)
        return self.ok(payroll.to_dict(), "Employee payroll saved successfully.")

    # --- Admin Payroll Documents ---
    def list_documents_admin(self):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR)
        queryset = services.list_admin_documents(
            self.user.organization,
            employee_id=self.param("employee_id"),
            document_type=self.param("document_type"),
        )
        return self.paginated(queryset)

    def upload_document_admin(self):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR)
        file_obj = self.file("file", required=True)
        doc = services.upload_payroll_document(
            self.user.organization, uploader=self.user, data=self.data, file_obj=file_obj
        )
        return self.created(doc.to_dict(), "Payroll document uploaded successfully.")

    def delete_document_admin(self, document_id: str):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR)
        services.delete_payroll_document(self.user.organization, document_id)
        return self.ok({}, "Payroll document deleted.")
