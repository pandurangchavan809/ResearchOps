"""Research run persistence in research.db."""

import json
import sqlite3
import time
import uuid
from pathlib import Path

from app.config import Settings
from app.db import connect
from app.schemas import ReportInfo, RunDetail, RunSummary
from app.services.users import refund_credits

RUNNING = "running"
COMPLETED = "completed"
REJECTED = "rejected"
FAILED = "failed"
INSUFFICIENT = "insufficient_evidence"


def create_run(settings: Settings, user_id: str, question: str, model: str, credits: int) -> str:
    run_id = uuid.uuid4().hex
    now = int(time.time())
    with connect(settings.research_db_path) as db:
        db.execute(
            "INSERT INTO runs (id, user_id, question, title, model, status, credits_charged, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, user_id, question, question[:90], model, RUNNING, credits, now, now),
        )
    return run_id


def has_active_run(settings: Settings, user_id: str) -> bool:
    cutoff = int(time.time()) - settings.max_runtime_seconds - 30
    with connect(settings.research_db_path) as db:
        row = db.execute(
            "SELECT 1 FROM runs WHERE user_id = ? AND status = ? AND created_at > ? LIMIT 1", (user_id, RUNNING, cutoff)
        ).fetchone()
    return row is not None


def finish_run(
    settings: Settings,
    run_id: str,
    user_id: str,
    status: str,
    *,
    title: str | None = None,
    result: dict | None = None,
    source_texts: dict[int, str] | None = None,
    error: str | None = None,
    refund: bool = False,
) -> None:
    """Record the outcome once. Only the first finish takes effect, so a credit cannot be refunded twice."""
    with connect(settings.research_db_path) as db:
        row = db.execute("SELECT status, credits_charged FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None or row["status"] != RUNNING:
            return
        db.execute(
            "UPDATE runs SET status = ?, title = COALESCE(?, title), result_json = ?, source_texts_json = ?, error = ?, "
            "credits_charged = ?, updated_at = ? WHERE id = ?",
            (
                status,
                title,
                json.dumps(result, ensure_ascii=False) if result else None,
                json.dumps(source_texts, ensure_ascii=False) if source_texts else None,
                error,
                0 if refund else row["credits_charged"],
                int(time.time()),
                run_id,
            ),
        )
    if refund and row["credits_charged"]:
        refund_credits(settings, user_id, row["credits_charged"])


def recover_interrupted(settings: Settings) -> None:
    """After a restart, fail runs that outlived the runtime ceiling and return their credits."""
    cutoff = int(time.time()) - settings.max_runtime_seconds - 30
    with connect(settings.research_db_path) as db:
        stale = db.execute("SELECT id, user_id FROM runs WHERE status = ? AND created_at < ?", (RUNNING, cutoff)).fetchall()
        db.execute("UPDATE runs SET report_status = 'none' WHERE report_status = 'generating' AND report_path IS NULL")
        db.execute("UPDATE runs SET report_status = 'ready' WHERE report_status = 'generating'")
    for row in stale:
        finish_run(settings, row["id"], row["user_id"], FAILED, error="The research was interrupted.", refund=True)


def get_run_row(settings: Settings, run_id: str, user_id: str) -> sqlite3.Row | None:
    """Scoped by owner, so one user can never read another's run."""
    with connect(settings.research_db_path) as db:
        return db.execute("SELECT * FROM runs WHERE id = ? AND user_id = ?", (run_id, user_id)).fetchone()


def list_runs(settings: Settings, user_id: str, limit: int = 100) -> list[RunSummary]:
    with connect(settings.research_db_path) as db:
        rows = db.execute(
            "SELECT id, title, status, created_at FROM runs WHERE user_id = ? AND status != ? "
            "ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (user_id, RUNNING, limit),
        ).fetchall()
    return [RunSummary(**dict(row)) for row in rows]


def report_info(settings: Settings, row: sqlite3.Row) -> ReportInfo:
    return ReportInfo(
        status=row["report_status"],
        title=row["report_title"],
        pages=row["report_pages"],
        requested_pages=row["report_requested_pages"],
        generations=row["report_count"],
        generations_limit=settings.max_reports_per_run,
    )


def to_detail(settings: Settings, row: sqlite3.Row) -> RunDetail:
    return RunDetail(
        id=row["id"],
        title=row["title"],
        status=row["status"],
        created_at=row["created_at"],
        question=row["question"],
        error=row["error"],
        result=json.loads(row["result_json"]) if row["result_json"] else None,
        report=report_info(settings, row),
    )


def claim_report(settings: Settings, run_id: str, user_id: str) -> bool:
    """Atomically mark report generation started, which rejects double clicks and exhausted limits."""
    with connect(settings.research_db_path) as db:
        cursor = db.execute(
            "UPDATE runs SET report_status = 'generating' WHERE id = ? AND user_id = ? "
            "AND report_status != 'generating' AND report_count < ?",
            (run_id, user_id, settings.max_reports_per_run),
        )
        return cursor.rowcount == 1


def finish_report(settings: Settings, run_id: str, title: str, path: str, pages: int, requested_pages: int) -> None:
    with connect(settings.research_db_path) as db:
        db.execute(
            "UPDATE runs SET report_status = 'ready', report_title = ?, report_path = ?, report_pages = ?, "
            "report_requested_pages = ?, report_count = report_count + 1 WHERE id = ?",
            (title, path, pages, requested_pages, run_id),
        )


def source_texts(row: sqlite3.Row) -> dict[int, str]:
    """Page text saved with the run. Empty for runs made before this was stored."""
    raw = json.loads(row["source_texts_json"]) if row["source_texts_json"] else {}
    return {int(source_id): text for source_id, text in raw.items()}


def fail_report(settings: Settings, run_id: str) -> None:
    """A failed attempt keeps any earlier report available for download."""
    with connect(settings.research_db_path) as db:
        db.execute(
            "UPDATE runs SET report_status = CASE WHEN report_path IS NULL THEN 'failed' ELSE 'ready' END WHERE id = ?",
            (run_id,),
        )


def _is_busy(row: sqlite3.Row) -> bool:
    return row["status"] == RUNNING or row["report_status"] == "generating"


def _remove_report_file(path: str | None) -> None:
    if path:
        Path(path).unlink(missing_ok=True)


def delete_run(settings: Settings, run_id: str, user_id: str) -> bool:
    """Delete one finished run and its PDF. Returns False while work on it is still in progress."""
    with connect(settings.research_db_path) as db:
        row = db.execute("SELECT * FROM runs WHERE id = ? AND user_id = ?", (run_id, user_id)).fetchone()
        if row is None or _is_busy(row):
            return False
        db.execute("DELETE FROM runs WHERE id = ?", (run_id,))
    _remove_report_file(row["report_path"])
    return True


def delete_all_runs(settings: Settings, user_id: str) -> int:
    """Delete this user's finished runs and PDFs, leaving anything still in progress. Returns the count."""
    with connect(settings.research_db_path) as db:
        rows = db.execute(
            "SELECT id, report_path FROM runs WHERE user_id = ? AND status != ? AND report_status != 'generating'",
            (user_id, RUNNING),
        ).fetchall()
        db.executemany("DELETE FROM runs WHERE id = ?", [(row["id"],) for row in rows])
    for row in rows:
        _remove_report_file(row["report_path"])
    return len(rows)
