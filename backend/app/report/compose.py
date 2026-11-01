"""Turns a saved research result into validated report content that fits a requested page count."""

import asyncio
import json
import math
import re

from app.guardrails import cited_ids, clean_title, numbers_in, rewrite_citations
from app.report.models import (
    ChartDraft,
    ReportDraft,
    ReportExpansion,
    ReportSource,
    ReportSpec,
    SectionDraft,
    TableDraft,
)
from app.report.render import render_report
from app.services.llm import AllModelsFailed, LLMRouter, TokenBudgetExceeded
from app.workflow.models import ResearchResult
from app.workflow.prompts import REPORT_EXPAND_SYSTEM, REPORT_SYSTEM

# These caps guarantee every table row and text block fits on one page, so layout can never fail.
MAX_CELL_CHARS = 280
MAX_COLUMNS = 6
MAX_ROWS = 25
MAX_PARAGRAPH_CHARS = 1_400
MAX_FINDINGS = 8
MAX_TABLES = 4
MAX_CHARTS = 4
MAX_SERIES = 3
MAX_CHART_POINTS = 14
MAX_LABEL_CHARS = 80

# Roughly what one page of this template holds, used only to brief the model.
# fit_to_pages measures the real rendered result.
WORDS_PER_PAGE = 480
FRONT_MATTER_WORDS = 300
WORDS_PER_SOURCE = 30
WORDS_PER_SECTION = 220
# Models cap their output (Nemotron at 8,192 tokens), so long reports are written in steps.
DRAFT_MAX_WORDS = 1_500
EXPANSION_MAX_WORDS = 2_500
MAX_EXPANSION_ROUNDS = 10
MAX_TRIM_PASSES = 60
EVIDENCE_TABLE_TITLE = "Supporting Evidence from Sources"


class ReportContentError(Exception):
    pass


