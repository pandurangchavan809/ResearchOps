import sqlite3
from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Response, status

from app.config import Settings
from app.dependencies import CurrentUser, SettingsDep
from app.schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.security import create_access_token
from app.services import users

router = APIRouter(prefix="/api/auth", tags=["auth"])

REFRESH_COOKIE = "researchops_refresh"
COOKIE_PATH = "/api/auth"


def _session_response(settings: Settings, response: Response, user: sqlite3.Row, refresh_token: str) -> TokenResponse:
    # The refresh token stays in an HttpOnly cookie, out of reach of page scripts.
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=settings.refresh_token_days * 86_400,
        path=COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return TokenResponse(
        access_token=create_access_token(settings, user["id"]),
        expires_in=settings.access_token_minutes * 60,
        user=users.to_user_out(settings, user),
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, settings: SettingsDep, response: Response) -> TokenResponse:
    try:
        user = users.create_user(settings, body.email, body.new_password)
    except users.EmailTaken as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.") from exc
    return _session_response(settings, response, user, users.issue_refresh_token(settings, user["id"]))


@router.post("/login")
def login(body: LoginRequest, settings: SettingsDep, response: Response) -> TokenResponse:
    try:
        user = users.authenticate(settings, body.email, body.password)
    except users.AccountLocked as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed attempts. Please try again later."
        ) from exc
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    return _session_response(settings, response, user, users.issue_refresh_token(settings, user["id"]))


@router.post("/refresh")
def refresh(
    settings: SettingsDep,
    response: Response,
    token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> TokenResponse:
    rotated = users.rotate_refresh_token(settings, token) if token else None
    user = users.get_user(settings, rotated[0]) if rotated else None
    if user is None:
        response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please log in.")
    return _session_response(settings, response, user, rotated[1])


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    settings: SettingsDep,
    response: Response,
    token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> None:
    if token:
        users.revoke_refresh_token(settings, token)
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)


@router.get("/me")
def me(settings: SettingsDep, user: CurrentUser) -> UserOut:
    return users.to_user_out(settings, user)
