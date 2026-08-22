import logging

logger = logging.getLogger(__name__)


"""Teams domain business logic."""
import calendar
from datetime import date, datetime, time, timedelta, timezone

from apps.attendance.models import Attendance
from apps.leaves.models import Holiday, LeaveRequest
from apps.teams.models import Team, TeamHierarchyLevel, TeamMember
from apps.users.models import User
from core.exceptions import NotFound, ValidationError
from core.validators import parse_date, require_fields, validate_object_id


# ---------------------------------------------------------------------------
# Teams Admin CRUD
# ---------------------------------------------------------------------------
def list_teams(organization, status=None):
    """List teams for an organization."""
    queryset = Team.objects.filter(organization=organization, is_deleted=False)
    if status:
        queryset = queryset.filter(status=status)
    return queryset.order_by("name")


def get_team(organization, team_id: str) -> Team:
    """Retrieve a team by ID, ensuring organization boundary."""
    tid = validate_object_id(team_id, "team_id")
    team = Team.objects.filter(id=tid, organization=organization, is_deleted=False).first()
    if not team:
        raise NotFound("Team not found.")
    return team


def create_team(organization, data: dict) -> Team:
    """Create a new team in the organization."""
    require_fields(data, ["name"])
    name = str(data["name"]).strip()

    if Team.objects.filter(organization=organization, name=name, is_deleted=False).first():
        raise ValidationError("A team with this name already exists.", details={"name": "Name must be unique."})

    team = Team(
        organization=organization,
        name=name,
        description=str(data.get("description", "")).strip(),
        status=data.get("status", Team.STATUS_ACTIVE),
    )
    return team.save()


def update_team(organization, team_id: str, data: dict) -> Team:
    """Update team attributes."""
    team = get_team(organization, team_id)

    if "name" in data:
        name = str(data["name"]).strip()
        if not name:
            raise ValidationError("Team name cannot be empty.", details={"name": "Name is required."})
        existing = Team.objects.filter(organization=organization, name=name, is_deleted=False).first()
        if existing and str(existing.id) != str(team.id):
            raise ValidationError("A team with this name already exists.", details={"name": "Name must be unique."})
        team.name = name

    if "description" in data:
        team.description = str(data["description"]).strip()

    if "status" in data:
        if data["status"] not in Team.STATUS_CHOICES:
            raise ValidationError("Invalid status value.", details={"status": "Must be active or inactive."})
        team.status = data["status"]

    team.save()
    return team


def delete_team(organization, team_id: str) -> bool:
    """Soft delete / deactivate a team and deactivate memberships."""
    team = get_team(organization, team_id)
    team.status = Team.STATUS_INACTIVE
    team.soft_delete()

    # Deactivate active team memberships for this team
    TeamMember.objects.filter(team=team, is_active=True).update(set__is_active=False)
    return True


# ---------------------------------------------------------------------------
# Team Hierarchy Management
# ---------------------------------------------------------------------------
def list_hierarchy_levels(team: Team):
    """List hierarchy levels for a team ordered by rank."""
    return TeamHierarchyLevel.objects.filter(team=team, is_active=True, is_deleted=False).order_by("order", "name")


def get_hierarchy_level(team: Team, level_id: str) -> TeamHierarchyLevel:
    lid = validate_object_id(level_id, "level_id")
    level = TeamHierarchyLevel.objects.filter(id=lid, team=team, is_deleted=False).first()
    if not level:
        raise NotFound("Hierarchy level not found.")
    return level


def create_hierarchy_level(team: Team, data: dict) -> TeamHierarchyLevel:
    """Create a new hierarchy level for a team."""
    require_fields(data, ["name"])
    name = str(data["name"]).strip()

    existing = TeamHierarchyLevel.objects.filter(team=team, name=name, is_active=True, is_deleted=False).first()
    if existing:
        raise ValidationError("A hierarchy level with this name already exists in the team.", details={"name": "Name must be unique."})

    # Default order to max existing order + 1
    existing_levels = TeamHierarchyLevel.objects.filter(team=team, is_active=True, is_deleted=False)
    max_order = max([l.order for l in existing_levels], default=0)
    order = int(data.get("order", max_order + 1))

    level = TeamHierarchyLevel(
        team=team,
        name=name,
        order=order,
        is_active=True,
    )
    return level.save()


