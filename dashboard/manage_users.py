#!/usr/bin/env python3
"""Provision or rotate local Lead Studio credentials without printing passwords."""

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dashboard.auth import USERS, USERS_PATH, provision, set_password  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Manage Lead Studio accounts")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("init", help="create the three required accounts")
    rotate = sub.add_parser("set-password", help="rotate one account password")
    rotate.add_argument("username", choices=USERS)
    args = parser.parse_args(argv)
    try:
        if args.action == "init":
            if USERS_PATH.exists():
                parser.error(f"credential store already exists: {USERS_PATH}")
            passwords = {user: getpass.getpass(f"Password for {user}: ") for user in USERS}
            provision(passwords)
            print(f"Created {', '.join(USERS)} in {USERS_PATH}")
        else:
            password = getpass.getpass(f"New password for {args.username}: ")
            set_password(args.username, password)
            print(f"Updated {args.username}; active sessions will be revoked.")
    except (ValueError, FileExistsError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
