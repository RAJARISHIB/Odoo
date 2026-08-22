"""Seed a demo organization so the UI has something to show immediately.

    python manage.py seed_demo
    python manage.py seed_demo --reset     # wipe the demo org first

Creates one organization, two departments, one admin, one HR, three employees
and a fortnight of attendance history.
"""
import random
from datetime import date, datetime, time, timedelta, timezone

from django.core.management.base import BaseCommand

from apps.attendance.models import Attendance, WorkSession
from apps.leaves.models import Holiday, LeaveRequest
from apps.organization.models import Department, Organization
from apps.teams.models import Team, TeamHierarchyLevel, TeamMember
from apps.users.models import RefreshToken, User, Role
from core.constants import AttendanceSource, AttendanceStatus, Role as RoleEnum, UserStatus, Permissions
from core.identifiers import generate_login_id, organization_code

DEMO_SLUG = "acme-corp"
DEMO_PASSWORD = "Password123"

DEMO_PEOPLE = [
    ("admin@acme.test", "Aisha", "Kapoor", RoleEnum.ADMIN, "Engineering", "Head of Engineering"),
    ("hr@acme.test", "Rahul", "Menon", RoleEnum.HR, "People Ops", "HR Manager"),
    ("manager@acme.test", "Sara", "Iyer", RoleEnum.MANAGER, "Engineering", "Engineering Manager"),
    ("dev@acme.test", "Vikram", "Rao", RoleEnum.EMPLOYEE, "Engineering", "Software Engineer"),
    ("designer@acme.test", "Neha", "Shah", RoleEnum.EMPLOYEE, "Engineering", "Product Designer"),
]