def update_hierarchy_level(team: Team, level_id: str, data: dict) -> TeamHierarchyLevel:
    """Update name or order of a hierarchy level."""
    level = get_hierarchy_level(team, level_id)

    if "name" in data:
        name = str(data["name"]).strip()
        if not name:
            raise ValidationError("Hierarchy level name cannot be empty.", details={"name": "Name is required."})
        existing = TeamHierarchyLevel.objects.filter(team=team, name=name, is_active=True, is_deleted=False).first()
        if existing and str(existing.id) != str(level.id):
            raise ValidationError("A hierarchy level with this name already exists in the team.", details={"name": "Name must be unique."})
        level.name = name

    if "order" in data:
        try:
            level.order = int(data["order"])
        except (ValueError, TypeError):
            raise ValidationError("Order must be an integer.", details={"order": "Must be an integer."})

    level.save()
    return level


def reorder_hierarchy_levels(team: Team, level_orders: list) -> list:
    """Reorder hierarchy levels in bulk using list of dicts [{'id': '...', 'order': 1}, ...]."""
    if not isinstance(level_orders, list):
        raise ValidationError("Invalid input format.", details={"levels": "Expected a list of levels with orders."})

    updated = []
    for item in level_orders:
        if not isinstance(item, dict) or "id" not in item or "order" not in item:
            continue
        level = get_hierarchy_level(team, item["id"])
        level.order = int(item["order"])
        level.save()
        updated.append(level)

    return list_hierarchy_levels(team)


def delete_hierarchy_level(team: Team, level_id: str) -> bool:
    """Soft delete a hierarchy level and detach members assigned to it."""
    level = get_hierarchy_level(team, level_id)
    level.is_active = False
    level.soft_delete()

    # Clear level reference for team members
    TeamMember.objects.filter(team=team, hierarchy_level=level).update(set__hierarchy_level=None)
    return True


# ---------------------------------------------------------------------------
# Team Membership Management
# ---------------------------------------------------------------------------
def list_team_members(team: Team):
    """List active members of a team."""
    return TeamMember.objects.filter(team=team, is_active=True, is_deleted=False)


def add_team_member(organization, team: Team, user_id: str, hierarchy_level_id: str = None) -> TeamMember:
    """Add or assign an employee to a team with optional hierarchy level."""
    uid = validate_object_id(user_id, "user_id")
    user = User.objects.filter(id=uid, organization=organization, is_deleted=False).first()
    if not user:
        raise ValidationError("Employee not found or belongs to another organization.", details={"user_id": "Invalid employee."})

    hierarchy_level = None
    if hierarchy_level_id and str(hierarchy_level_id).strip():
        hierarchy_level = get_hierarchy_level(team, hierarchy_level_id)

    # Deactivate existing active team memberships in other teams to ensure single active team
    TeamMember.objects.filter(organization=organization, employee=user, team__ne=team, is_active=True).update(set__is_active=False)

    member = TeamMember.objects.filter(organization=organization, team=team, employee=user, is_deleted=False).first()
    if not member:
        member = TeamMember(
            organization=organization,
            team=team,
            employee=user,
        )

    member.hierarchy_level = hierarchy_level
    member.is_active = True
    return member.save()


def remove_team_member(organization, team: Team, user_id: str) -> bool:
    """Deactivate an employee's membership in a team."""
    uid = validate_object_id(user_id, "user_id")
    user = User.objects.filter(id=uid, organization=organization, is_deleted=False).first()
    if not user:
        raise ValidationError("Employee not found.", details={"user_id": "Invalid employee."})

    members = TeamMember.objects.filter(team=team, employee=user, is_active=True)
    if not members:
        raise NotFound("Employee is not an active member of this team.")

    members.update(set__is_active=False)
    return True


