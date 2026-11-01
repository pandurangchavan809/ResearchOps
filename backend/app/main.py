import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import PROJECT_ROOT, Settings, get_settings
from app.db import init_databases
from app.dependencies import CurrentUser, SettingsDep
from app.routers import auth, research
from app.schemas import ConfigResponse
from app.services import llm, runs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

settings = get_settings()


def _configure_tracing(config: Settings) -> None:
    """LangSmith reads the process environment, while .env values only reach Settings."""
    if config.langsmith_tracing and config.langsmith_api_key:
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_API_KEY"] = config.langsmith_api_key.get_secret_value()
        os.environ["LANGSMITH_PROJECT"] = config.langsmith_project


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_databases(settings)
    runs.recover_interrupted(settings)
    _configure_tracing(settings)
    yield


app = FastAPI(
    title="ResearchOps API",
    description="Evidence-grounded technical research agent",
    version="1.0.0",
    lifespan=lifespan,
)
app.state.settings = settings
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Give the UI one readable sentence rather than a nested error structure."""
    message = exc.errors()[0]["msg"].removeprefix("Value error, ") if exc.errors() else "Invalid request."
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={"detail": message})


app.include_router(auth.router)
app.include_router(research.router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config", tags=["system"])
def config(config_settings: SettingsDep, _: CurrentUser) -> ConfigResponse:
    """Only models with a configured key are listed, so the UI never offers one that cannot run."""
    return ConfigResponse(
        models=[llm.to_model_info(spec) for spec in llm.available_models(config_settings)],
        auto_chain=[spec.id for spec in llm.auto_chain(config_settings)],
        search_configured=config_settings.tavily_api_key is not None,
        max_question_chars=config_settings.max_question_chars,
        max_reports_per_run=config_settings.max_reports_per_run,
        default_report_pages=config_settings.default_report_pages,
        max_report_pages=config_settings.max_report_pages,
    )


# In production the API also serves the built frontend, keeping the auth cookie same-origin.
_frontend = PROJECT_ROOT / "frontend" / "dist"
if _frontend.is_dir():
    app.mount("/", StaticFiles(directory=_frontend, html=True), name="frontend")