class Command(BaseCommand):
    help = "Seed a demo HRMS organization with users and attendance history."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete the demo org first.")
        parser.add_argument("--days", type=int, default=14, help="Days of attendance history.")

    def handle(self, *args, **options):
        if options["reset"]:
            self._reset()

        organization = self._organization()
        
        # Provision default roles for the organization
        roles = {}
        for r_slug, r_name, perms in [
            (RoleEnum.SUPER_ADMIN, "Super Admin", list(Permissions.ALL)),
            (RoleEnum.ADMIN, "Admin", list(Permissions.ALL)),
            (RoleEnum.HR, "HR Manager", [p for p in Permissions.ALL if p.startswith('users.') or p.startswith('leaves.') or p in (Permissions.ATTENDANCE_VIEW_ALL, Permissions.ATTENDANCE_MANAGE, Permissions.ORG_VIEW, Permissions.DEPARTMENTS_MANAGE, Permissions.ROLES_VIEW, Permissions.ROLES_ASSIGN)]),
            (RoleEnum.MANAGER, "Manager", [Permissions.USERS_VIEW, Permissions.ATTENDANCE_PUNCH, Permissions.ATTENDANCE_VIEW_OWN, Permissions.ATTENDANCE_VIEW_TEAM, Permissions.LEAVES_APPLY, Permissions.LEAVES_VIEW_OWN, Permissions.LEAVES_VIEW_TEAM, Permissions.LEAVES_APPROVE, Permissions.ORG_VIEW]),
            (RoleEnum.EMPLOYEE, "Employee", [Permissions.USERS_VIEW, Permissions.ATTENDANCE_PUNCH, Permissions.ATTENDANCE_VIEW_OWN, Permissions.LEAVES_APPLY, Permissions.LEAVES_VIEW_OWN, Permissions.ORG_VIEW])
        ]:
            roles[r_slug] = Role.objects.filter(organization=organization, slug=r_slug).first()
            if not roles[r_slug]:
                roles[r_slug] = Role(organization=organization, name=r_name, slug=r_slug, is_system=True, permissions=perms).save()
            
        departments = self._departments(organization)
        owner = self._owner(organization, roles)
        users = self._users(organization, departments, roles)
        self._attendance(organization, [owner] + users, options["days"])
        self._holidays(organization)
        self._leaves(organization, users)
        self._teams(organization, users)

        self.stdout.write(self.style.SUCCESS("\nDemo data ready."))
        self.stdout.write("  Organization : {} ({}, code {})".format(
            organization.name, organization.slug, organization.code))
        self.stdout.write("  Password     : {}\n".format(DEMO_PASSWORD))
        self.stdout.write("  Sign in with either the login ID or the email:")
        self.stdout.write("    {:<16} {:<20} {:<12} {}".format("LOGIN ID", "EMAIL", "ROLE", "PANEL"))
        for user in [owner] + users:
            panel = "admin panel" if user.role.slug in RoleEnum.ADMIN_PANEL else "user panel"
            self.stdout.write("    {:<16} {:<20} {:<12} {}".format(
                user.login_id, user.email, user.role.slug, panel))

    # -- steps -------------------------------------------------------------
    def _reset(self):
        organization = Organization.objects.filter(slug=DEMO_SLUG).first()
        if not organization:
            return
        Attendance.objects.filter(organization=organization).delete()
        Holiday.objects.filter(organization=organization).delete()
        LeaveRequest.objects.filter(organization=organization).delete()
        TeamMember.objects.filter(organization=organization).delete()
        for t in Team.objects.filter(organization=organization):
            TeamHierarchyLevel.objects.filter(team=t).delete()
            t.delete()
        for user in User.objects.filter(organization=organization):
            RefreshToken.objects.filter(user=user).delete()
        User.objects.filter(organization=organization).delete()
        Department.objects.filter(organization=organization).delete()
        organization.delete()
        self.stdout.write(self.style.WARNING("Removed existing demo organization."))

    def _organization(self) -> Organization:
        organization = Organization.objects.filter(slug=DEMO_SLUG).first()
        if organization:
            self.stdout.write("Organization already present, reusing it.")
            return organization
        return Organization(
            name="Acme Corp",
            slug=DEMO_SLUG,
            code=organization_code("Acme Corp"),
            email="hello@acme.test",
            phone="+91 98000 00000",
            city="Bengaluru",
            state="Karnataka",
            timezone="Asia/Kolkata",
        ).save()

    def _departments(self, organization) -> dict:
        departments = {}
        for name, code in (("Engineering", "ENG"), ("People Ops", "HR")):
            department = Department.objects.filter(organization=organization, name=name).first()
            if not department:
                department = Department(organization=organization, name=name, code=code).save()
            departments[name] = department
        return departments

    def _owner(self, organization, roles) -> User:
        owner = User.objects.filter(email="owner@acme.test").first()
        if owner:
            return owner
        joined_at = datetime.now(timezone.utc) - timedelta(days=900)
        owner = User(
            organization=organization,
            login_id=generate_login_id(organization, "Owner", "Acme", joined_at),
            email="owner@acme.test",
            first_name="Owner",
            last_name="Acme",
            role=roles[RoleEnum.SUPER_ADMIN],
            status=UserStatus.ACTIVE,
            designation="Founder",
            employee_id="EMP001",
            date_of_joining=joined_at,
        )
        owner.set_password(DEMO_PASSWORD)
        return owner.save()

    def _users(self, organization, departments, roles) -> list:
        created = []
        for index, (email, first, last, role, department, designation) in enumerate(DEMO_PEOPLE, start=2):
            user = User.objects.filter(email=email).first()
            if not user:
                joined_at = datetime.now(timezone.utc) - timedelta(days=120 + index * 10)
                user = User(
                        organization=organization,
                        department=departments.get(department),
                        login_id=generate_login_id(organization, first, last, joined_at),
                        email=email,
                        first_name=first,
                        last_name=last,
                        role=roles.get(role, roles[RoleEnum.EMPLOYEE]),
                    status=UserStatus.ACTIVE,
                    designation=designation,
                    employee_id="EMP{:03d}".format(index),
                    date_of_joining=joined_at,
                )
                user.set_password(DEMO_PASSWORD)
                user.save()
            created.append(user)
        return created

    def _attendance(self, organization, users, days: int):
        today = datetime.now(timezone.utc).date()
        written = 0

        for user in users:
            for offset in range(days):
                day = today - timedelta(days=offset)
                if day.weekday() >= 5:  # weekend
                    continue

                key = datetime.combine(day, time.min, tzinfo=timezone.utc)
                if Attendance.objects.filter(organization=organization, user=user, date=key).first():
                    continue

                # A little variety so charts and filters have something to show.
                roll = random.random()
                if roll < 0.08:
                    Attendance(
                        organization=organization, user=user, date=key,
                        status=AttendanceStatus.ABSENT,
                    ).save()
                    written += 1
                    continue

                late = roll < 0.25
                start_hour, start_minute = (10, 25) if late else (9, random.randint(15, 29))
                check_in = datetime.combine(
                    day, time(start_hour, start_minute), tzinfo=timezone.utc
                ) - timedelta(hours=5, minutes=30)  # org-local 09:30 IST -> UTC
                check_out = check_in + timedelta(hours=random.uniform(7.0, 9.5))

                record = Attendance(
                    organization=organization,
                    user=user,
                    date=key,
                    status=AttendanceStatus.LATE if late else AttendanceStatus.PRESENT,
                    late_minutes=random.randint(16, 60) if late else 0,
                    sessions=[
                        WorkSession(
                            check_in=check_in,
                            check_out=check_out,
                            source=AttendanceSource.WEB,
                        )
                    ],
                )
                record.recalculate().save()
                written += 1

        self.stdout.write("Wrote {} attendance records.".format(written))

    def _holidays(self, organization):
        today = datetime.now(timezone.utc).date()
        year = today.year
        month = today.month

        sample_holidays = [
            ("Independence Day", datetime(year, 8, 15, tzinfo=timezone.utc), Holiday.TYPE_GOVERNMENT, "National Holiday"),
            ("Republic Day", datetime(year, 1, 26, tzinfo=timezone.utc), Holiday.TYPE_GOVERNMENT, "National Holiday"),
            ("Gandhi Jayanti", datetime(year, 10, 2, tzinfo=timezone.utc), Holiday.TYPE_GOVERNMENT, "National Holiday"),
            ("Company Foundation Day", datetime(year, month, 28, tzinfo=timezone.utc), Holiday.TYPE_ORGANIZATION, "Annual Company Celebration"),
        ]

        count = 0
        for name, dt, h_type, desc in sample_holidays:
            if not Holiday.objects.filter(organization=organization, name=name, date=dt).first():
                Holiday(
                    organization=organization,
                    name=name,
                    date=dt,
                    type=h_type,
                    description=desc,
                ).save()
                count += 1
        self.stdout.write("Seeded {} holidays.".format(count))

    def _leaves(self, organization, users):
        today = datetime.now(timezone.utc).date()
        dev_user = next((u for u in users if u.email == "dev@acme.test"), None)
        if not dev_user:
            return

        # Create one pending leave request for testing
        start_d = today + timedelta(days=5)
        end_d = today + timedelta(days=5)
        start_dt = datetime.combine(start_d, time.min, tzinfo=timezone.utc)
        end_dt = datetime.combine(end_d, time.max, tzinfo=timezone.utc)

        if not LeaveRequest.objects.filter(organization=organization, employee=dev_user, start_date=start_dt).first():
            LeaveRequest(
                organization=organization,
                employee=dev_user,
                start_date=start_dt,
                end_date=end_dt,
                reason="Personal work",
                status=LeaveRequest.STATUS_PENDING,
            ).save()
            self.stdout.write("Seeded sample leave request for dev@acme.test.")

    def _teams(self, organization, users):
        today = datetime.now(timezone.utc).date()

        # Set sample dates of birth
        dob_map = {
            "dev@acme.test": datetime.combine(date(1995, today.month, today.day), time.min, tzinfo=timezone.utc),
            "designer@acme.test": datetime.combine(date(1996, (today + timedelta(days=3)).month, (today + timedelta(days=3)).day), time.min, tzinfo=timezone.utc),
            "manager@acme.test": datetime.combine(date(1992, (today + timedelta(days=5)).month, (today + timedelta(days=5)).day), time.min, tzinfo=timezone.utc),
        }

        for u in users:
            if u.email in dob_map and not u.date_of_birth:
                u.date_of_birth = dob_map[u.email]
                u.save()

        # Seed Team
        team = Team.objects.filter(organization=organization, name="Core Engineering").first()
        if not team:
            team = Team(
                organization=organization,
                name="Core Engineering",
                description="Core product and software engineering team",
                status=Team.STATUS_ACTIVE,
            ).save()

        # Seed Hierarchy Levels
        hierarchy_levels = [
            ("Engineering Lead", 1),
            ("Senior Developer", 2),
            ("Developer", 3),
            ("Intern", 4),
        ]
        level_objs = {}
        for name, order in hierarchy_levels:
            lvl = TeamHierarchyLevel.objects.filter(team=team, name=name).first()
            if not lvl:
                lvl = TeamHierarchyLevel(
                    team=team,
                    name=name,
                    order=order,
                    is_active=True,
                ).save()
            level_objs[name] = lvl

        # Assign Members
        assignments = [
            ("manager@acme.test", "Engineering Lead"),
            ("dev@acme.test", "Developer"),
            ("designer@acme.test", "Developer"),
        ]
        for email, lvl_name in assignments:
            u = next((usr for usr in users if usr.email == email), None)
            if u and not TeamMember.objects.filter(team=team, employee=u, is_active=True).first():
                TeamMember(
                    organization=organization,
                    team=team,
                    employee=u,
                    hierarchy_level=level_objs.get(lvl_name),
                    is_active=True,
                ).save()

        self.stdout.write("Seeded team 'Core Engineering' with 4 hierarchy levels and 3 members.")


