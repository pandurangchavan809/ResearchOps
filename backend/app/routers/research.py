import asyncio
import json
import logging
import re
import sqlite3
from collections.abc import AsyncIterator
from contextlib import aclosing

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse

from app.config import Settings
from app.dependencies import CurrentUser, SettingsDep
from app.guardrails import is_prompt_attack, requested_report
from app.report.compose import ReportContentError, compose_report
from app.schemas import ReportInfo, ReportRequest, ResearchRequest, RunDetail, RunSummary
from app.services import llm as llm_service
from app.services import runs, users
from app.services.web import SearchUnavailable, WebClient
from app.workflow.models import ResearchResult
from app.workflow.runner import ResearchTimeout, run_workflow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/research", tags=["research"])


def get_web_client(settings: SettingsDep) -> WebClient:
    return WebClient(settings)


def get_model_factory():
    return llm_service.build_chat_model


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _failure_message(exc: Exception) -> str:
    """Messages safe to show users. Internal details stay in the logs."""
    if isinstance(exc, ResearchTimeout):
        return "The research hit its time limit. Your credit was returned. Try a narrower question."
    if isinstance(exc, llm_service.TokenBudgetExceeded):
        return "The research hit its token budget. Your credit was returned. Try a narrower question."
    if isinstance(exc, llm_service.AllModelsFailed):
        return "All configured models are unavailable right now. Your credit was returned."
    if isinstance(exc, SearchUnavailable):
        return "Web search is unavailable right now. Your credit was returned."
    return "The research failed unexpectedly. Your credit was returned."


def _resolve_pages(settings: Settings, pages: int | None) -> int:
    return min(pages or settings.default_report_pages, settings.max_report_pages)


async def _research_events(
    settings: Settings,
    router_llm: llm_service.LLMRouter,
    web: WebClient,
    user_id: str,
    run_id: str,
    question: str,
) -> AsyncIterator[str]:
    def credits() -> dict:
        return users.to_user_out(settings, users.get_user(settings, user_id)).credits.model_dump()

    steps: list[dict] = []
    finished = False
    try:
        yield _sse("started", {"run_id": run_id, "credits": credits()})
        final: dict = {}
        # aclosing cancels the workflow as soon as the client goes away, so it stops spending tokens.
        async with aclosing(run_workflow(settings, router_llm, web, question)) as stream:
            async for event in stream:
                if "final" in event:
                    final = event["final"]
                    continue
                if event["status"] == "done":
                    steps.append(event)
                yield _sse("step", event)

        status_value = final.get("status")
        if status_value == "completed":
            result = {**final["result"], "steps": steps}
            # Tokens were counted after the result was assembled; report the true final figure.
            result["stats"]["tokens_used"] = router_llm.tokens_used
            result["models_used"] = router_llm.models_used
            runs.finish_run(
                settings, run_id, user_id, runs.COMPLETED,
                title=result["title"], result=result, source_texts=final.get("source_texts"),
            )
            finished = True
            wants_report, pages = requested_report(question)
            yield _sse(
                "result",
                {
                    "run_id": run_id,
                    "title": result["title"],
                    "result": result,
                    "credits": credits(),
                    "report_request": {"pages": _resolve_pages(settings, pages)} if wants_report else None,
                },
            )
        elif status_value == "rejected":
            message = final.get("rejection_reason") or "This question is outside the scope of technical research."
            runs.finish_run(settings, run_id, user_id, runs.REJECTED, error=message, refund=True)
            finished = True
            yield _sse("rejected", {"run_id": run_id, "message": message, "credits": credits()})
        else:
            message = "No reliable evidence was found for this question, so no answer was written. Your credit was returned."
            runs.finish_run(settings, run_id, user_id, runs.INSUFFICIENT, error=message, refund=True)
            finished = True
            yield _sse("rejected", {"run_id": run_id, "message": message, "credits": credits()})
    except Exception as exc:
        logger.exception("Research run %s failed", run_id)
        message = _failure_message(exc)
        runs.finish_run(settings, run_id, user_id, runs.FAILED, error=message, refund=True)
        finished = True
        yield _sse("error", {"run_id": run_id, "message": message, "credits": credits()})
    finally:
        # Reached without an outcome only if the client stopped or disconnected.
        if not finished:
            runs.finish_run(settings, run_id, user_id, runs.FAILED, error="Stopped before completion.", refund=True)


