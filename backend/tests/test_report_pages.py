"""Page-count fitting and report requests made inside a question."""

import asyncio
import sqlite3

import pytest

from app.db import init_databases
from app.config import get_settings
from app.guardrails import requested_report
from app.report.compose import compose_report, fit_to_pages
from app.report.models import ReportDraft, ReportExpansion, ReportSource, ReportSpec, SectionDraft, TableDraft
from app.workflow.models import CitedSource, ResearchResult, RunStats

PARAGRAPH = "Benchmarks show the engine sustains high throughput under load across replicas and regions [1]. " * 7


def make_spec(sections=12):
    return ReportSpec(
        title="Inference Engine Throughput Comparison",
        question="Compare engines",
        executive_summary=["The engine leads on throughput [1]."],
        key_findings=["Finding about throughput [1]."] * 5,
        tables=[TableDraft(title="Comparison", headers=["A", "B"], rows=[["x [1]", "y"]] * 10)],
        charts=[],
        sections=[SectionDraft(heading=f"Section {i}", paragraphs=[PARAGRAPH] * 4) for i in range(sections)],
        recommendation=["Benchmark it [1]."],
        sources=[
            ReportSource(id=1, title="Cited", url="https://example.com/1", domain="example.com"),
            ReportSource(id=2, title="Never cited", url="https://example.com/2", domain="example.com"),
        ],
    )


@pytest.mark.parametrize("pages", [1, 2, 3, 5])
def test_long_reports_are_fitted_to_the_exact_page_count(pages):
    spec, pdf, count = fit_to_pages(make_spec(), pages)
    assert count == pages
    assert pdf.startswith(b"%PDF")
    assert spec.executive_summary


def test_uncited_sources_are_dropped_and_input_is_not_mutated():
    original = make_spec()
    spec, _, _ = fit_to_pages(original, 2)
    assert [s.id for s in spec.sources] == [1]
    assert len(original.sections) == 12


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Generate a 3 page PDF on vLLM vs SGLang", (True, 3)),
        ("Create a detailed three-page report about Kafka", (True, 3)),
        ("write a report comparing Redis and Valkey", (True, None)),
        ("10 page pdf on vector databases", (True, 10)),
        ("Compare vLLM and SGLang for production inference", (False, None)),
        ("How do page tables and PDF rendering work in browsers?", (False, None)),
        ("What does a 4 page cache line eviction cost?", (False, None)),
    ],
)
def test_report_requests_are_read_from_the_question(question, expected):
    assert requested_report(question) == expected


class ScriptedLLM:
    """Returns a short draft, then whatever expansions the test supplies."""

    def __init__(self, expansions):
        self.expansions = list(expansions)
        self.expansion_calls = 0

    async def structured(self, schema, _system, _user):
        if schema is ReportDraft:
            return ReportDraft(
                title="Inference Engine Throughput Comparison",
                executive_summary=["Summary [1]."],
                key_findings=["Finding [1]."],
                comparison_tables=[],
                charts=[],
                analysis_sections=[SectionDraft(heading="Overview", paragraphs=[PARAGRAPH])],
                recommendation=["Test it [1]."],
            )
        self.expansion_calls += 1
        return self.expansions.pop(0) if self.expansions else ReportExpansion(sections=[])


def result_with_excerpts(excerpts=()):
    return ResearchResult(
        title="Throughput",
        answer_markdown="Answer [1].",
        claims=[],
        sources=[CitedSource(id=1, url="https://example.com", title="Source", domain="example.com", excerpts=list(excerpts))],
        limitations=[],
        models_used=[],
        stats=RunStats(searches=1, pages_fetched=1, sources_considered=1, iterations=1, tokens_used=1),
    )


def test_short_drafts_are_expanded_to_reach_the_page_count():
    extra = ReportExpansion(sections=[SectionDraft(heading=f"More {i}", paragraphs=[PARAGRAPH] * 4) for i in range(12)])
    llm = ScriptedLLM([extra])
    spec, _, count = asyncio.run(compose_report(llm, result_with_excerpts(), "Compare engines", 3))
    assert count == 3
    assert llm.expansion_calls == 1
    assert any(section.heading.startswith("More") for section in spec.sections)


def test_page_count_is_reported_honestly_when_sources_run_out():
    llm = ScriptedLLM([])
    _, _, count = asyncio.run(compose_report(llm, result_with_excerpts(), "Compare engines", 8))
    assert count < 8


def test_older_research_databases_gain_the_new_columns(tmp_path):
    settings = get_settings().model_copy(
        update={
            "auth_db_path": tmp_path / "auth.db",
            "research_db_path": tmp_path / "research.db",
            "report_dir": tmp_path / "reports",
        }
    )
    connection = sqlite3.connect(settings.research_db_path)
    connection.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, user_id TEXT, created_at INTEGER)")
    connection.commit()
    connection.close()
    init_databases(settings)
    connection = sqlite3.connect(settings.research_db_path)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(runs)")}
    connection.close()
    assert {"report_pages", "report_requested_pages", "source_texts_json"} <= columns
