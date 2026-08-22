"""Give existing records the fields the login-ID scheme needs.

    python manage.py backfill_login_ids
    python manage.py backfill_login_ids --dry-run

Organizations created before the scheme existed have no `code`, and their users
have no `login_id`.  Both are required and unique, so a database seeded earlier
must be filled in before anyone can sign in again.

This talks to pymongo directly rather than through mongoengine documents: the
unique index on `login_id` cannot be built while several documents still hold a
null there, and mongoengine builds its indexes on first use.  Writing at the
driver level fills the values in first, so the index builds cleanly afterwards.

Safe to re-run - records that already carry the fields are skipped.
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from mongoengine.connection import get_db

from core.identifiers import build_login_id, organization_code


class Command(BaseCommand):
    help = "Assign organization codes and login IDs to records created before they existed."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report without writing.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        db = get_db()

        organizations = self._backfill_organizations(db, dry_run)
        users = self._backfill_users(db, dry_run)

        verb = "would be updated" if dry_run else "updated"
        style = self.style.WARNING if dry_run else self.style.SUCCESS
        self.stdout.write(style("\n{} organizations and {} users {}.".format(
            organizations, users, verb)))

        if not dry_run and users:
            self.stdout.write("Sign-in now uses these login IDs; emails still work too.")

    # -- organizations -----------------------------------------------------
    def _backfill_organizations(self, db, dry_run: bool) -> int:
        taken = {
            doc["code"] for doc in db.organizations.find({"code": {"$exists": True, "$ne": None}})
        }
        updated = 0

        for doc in db.organizations.find({"$or": [{"code": None}, {"code": {"$exists": False}}]}):
            code = self._free_code(doc.get("name", ""), taken)
            taken.add(code)
            self.stdout.write("  org   {:<26} -> {}".format(str(doc.get("name"))[:26], code))
            if not dry_run:
                db.organizations.update_one({"_id": doc["_id"]}, {"$set": {"code": code}})
            updated += 1
        return updated

    # -- users -------------------------------------------------------------
    def _backfill_users(self, db, dry_run: bool) -> int:
        codes = {doc["_id"]: doc.get("code") or organization_code(doc.get("name", ""))
                 for doc in db.organizations.find()}

        # Continue numbering after whatever is already assigned, per org+year.
        serials = defaultdict(int)
        for doc in db.users.find({"login_id": {"$exists": True, "$ne": None}}):
            year = self._year_of(doc)
            serials[(doc.get("organization"), year)] += 1

        taken = {doc["login_id"] for doc in
                 db.users.find({"login_id": {"$exists": True, "$ne": None}})}
        updated = 0

        pending = db.users.find(
            {"$or": [{"login_id": None}, {"login_id": {"$exists": False}}]}
        ).sort("date_of_joining", 1)

        for doc in pending:
            org_id = doc.get("organization")
            if org_id not in codes:
                self.stdout.write(self.style.WARNING(
                    "  skip  {} - unknown organization".format(doc.get("email"))))
                continue

            year = self._year_of(doc)
            key = (org_id, year)

            serials[key] += 1
            login_id = build_login_id(
                codes[org_id], doc.get("first_name", ""), doc.get("last_name", ""),
                year, serials[key],
            )
            while login_id in taken:
                serials[key] += 1
                login_id = build_login_id(
                    codes[org_id], doc.get("first_name", ""), doc.get("last_name", ""),
                    year, serials[key],
                )
            taken.add(login_id)

            self.stdout.write("  user  {:<26} -> {}".format(str(doc.get("email"))[:26], login_id))
            if not dry_run:
                # The ID's year segment comes from the joining date, so persist
                # the fallback we used rather than leaving the field empty.
                update = {"login_id": login_id}
                if not doc.get("date_of_joining"):
                    update["date_of_joining"] = doc.get("created_at")
                db.users.update_one({"_id": doc["_id"]}, {"$set": update})
            updated += 1
        return updated

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _year_of(doc) -> int:
        from datetime import datetime, timezone

        moment = doc.get("date_of_joining") or doc.get("created_at")
        return (moment or datetime.now(timezone.utc)).year

    @staticmethod
    def _free_code(name: str, taken: set) -> str:
        base = organization_code(name)
        if base not in taken:
            return base
        for suffix in range(1, 100):
            candidate = "{}{}".format(base, suffix)
            if candidate not in taken:
                return candidate
        raise RuntimeError("Could not allocate an organization code for {}".format(name))
