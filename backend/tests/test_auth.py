import time

import jwt

from app.config import get_settings
from app.db import connect
from app.routers.auth import REFRESH_COOKIE

PASSWORD = "Passw0rd123"


def register(client, email, new=PASSWORD, confirm=PASSWORD):
    return client.post("/api/auth/register", json={"email": email, "new_password": new, "confirm_password": confirm})


def set_refresh_cookie(client, value):
    client.cookies.clear()
    client.cookies.set(REFRESH_COOKIE, value, path="/api/auth")


def refresh_cookie(response):
    return response.cookies.get(REFRESH_COOKIE)


def test_register_gives_configured_credits_and_session(client):
    response = register(client, "new.user@example.com")
    assert response.status_code == 201
    assert response.json()["user"]["credits"] == {"limit": 5, "used": 0, "remaining": 5}
    cookie = response.headers["set-cookie"]
    assert REFRESH_COOKIE in cookie and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()


def test_register_requires_matching_passwords(client):
    response = register(client, "mismatch@example.com", confirm="Different123")
    assert response.status_code == 422
    assert response.json()["detail"] == "Passwords do not match."


def test_register_enforces_password_policy(client):
    assert register(client, "short@example.com", "a1", "a1").status_code == 422
    assert register(client, "noletter@example.com", "12345678", "12345678").status_code == 422


def test_duplicate_email_is_rejected_case_insensitively(client):
    assert register(client, "dup@example.com").status_code == 201
    assert register(client, "DUP@example.com").status_code == 409


def test_login_and_me(client, user):
    email, _ = user
    response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {response.json()['access_token']}"})
    assert me.json()["email"] == email


def test_wrong_password_and_unknown_email_look_identical(client, user):
    email, _ = user
    wrong = client.post("/api/auth/login", json={"email": email, "password": "Wrong12345"})
    unknown = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "Wrong12345"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_repeated_failures_lock_the_account(client, user):
    email, _ = user
    for _ in range(3):
        assert client.post("/api/auth/login", json={"email": email, "password": "Wrong12345"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code == 429


def test_protected_routes_reject_bad_tokens(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_refresh_token_cannot_be_used_as_access_token(client):
    token = refresh_cookie(register(client, "wrongtype@example.com"))
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_expired_access_token_is_rejected(client):
    secret = get_settings().jwt_secret.get_secret_value()
    now = int(time.time())
    token = jwt.encode(
        {"sub": "x", "type": "access", "iss": "researchops", "iat": now - 100, "exp": now - 50}, secret, algorithm="HS256"
    )
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_refresh_rotates_token(client):
    old = refresh_cookie(register(client, "rotate@example.com"))
    set_refresh_cookie(client, old)
    response = client.post("/api/auth/refresh")
    assert response.status_code == 200
    assert refresh_cookie(response) != old
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {response.json()['access_token']}"})
    assert me.status_code == 200


def test_concurrent_refresh_within_grace_keeps_session(client):
    old = refresh_cookie(register(client, "grace@example.com"))
    set_refresh_cookie(client, old)
    assert client.post("/api/auth/refresh").status_code == 200
    set_refresh_cookie(client, old)
    assert client.post("/api/auth/refresh").status_code == 200


def test_replay_after_grace_revokes_whole_family(client):
    old = refresh_cookie(register(client, "replay@example.com"))
    set_refresh_cookie(client, old)
    newest = refresh_cookie(client.post("/api/auth/refresh"))
    with connect(get_settings().auth_db_path) as db:
        db.execute("UPDATE refresh_tokens SET rotated_at = rotated_at - 1000 WHERE rotated_at IS NOT NULL")
    set_refresh_cookie(client, old)
    assert client.post("/api/auth/refresh").status_code == 401
    set_refresh_cookie(client, newest)
    assert client.post("/api/auth/refresh").status_code == 401


def test_logout_revokes_refresh_token(client):
    old = refresh_cookie(register(client, "logout@example.com"))
    set_refresh_cookie(client, old)
    assert client.post("/api/auth/logout").status_code == 204
    set_refresh_cookie(client, old)
    assert client.post("/api/auth/refresh").status_code == 401
