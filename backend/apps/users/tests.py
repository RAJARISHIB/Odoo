"""Security test suite for authentication, RBAC, MFA and session handling.

Run against a disposable database only:

    MONGO_DB_NAME=hrms_test ./  .venv/Scripts/python.exe manage.py test apps.users

`setUpClass` refuses to run unless `MONGO_DB_NAME` looks like a test database
(ends with "_test") - these tests create and delete real documents and must
never run against a database holding real data.
"""
from django.conf import settings

from apps.organization.models import Organization
from apps.users import services
from apps.users.models import RefreshToken, Role, User
from core.constants import Permissions, Role as RoleEnum, UserStatus
from core.testing import ApiTestCase


def _require_test_database():
    db_name = settings.MONGO["DB_NAME"]
    if not db_name.endswith("_test"):
        raise RuntimeError(
            "Refusing to run apps.users.tests against MONGO_DB_NAME={!r} - it does not "
            "look like a disposable test database (expected a name ending in '_test'). "
            "Run with MONGO_DB_NAME=hrms_test instead.".format(db_name)
        )


class SecurityTestCase(ApiTestCase):
    """Common fixtures: an organization plus one user per role."""

    @classmethod
    def setUpClass(cls):
        _require_test_database()
        super().setUpClass()

    def setUp(self):
        super().setUp()
        # Go through the real bootstrap flow rather than hand-building an
        # Organization, so the five system roles are seeded exactly the way
        # they are in production (see `services.register_organization`) -
        # a hand-rolled fixture would silently drift from that as the real
        # seeding logic evolves.
        result = services.register_organization({
            "organization_name": "Test Co " + self._unique(""),
            "email": "org-{}@example.com".format(self._unique("")),
            "name": "Root Super",
            "password": "Password123",
        })
        self.organization = Organization.objects.get(id=result["organization"]["id"])
        self.super_admin = User.objects.get(id=result["user"]["id"])

        self.employee = self._make_user(RoleEnum.EMPLOYEE, "employee")
        self.other_employee = self._make_user(RoleEnum.EMPLOYEE, "other")
        self.hr = self._make_user(RoleEnum.HR, "hr")
        self.admin = self._make_user(RoleEnum.ADMIN, "admin")

    def tearDown(self):
        RefreshToken.objects.filter(user__in=[
            self.employee, self.other_employee, self.hr, self.admin, self.super_admin,
        ]).delete()
        User.objects.filter(organization=self.organization).delete()
        Role.objects.filter(organization=self.organization).delete()
        self.organization.delete()
        super().tearDown()

    _counter = 0

    @classmethod
    def _unique(cls, prefix: str) -> str:
        cls._counter += 1
        return "{}{}".format(prefix, cls._counter)

    def _role(self, role_slug: str) -> Role:
        return Role.objects.filter(organization=self.organization, slug=role_slug).first()

    def _role_id(self, role_slug: str) -> str:
        return str(self._role(role_slug).id)

    def _make_user(self, role_slug: str, tag: str, *, password: str = "Password123") -> User:
        user = User(
            organization=self.organization,
            login_id=self._unique("LID{}".format(tag)).upper()[:32],
            email="{}-{}@example.com".format(tag, self._unique("")),
            first_name=tag.capitalize(),
            role=self._role(role_slug),
            status=UserStatus.ACTIVE,
            email_verified=True,
        )
        user.set_password(password)
        user.save()
        return user

    def _login(self, user: User, password: str = "Password123") -> dict:
        response = self.post_json("/api/v1/auth/login", {"identifier": user.email, "password": password})
        self.assertEqual(response.status_code, 200, self.body(response))
        return self.body(response)["data"]

    def _access_token(self, user: User, password: str = "Password123") -> str:
        return self._login(user, password)["tokens"]["access_token"]

    def _enroll_mfa(self, user: User) -> str:
        """Enrolls `user` in MFA and returns the confirmed secret.  Sets
        `self.recovery_codes` to the one-time codes issued at confirmation."""
        token = self._access_token(user)
        start = self.post_json("/api/v1/security/mfa/enroll/start", **self.auth_header(token))
        self.assertEqual(start.status_code, 200)
        secret = self.body(start)["data"]["secret"]

        confirm = self.post_json(
            "/api/v1/security/mfa/enroll/confirm",
            {"code": self._totp_now(secret)},
            **self.auth_header(token),
        )
        self.assertEqual(confirm.status_code, 200)
        self.recovery_codes = self.body(confirm)["data"]["recovery_codes"]
        return secret

    @staticmethod
    def _totp_now(secret: str) -> str:
        # Computes a code the same way core.security does internally, so
        # this is a genuine round-trip through the real TOTP algorithm, not
        # a mocked shortcut.
        import time as time_module

        from core.security import _hotp

        return _hotp(secret, int(time_module.time()) // 30)


class AuthenticationTests(SecurityTestCase):
    def test_valid_login_succeeds(self):
        data = self._login(self.employee)
        self.assertFalse(data["mfa_required"])
        self.assertIn("access_token", data["tokens"])
        self.assertEqual(data["user"]["email"], self.employee.email)

    def test_invalid_password_rejected(self):
        response = self.post_json(
            "/api/v1/auth/login", {"identifier": self.employee.email, "password": "wrong-password"}
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.body(response)["error"]["code"], "invalid_credentials")

    def test_unknown_and_wrong_password_give_identical_error(self):
        """Anti-enumeration: the login endpoint must not reveal whether the
        account exists."""
        unknown = self.post_json(
            "/api/v1/auth/login", {"identifier": "nobody@example.com", "password": "whatever123"}
        )
        wrong = self.post_json(
            "/api/v1/auth/login", {"identifier": self.employee.email, "password": "wrong-password"}
        )
        self.assertEqual(self.body(unknown)["error"], self.body(wrong)["error"])

    def test_account_locks_after_repeated_failures(self):
        for _ in range(5):
            self.post_json(
                "/api/v1/auth/login", {"identifier": self.employee.email, "password": "wrong-password"}
            )
        response = self.post_json(
            "/api/v1/auth/login", {"identifier": self.employee.email, "password": "Password123"}
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.body(response)["error"]["code"], "account_locked")

    def test_logout_invalidates_the_refresh_token(self):
        data = self._login(self.employee)
        refresh_token = data["tokens"]["refresh_token"]

        logout_response = self.post_json("/api/v1/auth/logout", {"refresh_token": refresh_token})
        self.assertEqual(logout_response.status_code, 200)

        refreshed = self.post_json("/api/v1/auth/refresh", {"refresh_token": refresh_token})
        self.assertEqual(refreshed.status_code, 401)
        self.assertEqual(self.body(refreshed)["error"]["code"], "refresh_revoked")

    def test_password_change_invalidates_other_sessions(self):
        session_a = self._login(self.employee)
        session_b = self._login(self.employee)

        self.post_json(
            "/api/v1/auth/change-password",
            {"current_password": "Password123", "new_password": "NewPassword456"},
            **self.auth_header(session_a["tokens"]["access_token"]),
        )

        # Both refresh tokens (from before and after the change) must now be dead.
        for session in (session_a, session_b):
            refreshed = self.post_json(
                "/api/v1/auth/refresh", {"refresh_token": session["tokens"]["refresh_token"]}
            )
            self.assertEqual(refreshed.status_code, 401)

    def test_disabled_account_cannot_use_an_existing_session(self):
        data = self._login(self.employee)
        access_token = data["tokens"]["access_token"]

        self.employee.status = UserStatus.SUSPENDED
        self.employee.save()

        response = self.get_json("/api/v1/auth/me", **self.auth_header(access_token))
        self.assertEqual(response.status_code, 401)


class ObjectLevelAuthorizationTests(SecurityTestCase):
    def test_employee_cannot_read_another_employees_record(self):
        token = self._access_token(self.employee)
        response = self.get_json(
            "/api/v1/users/{}".format(self.other_employee.id), **self.auth_header(token)
        )
        self.assertEqual(response.status_code, 403)

    def test_employee_can_read_their_own_record(self):
        token = self._access_token(self.employee)
        response = self.get_json(
            "/api/v1/users/{}".format(self.employee.id), **self.auth_header(token)
        )
        self.assertEqual(response.status_code, 200)

    def test_employee_cannot_reach_admin_only_endpoint(self):
        token = self._access_token(self.employee)
        response = self.get_json("/api/v1/users/stats", **self.auth_header(token))
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_request_is_rejected(self):
        response = self.get_json("/api/v1/users/stats")
        self.assertEqual(response.status_code, 401)

    def test_employee_cannot_delete_a_user(self):
        token = self._access_token(self.employee)
        response = self.delete_json(
            "/api/v1/users/{}".format(self.other_employee.id), **self.auth_header(token)
        )
        self.assertEqual(response.status_code, 403)


class PrivilegeEscalationTests(SecurityTestCase):
    def test_hr_cannot_create_a_super_admin(self):
        token = self._access_token(self.hr)
        response = self.post_json(
            "/api/v1/users",
            {"email": "new-super@example.com", "name": "New Super", "role": RoleEnum.SUPER_ADMIN},
            **self.auth_header(token),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.body(response)["error"]["code"], "role_assignment_denied")

    def test_hr_can_create_an_employee(self):
        token = self._access_token(self.hr)
        response = self.post_json(
            "/api/v1/users",
            {"email": "new-employee@example.com", "name": "New Employee", "role": RoleEnum.EMPLOYEE},
            **self.auth_header(token),
        )
        self.assertEqual(response.status_code, 201)

    def test_admin_cannot_promote_another_admin_to_super_admin(self):
        token = self._access_token(self.admin)
        second_admin = self._make_user(RoleEnum.ADMIN, "second_admin")
        response = self.patch_json(
            "/api/v1/users/{}".format(second_admin.id),
            {"role": self._role_id(RoleEnum.SUPER_ADMIN)},
            **self.auth_header(token),
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_cannot_change_their_own_role(self):
        token = self._access_token(self.admin)
        response = self.patch_json(
            "/api/v1/users/{}".format(self.admin.id),
            {"role": self._role_id(RoleEnum.EMPLOYEE)},
            **self.auth_header(token),
        )
        self.assertEqual(response.status_code, 422)


class MfaTests(SecurityTestCase):
    def test_login_with_mfa_enabled_requires_second_step(self):
        secret = self._enroll_mfa(self.employee)

        first_step = self.post_json(
            "/api/v1/auth/login", {"identifier": self.employee.email, "password": "Password123"}
        )
        data = self.body(first_step)["data"]
        self.assertTrue(data["mfa_required"])
        self.assertNotIn("tokens", data)

        second_step = self.post_json(
            "/api/v1/auth/mfa/verify",
            {"mfa_pending_token": data["mfa_pending_token"], "code": self._totp_now(secret)},
        )
        self.assertEqual(second_step.status_code, 200)
        self.assertIn("access_token", self.body(second_step)["data"]["tokens"])

    def test_wrong_mfa_code_is_rejected(self):
        self._enroll_mfa(self.employee)
        first_step = self.post_json(
            "/api/v1/auth/login", {"identifier": self.employee.email, "password": "Password123"}
        )
        pending_token = self.body(first_step)["data"]["mfa_pending_token"]

        second_step = self.post_json(
            "/api/v1/auth/mfa/verify", {"mfa_pending_token": pending_token, "code": "000000"}
        )
        self.assertEqual(second_step.status_code, 401)
        self.assertEqual(self.body(second_step)["error"]["code"], "invalid_mfa_code")

    def test_recovery_code_logs_in_once_then_is_rejected(self):
        self._enroll_mfa(self.employee)
        recovery_code = self.recovery_codes[0]

        first_step = self.post_json(
            "/api/v1/auth/login", {"identifier": self.employee.email, "password": "Password123"}
        )
        pending_token = self.body(first_step)["data"]["mfa_pending_token"]

        used_once = self.post_json(
            "/api/v1/auth/mfa/verify", {"mfa_pending_token": pending_token, "code": recovery_code}
        )
        self.assertEqual(used_once.status_code, 200)

        # The same recovery code cannot be used a second time.
        first_step_again = self.post_json(
            "/api/v1/auth/login", {"identifier": self.employee.email, "password": "Password123"}
        )
        pending_token_2 = self.body(first_step_again)["data"]["mfa_pending_token"]
        used_twice = self.post_json(
            "/api/v1/auth/mfa/verify", {"mfa_pending_token": pending_token_2, "code": recovery_code}
        )
        self.assertEqual(used_twice.status_code, 401)

    def test_password_alone_does_not_yield_a_session_when_mfa_is_enabled(self):
        self._enroll_mfa(self.employee)
        response = self.post_json(
            "/api/v1/auth/login", {"identifier": self.employee.email, "password": "Password123"}
        )
        data = self.body(response)["data"]
        self.assertNotIn("tokens", data)
        self.assertNotIn("user", data)


class AuditLogAndPermissionTests(SecurityTestCase):
    def test_audit_log_requires_permission_and_mfa(self):
        # Admin has audit.view by default but has not enabled MFA yet.
        token = self._access_token(self.admin)
        response = self.get_json("/api/v1/admin/audit-logs", **self.auth_header(token))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.body(response)["error"]["code"], "mfa_setup_required")

    def test_employee_cannot_view_audit_logs(self):
        token = self._access_token(self.employee)
        response = self.get_json("/api/v1/admin/audit-logs", **self.auth_header(token))
        self.assertEqual(response.status_code, 403)

    def test_role_permissions_are_configurable_per_organization(self):
        # roles.manage is MFA-required (see core.permissions.MFA_REQUIRED_PERMISSIONS),
        # and that applies to super_admin too - "highly privileged" means it.
        self._enroll_mfa(self.super_admin)
        token = self._access_token(self.super_admin)
        employee_role_id = self._role_id(RoleEnum.EMPLOYEE)

        response = self.get_json(
            "/api/v1/auth/roles/{}".format(employee_role_id), **self.auth_header(token)
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(Permissions.LEAVES_APPLY, self.body(response)["data"]["permissions"])

        updated = self.put_json(
            "/api/v1/auth/roles/{}".format(employee_role_id),
            {"permissions": [Permissions.LEAVES_VIEW_OWN]},
            **self.auth_header(token),
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(
            Role.objects.get(id=employee_role_id).permissions,
            [Permissions.LEAVES_VIEW_OWN],
        )

    def test_employee_cannot_edit_role_permissions(self):
        token = self._access_token(self.employee)
        response = self.put_json(
            "/api/v1/auth/roles/{}".format(self._role_id(RoleEnum.EMPLOYEE)),
            {"permissions": []},
            **self.auth_header(token),
        )
        self.assertEqual(response.status_code, 403)


class InputValidationTests(SecurityTestCase):
    def test_search_with_regex_metacharacters_is_treated_as_a_literal(self):
        """A `$regex`-shaped or wildcard-heavy search term must not widen the
        match beyond an actual substring - see the `re.escape` fix in
        `apps.users.services.search_users`."""
        token = self._access_token(self.admin)
        response = self.get_json(
            "/api/v1/users", {"search": ".*"}, **self.auth_header(token)
        )
        self.assertEqual(response.status_code, 200)
        emails = [item["email"] for item in self.body(response)["data"]]
        # ".*" as a literal substring matches nobody's real email address.
        self.assertEqual(emails, [])

    def test_malformed_object_id_is_a_validation_error_not_a_500(self):
        token = self._access_token(self.admin)
        response = self.get_json("/api/v1/users/not-a-valid-id", **self.auth_header(token))
        self.assertIn(response.status_code, (400, 404, 422))
        self.assertLess(response.status_code, 500)

    def test_malformed_json_body_is_rejected_cleanly(self):
        response = self.client.post(
            "/api/v1/auth/login", data="{not json", content_type="application/json"
        )
        self.assertEqual(response.status_code, 422)
