from django.core.management.base import BaseCommand
from core.constants import Role as RoleEnum, Permissions
from apps.organization.models import Organization
from apps.users.models import User, Role

class Command(BaseCommand):
    help = "Migrate string roles to dynamic Role references per organization"

    def handle(self, *args, **options):
        orgs = Organization.objects.all()
        for org in orgs:
            self.stdout.write(f"Migrating organization: {org.name}")
            
            roles = {
                RoleEnum.ADMIN: Role.objects.filter(organization=org, slug=RoleEnum.ADMIN).first(),
                RoleEnum.HR: Role.objects.filter(organization=org, slug=RoleEnum.HR).first(),
                RoleEnum.MANAGER: Role.objects.filter(organization=org, slug=RoleEnum.MANAGER).first(),
                RoleEnum.EMPLOYEE: Role.objects.filter(organization=org, slug=RoleEnum.EMPLOYEE).first(),
            }
            
            if not roles[RoleEnum.ADMIN]:
                roles[RoleEnum.ADMIN] = Role(organization=org, name="Admin", slug=RoleEnum.ADMIN, is_system=True, permissions=list(Permissions.ALL)).save()
            if not roles[RoleEnum.HR]:
                perms = [p for p in Permissions.ALL if p.startswith('users.') or p.startswith('leaves.') or p in (Permissions.ATTENDANCE_VIEW_ALL, Permissions.ATTENDANCE_MANAGE, Permissions.ORG_VIEW, Permissions.DEPARTMENTS_MANAGE, Permissions.ROLES_VIEW, Permissions.ROLES_ASSIGN)]
                roles[RoleEnum.HR] = Role(organization=org, name="HR Manager", slug=RoleEnum.HR, is_system=True, permissions=perms).save()
            if not roles[RoleEnum.MANAGER]:
                perms = [Permissions.USERS_VIEW, Permissions.ATTENDANCE_PUNCH, Permissions.ATTENDANCE_VIEW_OWN, Permissions.ATTENDANCE_VIEW_TEAM, Permissions.LEAVES_APPLY, Permissions.LEAVES_VIEW_OWN, Permissions.LEAVES_VIEW_TEAM, Permissions.LEAVES_APPROVE, Permissions.ORG_VIEW]
                roles[RoleEnum.MANAGER] = Role(organization=org, name="Manager", slug=RoleEnum.MANAGER, is_system=True, permissions=perms).save()
            if not roles[RoleEnum.EMPLOYEE]:
                perms = [Permissions.USERS_VIEW, Permissions.ATTENDANCE_PUNCH, Permissions.ATTENDANCE_VIEW_OWN, Permissions.LEAVES_APPLY, Permissions.LEAVES_VIEW_OWN, Permissions.ORG_VIEW]
                roles[RoleEnum.EMPLOYEE] = Role(organization=org, name="Employee", slug=RoleEnum.EMPLOYEE, is_system=True, permissions=perms).save()

            # Now find users in this org that still have string roles
            users = User.objects.filter(organization=org)
            for user in users:
                # If user.role is a string (legacy)
                # MongoDB query returns it as a generic reference or we can just update it
                # Wait, mongoengine might fail to deserialize `User` if `role` expects a ReferenceField but finds a string.
                # Actually, MongoEngine might raise a ValidationError when reading.
                # To bypass, we can use PyMongo raw updates:
                pass
                
        # Run raw PyMongo update
        self.stdout.write("Running raw MongoDB updates...")
        db = Organization._get_collection().database
        users_coll = db['users']
        roles_coll = db['roles']
        
        migrated = 0
        for doc in users_coll.find({}):
            role_val = doc.get("role")
            if isinstance(role_val, str):
                org_id = doc.get("organization")
                if org_id:
                    role_doc = roles_coll.find_one({"organization": org_id, "slug": role_val})
                    if role_doc:
                        users_coll.update_one({"_id": doc["_id"]}, {"$set": {"role": role_doc["_id"]}})
                        migrated += 1

        self.stdout.write(self.style.SUCCESS(f"Migrated {migrated} users to dynamic roles."))
