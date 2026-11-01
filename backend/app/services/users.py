"""Accounts, credits, and refresh-token rotation, all stored in auth.db."""

import sqlite3
import time
import uuid

from app.config import Settings
from app.db import connect
from app.schemas import Credits, UserOut
from app.security import create_refresh_token, decode_token, hash_password, verify_password


class EmailTaken(Exception):
    pass


class AccountLocked(Exception):
    pass


def to_user_out(settings: Settings, row: sqlite3.Row) -> UserOut:
    limit = settings.user_credits
    used = row["credits_used"]
    return UserOut(id=row["id"], email=row["email"], credits=Credits(limit=limit, used=used, remaining=max(limit - used, 0)))


def get_user(settings: Settings, user_id: str) -> sqlite3.Row | None:
    with connect(settings.auth_db_path) as db:
        return db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def create_user(settings: Settings, email: str, password: str) -> sqlite3.Row:
    password_hash = hash_password(password)
    with connect(settings.auth_db_path) as db:
        try:
            db.execute(
                "INSERT INTO users (id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (uuid.uuid4().hex, email, password_hash, int(time.time())),
            )
        except sqlite3.IntegrityError as exc:
            raise EmailTaken from exc
        return db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


def authenticate(settings: Settings, email: str, password: str) -> sqlite3.Row | None:
    """Return the user for valid credentials, applying a temporary lock after repeated failures."""
    now = int(time.time())
    with connect(settings.auth_db_path) as db:
        row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if row is not None and row["locked_until"] > now:
        raise AccountLocked

    if not verify_password(password, row["password_hash"] if row else None):
        if row is not None:
            with connect(settings.auth_db_path) as db:
                failures = row["failed_logins"] + 1
                locked = failures >= settings.login_max_failures
                db.execute(
                    "UPDATE users SET failed_logins = ?, locked_until = ? WHERE id = ?",
                    (0 if locked else failures, now + settings.login_lock_minutes * 60 if locked else 0, row["id"]),
                )
        return None

    with connect(settings.auth_db_path) as db:
        db.execute("UPDATE users SET failed_logins = 0, locked_until = 0 WHERE id = ?", (row["id"],))
    return row


def consume_credits(settings: Settings, user_id: str, amount: int) -> bool:
    """Atomically reserve credits. The limit is read from settings, so raising it applies to everyone."""
    with connect(settings.auth_db_path) as db:
        cursor = db.execute(
            "UPDATE users SET credits_used = credits_used + ? WHERE id = ? AND credits_used + ? <= ?",
            (amount, user_id, amount, settings.user_credits),
        )
        return cursor.rowcount == 1


def refund_credits(settings: Settings, user_id: str, amount: int) -> None:
    with connect(settings.auth_db_path) as db:
        db.execute("UPDATE users SET credits_used = MAX(credits_used - ?, 0) WHERE id = ?", (amount, user_id))


def issue_refresh_token(settings: Settings, user_id: str, family_id: str | None = None) -> str:
    family_id = family_id or uuid.uuid4().hex
    token, jti, expires_at = create_refresh_token(settings, user_id, family_id)
    with connect(settings.auth_db_path) as db:
        db.execute("DELETE FROM refresh_tokens WHERE expires_at < ?", (int(time.time()),))
        db.execute(
            "INSERT INTO refresh_tokens (jti, user_id, family_id, expires_at) VALUES (?, ?, ?, ?)",
            (jti, user_id, family_id, expires_at),
        )
    return token


def rotate_refresh_token(settings: Settings, token: str) -> tuple[str, str] | None:
    """Exchange a refresh token for a new one, returning (user_id, new_token).

    Replaying an already-rotated token after the grace window suggests theft,
    so the whole token family is revoked and the user must log in again.
    """
    claims = decode_token(settings, token, "refresh")
    if claims is None or "jti" not in claims:
        return None
    now = int(time.time())
    with connect(settings.auth_db_path) as db:
        row = db.execute("SELECT * FROM refresh_tokens WHERE jti = ?", (claims["jti"],)).fetchone()
        if row is None or row["revoked_at"] is not None:
            return None
        if row["rotated_at"] is not None and now - row["rotated_at"] > settings.refresh_reuse_grace_seconds:
            db.execute(
                "UPDATE refresh_tokens SET revoked_at = ? WHERE family_id = ? AND revoked_at IS NULL",
                (now, row["family_id"]),
            )
            return None
        if row["rotated_at"] is None:
            db.execute("UPDATE refresh_tokens SET rotated_at = ? WHERE jti = ?", (now, row["jti"]))
    return row["user_id"], issue_refresh_token(settings, row["user_id"], row["family_id"])


def revoke_refresh_token(settings: Settings, token: str) -> None:
    claims = decode_token(settings, token, "refresh")
    if claims is None or "fam" not in claims:
        return
    with connect(settings.auth_db_path) as db:
        db.execute(
            "UPDATE refresh_tokens SET revoked_at = ? WHERE family_id = ? AND revoked_at IS NULL",
            (int(time.time()), claims["fam"]),
        )