def _clip(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def _clean_paragraphs(paragraphs: list[str], valid: dict[int, int]) -> list[str]:
    cleaned = (_clip(rewrite_citations(p, valid), MAX_PARAGRAPH_CHARS) for p in paragraphs)
    return [p for p in cleaned if p]


def _clean_table(table: TableDraft, valid: dict[int, int]) -> TableDraft | None:
    headers = [_clip(h, 60) for h in table.headers][:MAX_COLUMNS]
    if len(headers) < 2 or not all(headers):
        return None
    rows = []
    for row in table.rows[:MAX_ROWS]:
        cells = [_clip(rewrite_citations(cell, valid), MAX_CELL_CHARS) for cell in row][: len(headers)]
        cells += [""] * (len(headers) - len(cells))
        if any(cells):
            rows.append(cells)
    return TableDraft(title=_clip(table.title, 120), headers=headers, rows=rows) if rows else None


def clean_chart(chart: ChartDraft, result: ResearchResult, source_texts: dict[int, str]) -> ChartDraft | None:
    """Keep a chart only if it is well formed and every value appears in the sources it cites."""
    by_id = {source.id: source for source in result.sources}
    cited = [by_id[i] for i in chart.source_ids if i in by_id]
    texts = [excerpt for source in cited for excerpt in source.excerpts]
    texts += [source_texts[source.id] for source in cited if source.id in source_texts]
    known = numbers_in(texts)
    labels = [_clip(label, MAX_LABEL_CHARS) for label in chart.labels]
    series = chart.series[:MAX_SERIES]
    if not cited or not 2 <= len(labels) <= MAX_CHART_POINTS or not series:
        return None
    for item in series:
        if len(item.values) != len(labels):
            return None
        if not all(math.isfinite(v) and abs(v) in known for v in item.values):
            return None
    return chart.model_copy(
        update={
            "title": _clip(chart.title, 120),
            "unit": _clip(chart.unit, 24),
            "labels": labels,
            "series": series,
            "source_ids": [source.id for source in cited],
        }
    )


def _clean_sections(sections: list[SectionDraft], valid: dict[int, int]) -> list[SectionDraft]:
    return [
        SectionDraft(heading=_clip(section.heading, 100), paragraphs=paragraphs)
        for section in sections
        if (paragraphs := _clean_paragraphs(section.paragraphs, valid)) and section.heading.strip()
    ]


def validate_draft(
    draft: ReportDraft, result: ResearchResult, question: str, source_texts: dict[int, str] | None = None
) -> ReportSpec:
    source_texts = source_texts or {}
    valid = {source.id: source.id for source in result.sources}
    summary = _clean_paragraphs(draft.executive_summary, valid)
    if not summary:
        raise ReportContentError("The report has no executive summary")
    return ReportSpec(
        title=clean_title(draft.title, result.title or question),
        question=_clip(question, 400),
        executive_summary=summary,
        key_findings=_clean_paragraphs(draft.key_findings, valid)[:MAX_FINDINGS],
        tables=[t for t in (_clean_table(t, valid) for t in draft.comparison_tables[:MAX_TABLES]) if t],
        charts=[c for c in (clean_chart(c, result, source_texts) for c in draft.charts[:MAX_CHARTS]) if c],
        sections=_clean_sections(draft.analysis_sections, valid),
        recommendation=_clean_paragraphs(draft.recommendation, valid),
        sources=[
            ReportSource(id=s.id, title=_clip(s.title, 200), url=s.url, domain=s.domain, published_date=s.published_date)
            for s in result.sources
        ],
    )


def _trim_once(spec: ReportSpec) -> bool:
    """Remove the least essential remaining content. Returns False when nothing more can go."""
    longest = max(spec.sections, key=lambda s: len(s.paragraphs), default=None)
    if longest and len(longest.paragraphs) > 1:
        longest.paragraphs.pop()
        return True
    if spec.tables and max(len(t.rows) for t in spec.tables) > 6:
        max(spec.tables, key=lambda t: len(t.rows)).rows.pop()
        return True
    if spec.charts:
        spec.charts.pop()
        return True
    if len(spec.sections) > 1:
        spec.sections.pop()
        return True
    if len(spec.tables) > 1:
        spec.tables.pop()
        return True
    if spec.sections:
        spec.sections.pop()
        return True
    if spec.tables:
        spec.tables.pop()
        return True
    if len(spec.key_findings) > 3:
        spec.key_findings.pop()
        return True
    for paragraphs in (spec.executive_summary, spec.recommendation):
        if len(paragraphs) > 1:
            paragraphs.pop()
            return True
    return False


def _without_uncited_sources(spec: ReportSpec) -> ReportSpec:
    """List only the sources this version of the report actually cites."""
    text = " ".join(
        [
            *spec.executive_summary,
            *spec.key_findings,
            *spec.recommendation,
            *(p for section in spec.sections for p in section.paragraphs),
            *(cell for table in spec.tables for row in table.rows for cell in row),
        ]
    )
    used = set(cited_ids(text)) | {i for chart in spec.charts for i in chart.source_ids}
    return spec.model_copy(update={"sources": [s for s in spec.sources if s.id in used] or spec.sources})


def fit_to_pages(spec: ReportSpec, pages: int) -> tuple[ReportSpec, bytes, int]:
    """Render, trimming content until the report is no longer than the requested page count."""
    spec = spec.model_copy(deep=True)
    for _ in range(MAX_TRIM_PASSES):
        fitted = _without_uncited_sources(spec)
        pdf, count = render_report(fitted)
        if count <= pages:
            return fitted, pdf, count
        # Take more per pass when far over, which keeps long reports quick to fit.
        for _ in range((count - pages) * 3):
            if not _trim_once(spec):
                return fitted, pdf, count
    return fitted, pdf, count


def _evidence_table(result: ResearchResult) -> TableDraft | None:
    """Verbatim excerpts: real content that may lengthen a short report without inventing anything."""
    rows = [
        [f"[{source.id}] {source.domain}", _clip(excerpt, MAX_CELL_CHARS)]
        for source in result.sources
        for excerpt in source.excerpts
    ]
    return TableDraft(title=EVIDENCE_TABLE_TITLE, headers=["Source", "Excerpt"], rows=rows[:MAX_ROWS]) if rows else None


def _material(result: ResearchResult, question: str, source_texts: dict[int, str]) -> dict:
    return {
        "question": question,
        "working_title": result.title,
        "answer": result.answer_markdown,
        "claims": [claim.model_dump() for claim in result.claims],
        "limitations": result.limitations,
        "sources": [{**source.model_dump(), "page_text": source_texts.get(source.id, "")} for source in result.sources],
    }


async def compose_report(
    llm: LLMRouter, result: ResearchResult, question: str, pages: int, source_texts: dict[int, str] | None = None
) -> tuple[ReportSpec, bytes, int]:
    """Write the report and fit it to the page count, measuring real rendered pages rather than estimating."""
    source_texts = source_texts or {}
    material = json.dumps(_material(result, question, source_texts), ensure_ascii=False)
    question = result.research_question or question
    words = min(
        max(pages * WORDS_PER_PAGE - FRONT_MATTER_WORDS - len(result.sources) * WORDS_PER_SOURCE, 100), DRAFT_MAX_WORDS
    )
    system = REPORT_SYSTEM.format(pages=pages, words=words, sections=max(words // WORDS_PER_SECTION, 2))
    draft = await llm.structured(ReportDraft, system, material)
    spec = validate_draft(draft, result, question, source_texts)
    fitted, pdf, count = await asyncio.to_thread(fit_to_pages, spec, pages)

    valid = {source.id: source.id for source in result.sources}
    for _ in range(MAX_EXPANSION_ROUNDS):
        if count >= pages:
            break
        missing = min((pages - count) * WORDS_PER_PAGE, EXPANSION_MAX_WORDS)
        headings = [section.heading for section in spec.sections]
        try:
            extra = await llm.structured(
                ReportExpansion,
                REPORT_EXPAND_SYSTEM.format(words=missing),
                f"Existing headings: {json.dumps(headings, ensure_ascii=False)}\n\n{material}",
            )
        except (AllModelsFailed, TokenBudgetExceeded):
            break  # The report so far is still valid; the page count is reported honestly.
        sections = _clean_sections(extra.sections, valid)
        if not sections:
            break
        spec.sections += sections
        fitted, pdf, count = await asyncio.to_thread(fit_to_pages, spec, pages)

    if count < pages and (table := _evidence_table(result)):
        spec.tables.append(table)
        longer, longer_pdf, longer_count = await asyncio.to_thread(fit_to_pages, spec, pages)
        # Trimming may undo the gain, so only keep this version if it really is closer to the target.
        if longer_count > count:
            fitted, pdf, count = longer, longer_pdf, longer_count
    return fitted, pdf, count
