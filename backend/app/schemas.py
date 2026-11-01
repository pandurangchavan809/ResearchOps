"""Validated API boundaries."""

import re

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.config import get_settings


class RegisterRequest(BaseModel):
    email: EmailStr
    new_password: str = Field(max_length=128)
    confirm_password: str = Field(max_length=128)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("new_password")
    @classmethod
    def _password_policy(cls, value: str) -> str:
        minimum = get_settings().password_min_length
        if len(value) < minimum:
            raise ValueError(f"Password must be at least {minimum} characters.")
        if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
            raise ValueError("Password must contain a letter and a number.")
        return value

    @model_validator(mode="after")
    def _passwords_match(self) -> "RegisterRequest":
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class Credits(BaseModel):
    limit: int
    used: int
    remaining: int


class UserOut(BaseModel):
    id: str
    email: str
    credits: Credits


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class ModelInfo(BaseModel):
    id: str
    label: str
    name: str
    provider: str
    provider_label: str
    role: str


class ConfigResponse(BaseModel):
    models: list[ModelInfo]
    auto_chain: list[str]
    search_configured: bool
    max_question_chars: int
    max_reports_per_run: int
    default_report_pages: int
    max_report_pages: int


class ResearchRequest(BaseModel):
    question: str = Field(min_length=1)
    model: str = "auto"

    @field_validator("question")
    @classmethod
    def _question_limits(cls, value: str) -> str:
        value = value.strip()
        maximum = get_settings().max_question_chars
        if len(value) < 10:
            raise ValueError("Please ask a complete research question.")
        if len(value) > maximum:
            raise ValueError(f"Questions are limited to {maximum} characters.")
        return value


class ReportRequest(BaseModel):
    pages: int | None = Field(default=None, ge=1)


class ReportInfo(BaseModel):
    status: str
    title: str | None = None
    pages: int | None = None
    requested_pages: int | None = None
    generations: int = 0
    generations_limit: int


class RunSummary(BaseModel):
    id: str
    title: str
    status: str
    created_at: int


class RunDetail(RunSummary):
    question: str
    error: str | None = None
    result: dict | None = None
    report: ReportInfo
