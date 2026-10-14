"""User accounts: sign up / sign in with email + password, sessions in an HttpOnly cookie. SQLite, stdlib only."""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import threading
import time

DB_PATH = os.getenv("SPYRA_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "spyra.db"))
COOKIE = "spyra_session"
SESSION_DAYS = 30
PBKDF2_ROUNDS = 240_000
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_lock = threading.Lock()
_fails: dict[str, list[float]] = {}  # ip -> recent failed sign-in times


def _db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def init() -> None:
    with _lock, _db() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
                pw_hash TEXT NOT NULL, created_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), expires_at REAL NOT NULL);
        """)


def _hash_pw(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2${PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def _check_pw(password: str, stored: str) -> bool:
    _, rounds, salt, want = stored.split("$")
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
    return hmac.compare_digest(dk.hex(), want)


def _token_hash(token: str) -> str:
    # Only a hash of the session token is stored, so a leaked database cannot be used to sign in.
    return hashlib.sha256(token.encode()).hexdigest()


def _public(row) -> dict:
    return {"id": row["id"], "name": row["name"], "email": row["email"], "demo": row["email"] == DEMO_EMAIL}


def sign_up(name: str, email: str, password: str) -> dict:
    name, email = (name or "").strip(), (email or "").strip().lower()
    if len(name) < 2:
        raise ValueError("Please enter your name.")
    if not EMAIL_RE.match(email):
        raise ValueError("Please enter a valid email address.")
    if len(password or "") < 8:
        raise ValueError("Password must be at least 8 characters.")
    with _lock, _db() as con:
        if con.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise ValueError("An account with this email already exists. Sign in instead.")
        cur = con.execute("INSERT INTO users (name, email, pw_hash, created_at) VALUES (?, ?, ?, ?)",
                          (name, email, _hash_pw(password), time.time()))
        return {"id": cur.lastrowid, "name": name, "email": email}


def throttled(ip: str) -> bool:
    """True after 8 failed sign-ins from one IP in 15 minutes."""
    now = time.time()
    recent = [t for t in _fails.get(ip, []) if now - t < 900]
    _fails[ip] = recent
    return len(recent) >= 8


def sign_in(email: str, password: str, ip: str) -> dict:
    email = (email or "").strip().lower()
    with _lock, _db() as con:
        row = con.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not row or not _check_pw(password or "", row["pw_hash"]):
        _fails.setdefault(ip, []).append(time.time())
        raise ValueError("Wrong email or password.")
    _fails.pop(ip, None)
    return _public(row)


def new_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with _lock, _db() as con:
        con.execute("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))
        con.execute("INSERT INTO sessions VALUES (?, ?, ?)", (_token_hash(token), user_id, time.time() + SESSION_DAYS * 86400))
    return token


def user_for(token: str | None) -> dict | None:
    if not token:
        return None
    with _lock, _db() as con:
        row = con.execute("SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
                          "WHERE s.token_hash = ? AND s.expires_at > ?", (_token_hash(token), time.time())).fetchone()
    return _public(row) if row else None


def end_session(token: str | None) -> None:
    if token:
        with _lock, _db() as con:
            con.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


DEMO_EMAIL = "demo@spyra.si"


def demo_user() -> dict:
    """The shared demo account behind the "Try the demo" button (created on first use, password never shown)."""
    with _lock, _db() as con:
        row = con.execute("SELECT * FROM users WHERE email = ?", (DEMO_EMAIL,)).fetchone()
        if not row:
            con.execute("INSERT INTO users (name, email, pw_hash, created_at) VALUES (?, ?, ?, ?)",
                        ("Demo user", DEMO_EMAIL, _hash_pw(secrets.token_urlsafe(24)), time.time()))
            row = con.execute("SELECT * FROM users WHERE email = ?", (DEMO_EMAIL,)).fetchone()
    return _public(row) | {"demo": True}
