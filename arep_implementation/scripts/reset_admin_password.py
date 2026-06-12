#!/usr/bin/env python3
"""
Emergency admin password reset script.

Usage (run from arep_implementation/):
    python scripts/reset_admin_password.py --email admin@example.com --new-password NewPass123

Does NOT require the API to be running — writes directly to the database.
"""
import argparse
import sys
from pathlib import Path

# Make sure arep package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def main() -> None:
    parser = argparse.ArgumentParser(description="Reset a user password directly in the DB")
    parser.add_argument("--email", required=True, help="Email of the account to reset")
    parser.add_argument("--new-password", required=True, help="New password (min 6 chars)")
    args = parser.parse_args()

    if len(args.new_password) < 6:
        print("ERROR: password must be at least 6 characters")
        sys.exit(1)
    if len(args.new_password) > 72:
        print("ERROR: password cannot be longer than 72 characters")
        sys.exit(1)

    from arep.api.auth import hash_password
    from arep.database.connection import session_scope
    from arep.database.models import UserRecord
    from arep.database.repository import PasswordResetRepository

    with session_scope() as session:
        user = session.query(UserRecord).filter_by(email=args.email).first()
        if user is None:
            print(f"ERROR: no user found with email '{args.email}'")
            sys.exit(1)

        # Invalidate all outstanding reset tokens for this user
        pr_repo = PasswordResetRepository(session)
        invalidated = pr_repo.invalidate_all_for_user(user.id)

        user.hashed_password = hash_password(args.new_password)
        session.flush()

    print(f"Password updated for {user.email} (username: {user.username}, role: {user.role})")
    if invalidated:
        print(f"Invalidated {invalidated} outstanding reset token(s)")
    print("You can now log in via POST /api/auth/login")

if __name__ == "__main__":
    main()
