"""Local dashboard accounts and short-lived, server-side sessions."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
import threading
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USERS_PATH = ROOT / "data" / "dashboard-users.json"
USERS = ("tarun", "prabh", "uttkarsh")
ITERATIONS = 600_000
SESSION_SECONDS = 12 * 60 * 60
FAILED_LIMIT = 5
FAILED_WINDOW = 10 * 60


def _record(password: str) -> dict[str, str | int]:
    salt = secrets.token_bytes(32)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return {"salt": salt.hex(), "hash": digest.hex(), "iterations": ITERATIONS}


def _write_users(path: Path, users: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".dashboard-users-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump({"users": users}, out, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def provision(passwords: dict[str, str], path: Path = USERS_PATH) -> None:
    """Create the exact three accounts once; never overwrite an existing store."""
    if set(passwords) != set(USERS) or not all(isinstance(p, str) and p for p in passwords.values()):
        raise ValueError("provide a nonempty password for tarun, prabh, and uttkarsh")
    if path.exists():
        raise FileExistsError(f"credential store already exists: {path}")
    _write_users(path, {user: _record(passwords[user]) for user in USERS})


def load_users(path: Path = USERS_PATH) -> dict:
    try:
        if os.name != "nt" and path.stat().st_mode & 0o077:
            raise ValueError(f"credential store must be owner-only (chmod 600): {path}")
        users = json.loads(path.read_text(encoding="utf-8"))["users"]
        if set(users) != set(USERS):
            raise ValueError("credential store must contain exactly tarun, prabh, and uttkarsh")
        for record in users.values():
            if record["iterations"] != ITERATIONS or len(bytes.fromhex(record["salt"])) != 32 or len(bytes.fromhex(record["hash"])) != 32:
                raise ValueError("invalid password record")
        return users
    except FileNotFoundError as exc:
        raise ValueError(f"dashboard accounts are not configured; run python dashboard/manage_users.py init ({path})") from exc
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid credential store: {path}") from exc


def set_password(username: str, password: str, path: Path = USERS_PATH) -> None:
    if username not in USERS or not password:
        raise ValueError("choose tarun, prabh, or uttkarsh and a nonempty password")
    users = load_users(path)
    users[username] = _record(password)
    _write_users(path, users)


class AuthStore:
    def __init__(self, path: Path = USERS_PATH):
        self.path = path
        self.users = load_users(path)
        self.mtime = path.stat().st_mtime_ns
        self.lock = threading.RLock()
        self.sessions: dict[str, dict] = {}
        self.failures: dict[str, deque[float]] = {}

    def _reload(self) -> None:
        mtime = self.path.stat().st_mtime_ns
        if mtime != self.mtime:
            self.users = load_users(self.path)
            self.mtime = mtime
            self.sessions.clear()  # password changes revoke every active session

    def login(self, username: str, password: str, peer: str) -> tuple[str, str] | None:
        username = username.strip().lower()
        if not isinstance(password, str) or len(password) > 1024:
            return None
        now = time.monotonic()
        key = f"{peer}:{username}"
        with self.lock:
            self._reload()
            attempts = self.failures.setdefault(key, deque())
            while attempts and now - attempts[0] > FAILED_WINDOW:
                attempts.popleft()
            if len(attempts) >= FAILED_LIMIT:
                raise PermissionError("too many attempts; try again later")
            record = self.users.get(username)
            salt = bytes.fromhex(record["salt"]) if record else bytes(32)
            expected = bytes.fromhex(record["hash"]) if record else bytes(32)
            candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
            if not record or not hmac.compare_digest(candidate, expected):
                attempts.append(now)
                return None
            self.failures.pop(key, None)
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            self.sessions[token] = {"username": username, "csrf": csrf, "expires": time.time() + SESSION_SECONDS}
            return token, csrf

    def session(self, token: str) -> dict | None:
        with self.lock:
            self._reload()
            session = self.sessions.get(token)
            if not session:
                return None
            if session["expires"] <= time.time():
                self.sessions.pop(token, None)
                return None
            return session.copy()

    def revoke(self, token: str) -> None:
        with self.lock:
            self.sessions.pop(token, None)
