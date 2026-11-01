import os
import tempfile
from pathlib import Path

# Set before the app is imported, so tests never touch the real .env values or databases.
_data = Path(tempfile.mkdtemp(prefix="researchops-tests-"))
os.environ.update(
    {
        "RESEARCHOPS_JWT_SECRET": "test-secret-" + "x" * 40,
        "RESEARCHOPS_AUTH_DB_PATH": str(_data / "auth.db"),
        "RESEARCHOPS_RESEARCH_DB_PATH": str(_data / "research.db"),
        "RESEARCHOPS_REPORT_DIR": str(_data / "reports"),
        "RESEARCHOPS_USER_CREDITS": "5",
        "RESEARCHOPS_RESEARCH_CREDIT_COST": "1",
        "RESEARCHOPS_MAX_REPORTS_PER_RUN": "3",
        "RESEARCHOPS_PRIMARY_MODEL": "openai:primary",
        "RESEARCHOPS_FALLBACK_MODELS": "gemini:fallback",
        "RESEARCHOPS_EXTRA_MODELS": "nebius:extra",
        "RESEARCHOPS_LOGIN_MAX_FAILURES": "3",
        "RESEARCHOPS_COOKIE_SECURE": "false",
        "RESEARCHOPS_ENVIRONMENT": "development",
        "OPENAI_API_KEY": "test",
        "GEMINI_API_KEY": "test",
        "NEBIUS_API_KEY": "",
        "TAVILY_API_KEY": "test",
        "LANGSMITH_API_KEY": "",
        "RESEARCHOPS_LANGSMITH_TRACING": "false",
    }
)

import uuid  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def user(client):
    """A registered, logged-in user. Returns (email, auth headers)."""
    email = f"{uuid.uuid4().hex[:10]}@example.com"
    response = client.post(
        "/api/auth/register",
        json={"email": email, "new_password": "Passw0rd123", "confirm_password": "Passw0rd123"},
    )
    assert response.status_code == 201
    return email, {"Authorization": f"Bearer {response.json()['access_token']}"}