def move_team_member(organization, user_id: str, target_team_id: str, target_hierarchy_level_id: str = None) -> TeamMember:
    """Move an employee from their current team to a target team."""
    target_team = get_team(organization, target_team_id)
    return add_team_member(organization, target_team, user_id, hierarchy_level_id=target_hierarchy_level_id)


def assign_hierarchy_level(team: Team, user_id: str, hierarchy_level_id: str) -> TeamMember:
    """Assign or change hierarchy level for an existing team member."""
    uid = validate_object_id(user_id, "user_id")
    member = TeamMember.objects.filter(team=team, employee=uid, is_active=True, is_deleted=False).first()
    if not member:
        raise NotFound("Active team member not found.")

    hierarchy_level = None
    if hierarchy_level_id and str(hierarchy_level_id).strip():
        hierarchy_level = get_hierarchy_level(team, hierarchy_level_id)

    member.hierarchy_level = hierarchy_level
    member.save()
    return member


# ---------------------------------------------------------------------------
# Employee Team Views
# ---------------------------------------------------------------------------
def get_my_team(organization, employee: User) -> dict:
    """Retrieve team information for signed-in employee."""
    membership = TeamMember.objects.filter(
        organization=organization,
        employee=employee,
        is_active=True,
        is_deleted=False,
    ).first()

    if not membership or not membership.team or membership.team.status != Team.STATUS_ACTIVE:
        return {
            "team": None,
            "hierarchy_levels": [],
            "members": [],
        }

    team = membership.team
    hierarchy_levels = [hl.to_dict() for hl in list_hierarchy_levels(team)]
    members = [m.to_dict() for m in list_team_members(team)]

    # Sort members by hierarchy order (1=highest) then name
    def sort_key(m):
        hl = m.get("hierarchy_level")
        order = hl["order"] if hl else 9999
        name = m.get("employee", {}).get("full_name", "")
        return (order, name)

    members.sort(key=sort_key)

    team_data = team.to_dict()
    team_data["my_membership"] = membership.to_dict()

    return {
        "team": team_data,
        "hierarchy_levels": hierarchy_levels,
        "members": members,
    }