@router.post("")
async def start_research(
    body: ResearchRequest,
    settings: SettingsDep,
    user: CurrentUser,
    web: WebClient = Depends(get_web_client),
    model_factory=Depends(get_model_factory),
) -> StreamingResponse:
    """Stream real workflow progress as Server-Sent Events. All refusals happen before a credit is spent."""
    if is_prompt_attack(body.question):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Please ask a technical research question.")
    if settings.tavily_api_key is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Web search is not configured on this server.")
    available = llm_service.available_models(settings)
    if not llm_service.auto_chain(settings) and not available:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No AI model is configured on this server.")
    if body.model != llm_service.AUTO and body.model not in {spec.id for spec in available}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That model is not available.")
    if runs.has_active_run(settings, user["id"]):
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have research in progress.")
    cost = settings.research_credit_cost
    if not users.consume_credits(settings, user["id"], cost):
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "You have used all your research credits.")

    run_id = runs.create_run(settings, user["id"], body.question, body.model, cost)
    router_llm = llm_service.LLMRouter(
        settings,
        llm_service.resolve_chain(settings, body.model),
        settings.max_token_budget,
        model_factory,
    )
    return StreamingResponse(
        _research_events(settings, router_llm, web, user["id"], run_id, body.question),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get("")
def list_research(settings: SettingsDep, user: CurrentUser) -> list[RunSummary]:
    return runs.list_runs(settings, user["id"])


def _owned_run(settings: Settings, run_id: str, user_id: str) -> sqlite3.Row:
    row = runs.get_run_row(settings, run_id, user_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Research not found.")
    return row


@router.get("/{run_id}")
def get_research(run_id: str, settings: SettingsDep, user: CurrentUser) -> RunDetail:
    return runs.to_detail(settings, _owned_run(settings, run_id, user["id"]))


@router.post("/{run_id}/report")
async def generate_report(
    run_id: str,
    settings: SettingsDep,
    user: CurrentUser,
    body: ReportRequest | None = None,
    model_factory=Depends(get_model_factory),
) -> ReportInfo:
    """Create the PDF on explicit request. Calling again regenerates it with a fresh title and content."""
    row = _owned_run(settings, run_id, user["id"])
    requested = body.pages if body else None
    if requested is not None and requested > settings.max_report_pages:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Reports are limited to {settings.max_report_pages} pages."
        )
    pages = _resolve_pages(settings, requested)
    if row["status"] != runs.COMPLETED:
        raise HTTPException(status.HTTP_409_CONFLICT, "A report needs a completed research answer.")
    if not llm_service.auto_chain(settings) and not llm_service.available_models(settings):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No AI model is configured on this server.")
    if not runs.claim_report(settings, run_id, user["id"]):
        if row["report_count"] >= settings.max_reports_per_run:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "This research has reached its report limit.")
        raise HTTPException(status.HTTP_409_CONFLICT, "This report is already being generated.")

    try:
        model = row["model"] if row["model"] in {s.id for s in llm_service.available_models(settings)} else llm_service.AUTO
        report_settings = settings.model_copy(update={"llm_timeout_seconds": settings.report_llm_timeout_seconds})
        router_llm = llm_service.LLMRouter(
            report_settings, llm_service.resolve_chain(settings, model), settings.report_token_budget, model_factory
        )
        result = ResearchResult.model_validate_json(row["result_json"])
        spec, pdf, page_count = await asyncio.wait_for(
            compose_report(router_llm, result, row["question"], pages, runs.source_texts(row)),
            timeout=settings.report_max_runtime_seconds,
        )
        path = settings.report_dir / f"{run_id}.pdf"
        temporary = path.with_suffix(".tmp")
        await asyncio.to_thread(temporary.write_bytes, pdf)
        temporary.replace(path)
    except BaseException as exc:
        runs.fail_report(settings, run_id)
        if not isinstance(exc, Exception):
            raise
        logger.exception("Report generation failed for run %s", run_id)
        detail = (
            "The model returned an incomplete report. Please try again."
            if isinstance(exc, ReportContentError)
            else "The report could not be generated. Please try again."
        )
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail) from exc

    runs.finish_report(settings, run_id, spec.title, str(path), page_count, pages)
    return runs.report_info(settings, _owned_run(settings, run_id, user["id"]))


@router.get("/{run_id}/report/download")
def download_report(run_id: str, settings: SettingsDep, user: CurrentUser) -> FileResponse:
    row = _owned_run(settings, run_id, user["id"])
    if not row["report_path"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No report has been generated yet.")
    slug = re.sub(r"[^a-z0-9]+", "-", (row["report_title"] or "report").lower()).strip("-")[:80]
    return FileResponse(row["report_path"], media_type="application/pdf", filename=f"{slug or 'report'}.pdf")
