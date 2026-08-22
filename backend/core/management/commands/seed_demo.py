"""Seed a demo organization so the UI has something to show immediately.

    python manage.py seed_demo
    python manage.py seed_demo --reset     # wipe the demo org first

Creates one organization, two departments, one admin, one HR, three employees
and a fortnight of attendance history.
"""
import random
from datetime import datetime, time, timedelta, timezone

from django.core.management.base import BaseCommand

from apps.attendance.models import Attendance, WorkSession
from apps.organization.models import Department, Organization
from apps.users.models import RefreshToken, User
from core.constants import AttendanceSource, AttendanceStatus, Role, UserStatus

DEMO_SLUG = "acme-corp"
DEMO_PASSWORD = "Password123"

DEMO_PEOPLE = [
    ("admin@acme.test", "Aisha", "Kapoor", Role.ADMIN, "Engineering", "Head of Engineering"),
    ("hr@acme.test", "Rahul", "Menon", Role.HR, "People Ops", "HR Manager"),
    ("manager@acme.test", "Sara", "Iyer", Role.MANAGER, "Engineering", "Engineering Manager"),
    ("dev@acme.test", "Vikram", "Rao", Role.EMPLOYEE, "Engineering", "Software Engineer"),
    ("designer@acme.test", "Neha", "Shah", Role.EMPLOYEE, "Engineering", "Product Designer"),
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
        departments = self._departments(organization)
        owner = self._owner(organization)
        users = self._users(organization, departments)
        self._attendance(organization, [owner] + users, options["days"])

        self.stdout.write(self.style.SUCCESS("\nDemo data ready."))
        self.stdout.write("  Organization : {} ({})".format(organization.name, organization.slug))
        self.stdout.write("  Password     : {}\n".format(DEMO_PASSWORD))
        self.stdout.write("  Sign in as:")
        self.stdout.write("    owner@acme.test    super_admin  -> admin panel")
        for email, _, _, role, _, _ in DEMO_PEOPLE:
            panel = "admin panel" if role in Role.ADMIN_PANEL else "user panel"
            self.stdout.write("    {:<18} {:<12} -> {}".format(email, role, panel))

    # -- steps -------------------------------------------------------------
    def _reset(self):
        organization = Organization.objects.filter(slug=DEMO_SLUG).first()
        if not organization:
            return
        Attendance.objects.filter(organization=organization).delete()
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

    def _owner(self, organization) -> User:
        owner = User.objects.filter(email="owner@acme.test").first()
        if owner:
            return owner
        owner = User(
            organization=organization,
            email="owner@acme.test",
            first_name="Owner",
            last_name="Acme",
            role=Role.SUPER_ADMIN,
            status=UserStatus.ACTIVE,
            designation="Founder",
            employee_id="EMP001",
        )
        owner.set_password(DEMO_PASSWORD)
        return owner.save()

    def _users(self, organization, departments) -> list:
        created = []
        for index, (email, first, last, role, department, designation) in enumerate(DEMO_PEOPLE, start=2):
            user = User.objects.filter(email=email).first()
            if not user:
                user = User(
                    organization=organization,
                    department=departments.get(department),
                    email=email,
                    first_name=first,
                    last_name=last,
                    role=role,
                    status=UserStatus.ACTIVE,
                    designation=designation,
                    employee_id="EMP{:03d}".format(index),
                    date_of_joining=datetime.now(timezone.utc) - timedelta(days=120 + index * 10),
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
