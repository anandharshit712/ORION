"""
Bootstrap the ORION system org and seed/promote the first superadmin user.

Usage:
    PYTHONPATH=. python scripts/bootstrap_superadmin.py \
        --email anandharshit560@gmail.com \
        --username Venomous \
        --password '<password>' \
        --full-name 'Harshit Anand'

Behaviour:
  - Creates (or fetches) the global "system" org with plan=enterprise, unlimited credits.
  - If a user with the given email/username exists: re-attaches to system org, sets
    role="superadmin". Optionally resets password if --reset-password supplied.
  - Else: creates a new superadmin user attached to the system org.

Idempotent: safe to run multiple times.
"""

from __future__ import annotations

import argparse
import sys

from arep.api.auth import hash_password
from arep.database.connection import init_database, session_scope
from arep.database.models import UserRecord
from arep.database.repository import OrganisationRepository, UserRepository


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed/promote the first superadmin user.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", default=None, help="Required if user does not exist")
    parser.add_argument("--full-name", default=None)
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="If set, overwrite hashed_password with --password even on existing user",
    )
    args = parser.parse_args()

    init_database()

    with session_scope() as session:
        org = OrganisationRepository(session).get_or_create_system_org()
        users = UserRepository(session)

        existing = (
            session.query(UserRecord)
            .filter(
                (UserRecord.email == args.email) | (UserRecord.username == args.username)
            )
            .first()
        )

        if existing is not None:
            existing.role = "superadmin"
            existing.org_id = org.id
            if args.full_name and not existing.full_name:
                existing.full_name = args.full_name
            if args.reset_password:
                if not args.password:
                    print("ERROR: --reset-password requires --password", file=sys.stderr)
                    return 2
                existing.hashed_password = hash_password(args.password)
            session.flush()
            session.refresh(existing)
            print(
                f"Promoted user id={existing.id} username={existing.username} "
                f"email={existing.email} -> role=superadmin org={org.slug}"
            )
            return 0

        if not args.password:
            print("ERROR: user does not exist; --password required to create", file=sys.stderr)
            return 2

        user = UserRecord(
            org_id=org.id,
            role="superadmin",
            email=args.email,
            username=args.username,
            hashed_password=hash_password(args.password),
            full_name=args.full_name,
        )
        session.add(user)
        session.flush()
        session.refresh(user)
        print(
            f"Created superadmin id={user.id} username={user.username} "
            f"email={user.email} org={org.slug}"
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
