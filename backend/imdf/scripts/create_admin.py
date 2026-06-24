#!/usr/bin/env python3
"""
IMDF Admin Account Creator
===========================
Creates or resets an admin user in the IMDF database.

Usage:
  python scripts/create_admin.py --username admin --password MySecurePass123
  python scripts/create_admin.py --username admin --password MySecurePass123 --role admin
  python scripts/create_admin.py --username admin --password MySecurePass123 --db sqlite:///data/imdf.db

If no --username/--password are provided, reads from environment variables:
  IMDF_ADMIN_USERNAME
  IMDF_ADMIN_PASSWORD

IMPORTANT: The current auth system (api/auth_routes.py) uses an in-memory
user store. For this admin account to work, the application must be updated
to load users from the database on startup (see db_models.py User model).
"""

import os
import sys
import argparse
from pathlib import Path

# Ensure the project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def hash_password(password: str) -> str:
    """Hash a password using argon2 (same as auth_routes.py)."""
    try:
        from argon2 import PasswordHasher
        ph = PasswordHasher()
        return ph.hash(password)
    except ImportError:
        print("ERROR: argon2-cffi is not installed. Run: pip install argon2-cffi")
        sys.exit(1)


def init_db(database_url: str = None):
    """Initialize the database and create tables if needed."""
    from sqlalchemy import create_engine
    from api.db_models import Base

    if database_url is None:
        database_url = os.environ.get("DATABASE_URL", "sqlite:///data/imdf.db")

    # Ensure data directory exists for SQLite
    if database_url.startswith("sqlite:///"):
        db_path = database_url.replace("sqlite:///", "")
        os.makedirs(os.path.dirname(db_path) or "data", exist_ok=True)

    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False} if "sqlite" in database_url else {},
    )
    Base.metadata.create_all(bind=engine)
    return engine, database_url


def create_admin(
    username: str,
    password: str,
    role: str = "admin",
    database_url: str = None,
    force: bool = False,
) -> bool:
    """Create or update an admin user in the database."""
    from sqlalchemy.orm import Session
    from api.db_models import User

    engine, db_url = init_db(database_url)
    password_hash = hash_password(password)

    with Session(engine) as session:
        existing = session.query(User).filter(User.username == username).first()

        if existing:
            if not force:
                print(f"User '{username}' already exists (role: {existing.role}).")
                print("Use --force to reset the password and role.")
                return False
            # Update existing user
            existing.password_hash = password_hash
            existing.role = role
            existing.status = "active"
            session.commit()
            print(f"[UPDATED] User '{username}' — password reset, role set to '{role}'.")
            return True
        else:
            # Create new user
            user = User(
                username=username,
                password_hash=password_hash,
                role=role,
                status="active",
            )
            session.add(user)
            session.commit()
            print(f"[CREATED] User '{username}' with role '{role}'.")
            return True


def main():
    parser = argparse.ArgumentParser(
        description="IMDF Admin Account Creator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/create_admin.py --username admin --password s3cur3!
  python scripts/create_admin.py --username admin --password s3cur3! --role admin
  python scripts/create_admin.py --username admin --password s3cur3! --force
  python scripts/create_admin.py --username admin --password s3cur3! --db sqlite:///data/imdf.db

Environment variables:
  IMDF_ADMIN_USERNAME   Default username
  IMDF_ADMIN_PASSWORD   Default password
  DATABASE_URL          Database URL (default: sqlite:///data/imdf.db)
        """,
    )
    parser.add_argument(
        "--username", "-u",
        default=os.environ.get("IMDF_ADMIN_USERNAME", ""),
        help="Admin username (env: IMDF_ADMIN_USERNAME)",
    )
    parser.add_argument(
        "--password", "-p",
        default=os.environ.get("IMDF_ADMIN_PASSWORD", ""),
        help="Admin password (env: IMDF_ADMIN_PASSWORD)",
    )
    parser.add_argument(
        "--role", "-r",
        default="admin",
        choices=["admin", "manager", "viewer"],
        help="User role (default: admin)",
    )
    parser.add_argument(
        "--db",
        default=os.environ.get("DATABASE_URL", "sqlite:///data/imdf.db"),
        help="Database URL (default: sqlite:///data/imdf.db)",
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force update if user already exists (reset password/role)",
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.username:
        print("ERROR: Username is required. Use --username or set IMDF_ADMIN_USERNAME.")
        sys.exit(1)
    if not args.password:
        print("ERROR: Password is required. Use --password or set IMDF_ADMIN_PASSWORD.")
        sys.exit(1)
    if len(args.password) < 8:
        print("WARNING: Password is shorter than 8 characters. Consider a stronger password.")
    if len(args.username) < 3:
        print("ERROR: Username must be at least 3 characters.")
        sys.exit(1)

    # Ensure we're running from the project root
    os.chdir(PROJECT_ROOT)

    success = create_admin(
        username=args.username,
        password=args.password,
        role=args.role,
        database_url=args.db,
        force=args.force,
    )

    if success:
        print(f"\nAdmin account ready. Login at /auth/login with:")
        print(f"  Username: {args.username}")
        print(f"  Role:     {args.role}")
        print(f"\nNOTE: auth_routes.py currently uses an in-memory user store.")
        print(f"The admin user has been written to the database ({args.db}).")
        print(f"To make it work, update auth_routes.py to load users from the DB.")
    else:
        print("\nNo changes made.")
        sys.exit(1)


if __name__ == "__main__":
    main()
