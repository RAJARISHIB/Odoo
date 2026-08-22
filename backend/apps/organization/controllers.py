"""Organization + department controllers."""
from apps.organization import services
from core.base_controller import BaseController
from core.constants import RealtimeEvent, Role


class OrganizationController(BaseController):
    """The caller's own organization: /api/v1/organization"""

    def retrieve(self):
        user = self.require_user()
        organization = services.get_organization(user.organization.id)
        return self.ok(organization.to_dict())

    def update(self):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN)
        organization = services.get_organization(self.organization_id)
        organization = services.update_organization(organization, self.data)

        # Working-hours changes affect every open screen, so tell the whole org.
        self.emit_to_org(RealtimeEvent.ORG_UPDATED, {"organization": organization.to_dict()})
        return self.ok(organization.to_dict(), "Organization updated.")

    def upload_logo(self):
        """Replace the company logo.

        Multipart, field name `logo`.  The old file is deleted once the new one
        is safely stored - see `core.storage`.
        """
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN)
        organization = services.get_organization(self.organization_id)
        organization = services.set_logo(organization, self.file("logo", required=True))

        self.emit_to_org(RealtimeEvent.ORG_UPDATED, {"organization": organization.to_dict()})
        return self.ok(
            {"logo_url": organization.logo_url, "organization": organization.to_dict()},
            "Logo updated.",
        )

    def overview(self):
        """Small aggregate used by the admin dashboard header."""
        self.require_admin()
        organization = services.get_organization(self.organization_id)
        return self.ok(
            {
                "organization": organization.to_dict(),
                "departments": services.department_headcount(organization),
            }
        )


class DepartmentController(BaseController):
    """Departments within the caller's organization: /api/v1/departments/*"""

    def list(self):
        user = self.require_user()
        queryset = services.list_departments(
            user.organization,
            search=self.param("search"),
            active_only=self.param("active_only", "false").lower() == "true",
        )
        return self.paginated(queryset)

    def create(self):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR)
        department = services.create_department(self.user.organization, self.data)
        self.emit_to_admins(RealtimeEvent.ORG_UPDATED, {"department": department.to_dict()})
        return self.created(department.to_dict(), "Department created.")

    def retrieve(self, department_id):
        user = self.require_user()
        department = services.get_department(user.organization, department_id)
        return self.ok(department.to_dict())

    def update(self, department_id):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR)
        department = services.get_department(self.user.organization, department_id)
        department = services.update_department(self.user.organization, department, self.data)
        self.emit_to_admins(RealtimeEvent.ORG_UPDATED, {"department": department.to_dict()})
        return self.ok(department.to_dict(), "Department updated.")

    def destroy(self, department_id):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN)
        department = services.get_department(self.user.organization, department_id)
        department.soft_delete()
        self.emit_to_admins(RealtimeEvent.ORG_UPDATED, {"department_id": str(department.id)})
        return self.deleted("Department removed.")
