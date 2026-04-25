from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "mallika_auth.db"


def get_db() -> sqlite3.Connection:
    database = sqlite3.connect(DATABASE_PATH)
    database.row_factory = sqlite3.Row
    return database


def list_users() -> int:
    with get_db() as db:
        rows = db.execute(
            "SELECT id, username, created_at, is_admin FROM users ORDER BY is_admin DESC, username COLLATE NOCASE ASC"
        ).fetchall()

    if not rows:
        print("No users found.")
        return 0

    print("ID  ROLE   USERNAME              CREATED")
    for row in rows:
        role = "admin" if row["is_admin"] else "user"
        print(f"{row['id']:<3} {role:<6} {row['username']:<20} {row['created_at']}")
    return 0


def delete_user(username: str) -> int:
    with get_db() as db:
        existing = db.execute("SELECT id, username, is_admin FROM users WHERE username = ?", (username,)).fetchone()
        if not existing:
            print(f"User '{username}' was not found.")
            return 1

        db.execute("DELETE FROM users WHERE id = ?", (existing["id"],))
        db.commit()

    print(f"Deleted user '{username}'.")
    if existing["is_admin"]:
        print("That account was an admin. If no admin remains, the next new registration will become admin.")
    return 0


def make_admin(username: str) -> int:
    with get_db() as db:
        existing = db.execute("SELECT id, username, is_admin FROM users WHERE username = ?", (username,)).fetchone()
        if not existing:
            print(f"User '{username}' was not found.")
            return 1

        if existing["is_admin"]:
            print(f"User '{username}' is already an admin.")
            return 0

        db.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (existing["id"],))
        db.commit()

    print(f"User '{username}' is now an admin.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Mallika Hospital users.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="Show all users and roles.")

    delete_parser = subparsers.add_parser("delete-user", help="Delete a user account.")
    delete_parser.add_argument("username", help="Username to delete")

    promote_parser = subparsers.add_parser("make-admin", help="Promote an existing user to admin.")
    promote_parser.add_argument("username", help="Username to promote")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "list":
        return list_users()
    if args.command == "delete-user":
        return delete_user(args.username)
    if args.command == "make-admin":
        return make_admin(args.username)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