def get_team_availability(organization, employee: User, target_date_str: str = None) -> dict:
    """Get current week (Mon-Fri) availability grid for employee's team."""
    team_info = get_my_team(organization, employee)
    team = team_info.get("team")
    members_data = team_info.get("members", [])

    if not team or not members_data:
        return {
            "start_date": None,
            "end_date": None,
            "days": [],
            "members": [],
        }

    # Determine week range (Monday to Friday)
    if target_date_str:
        ref_d = parse_date(target_date_str, "target_date") or date.today()
    else:
        ref_d = date.today()

    monday_d = ref_d - timedelta(days=ref_d.weekday())
    friday_d = monday_d + timedelta(days=4)

    week_dates = [(monday_d + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(5)]
    week_start_dt = datetime.combine(monday_d, time.min, tzinfo=timezone.utc)
    week_end_dt = datetime.combine(friday_d, time.max, tzinfo=timezone.utc)

    # Pre-fetch holidays, leaves, and attendance for week
    holidays = Holiday.objects.filter(
        organization=organization, is_active=True, is_deleted=False,
        date__gte=week_start_dt, date__lte=week_end_dt
    )
    holiday_dates = {h.date.strftime("%Y-%m-%d"): h.name for h in holidays}

    member_user_ids = [m["employee"]["id"] for m in members_data if m.get("employee")]

    # Pre-fetch approved leaves for team members
    approved_leaves = LeaveRequest.objects.filter(
        organization=organization,
        employee__in=member_user_ids,
        status=LeaveRequest.STATUS_APPROVED,
        is_deleted=False,
        start_date__lte=week_end_dt,
        end_date__gte=week_start_dt,
    )

    # Pre-fetch attendance records for week
    attendance_records = Attendance.objects.filter(
        organization=organization,
        user__in=member_user_ids,
        is_deleted=False,
        date__gte=week_start_dt,
        date__lte=week_end_dt,
    )

    # Map attendance: (user_id, date_str) -> status
    att_map = {}
    for att in attendance_records:
        uid = str(att.user.id) if att.user else None
        d_str = att.date.strftime("%Y-%m-%d") if att.date else None
        if uid and d_str:
            att_map[(uid, d_str)] = att.status

    # Map leaves: (user_id, date_str) -> True
    leave_map = {}
    for l in approved_leaves:
        uid = str(l.employee.id) if l.employee else None
        if not uid:
            continue
        cur = l.start_date.date()
        end = l.end_date.date()
        while cur <= end:
            leave_map[(uid, cur.strftime("%Y-%m-%d"))] = True
            cur += timedelta(days=1)

    today_str = date.today().strftime("%Y-%m-%d")

    grid_members = []
    for m in members_data:
        emp = m.get("employee")
        if not emp:
            continue
        uid = emp["id"]

        availability_list = []
        for d_str in week_dates:
            if d_str in holiday_dates:
                status = "HOLIDAY"
                label = f"Holiday ({holiday_dates[d_str]})"
            elif (uid, d_str) in leave_map:
                status = "ON_LEAVE"
                label = "On Leave"
            elif (uid, d_str) in att_map:
                att_status = att_map[(uid, d_str)]
                status = att_status.upper()
                label = att_status.replace("_", " ").title()
            elif d_str <= today_str:
                status = "ABSENT"
                label = "Absent"
            else:
                status = "SCHEDULED"
                label = "Scheduled"

            availability_list.append({
                "date": d_str,
                "status": status,
                "label": label,
            })

        grid_members.append({
            "employee": emp,
            "hierarchy_level": m.get("hierarchy_level"),
            "availability": availability_list,
        })

    return {
        "start_date": monday_d.strftime("%Y-%m-%d"),
        "end_date": friday_d.strftime("%Y-%m-%d"),
        "days": week_dates,
        "members": grid_members,
    }


def get_team_birthdays(organization, employee: User, ref_date_str: str = None) -> dict:
    """Get today's and upcoming (next 7 days) birthdays for team members."""
    team_info = get_my_team(organization, employee)
    members_data = team_info.get("members", [])

    if not members_data:
        return {
            "birthdays_today": [],
            "upcoming_birthdays": [],
        }

    if ref_date_str:
        today = parse_date(ref_date_str, "ref_date") or date.today()
    else:
        today = date.today()

    birthdays_today = []
    upcoming_birthdays = []

    for m in members_data:
        emp = m.get("employee")
        if not emp or not emp.get("date_of_birth"):
            continue

        dob_str = emp["date_of_birth"]
        dob = parse_date(dob_str, "date_of_birth")
        if not dob:
            continue

        # Birthday in current year
        try:
            bday_this_year = date(today.year, dob.month, dob.day)
        except ValueError:
            # Handle Feb 29 on non-leap year -> Feb 28
            bday_this_year = date(today.year, 2, 28)

        # Handle year boundary (e.g. Dec 30 -> Jan 5)
        if bday_this_year < today:
            try:
                bday_next = date(today.year + 1, dob.month, dob.day)
            except ValueError:
                bday_next = date(today.year + 1, 2, 28)
        else:
            bday_next = bday_this_year

        days_until = (bday_next - today).days

        item = {
            "employee": emp,
            "hierarchy_level": m.get("hierarchy_level"),
            "birthday_date": dob_str,
            "days_until": days_until,
            "is_today": days_until == 0,
        }

        if days_until == 0:
            birthdays_today.append(item)
        elif 1 <= days_until <= 7:
            upcoming_birthdays.append(item)

    upcoming_birthdays.sort(key=lambda x: x["days_until"])

    return {
        "birthdays_today": birthdays_today,
        "upcoming_birthdays": upcoming_birthdays,
    }
