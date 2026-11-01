"""The bounded LangGraph research workflow.

External actions live in WebClient and LLMRouter; nodes hold the reasoning steps and enforce limits.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypedDict
from urllib.parse import urldefrag, urlsplit

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from app.config import Settings
from app.guardrails import (
    cited_ids,
    clean_title,
    locate_excerpt,
    rewrite_citations,
    sanitize_untrusted,
    strip_sources_section,
)
from app.services.llm import LLMRouter
from app.services.web import SearchUnavailable, WebClient
from app.workflow import prompts
from app.workflow.models import (
    CitedSource,
    Evidence,
    EvidenceBatch,
    ResearchPlan,
    ResearchResult,
    RunStats,
    ScopeDecision,
    Source,
    SynthesisOutput,
    VerificationOutput,
    VerifiedClaim,
)

MAX_QUERIES_PER_ROUND = 4
FETCH_CONCURRENCY = 5
EVIDENCE_BATCH_SOURCES = 3
# Past these fractions of a limit, stop researching and write up what has been found.
TOKEN_STOP_RATIO = 0.7
RUNTIME_STOP_RATIO = 0.6

# Domains that usually publish primary technical material.
AUTHORITATIVE_HINTS = (".gov", ".edu", "arxiv.org", "acm.org", "ieee.org", "github.com", "docs.", "developer.", "developers.")


class ResearchState(TypedDict, total=False):
    question: str
    status: str
    rejection_reason: str
    pending_queries: list[str]
    searched_queries: list[str]
    sources: dict[str, dict]
    new_source_ids: list[int]
    evidence: list[dict]
    claims: list[dict]
    needs_more: bool
    follow_ups: list[str]
    iterations: int
    pages_fetched: int
    result: dict
    source_texts: dict[int, str]


@dataclass
class Context:
    settings: Settings
    llm: LLMRouter
    web: WebClient
    started_at: float


def _sources(state: ResearchState) -> list[Source]:
    return [Source(**item) for item in state.get("sources", {}).values()]


def _canonical(url: str) -> str:
    return urldefrag(url)[0].rstrip("/")


def _domain(url: str) -> str:
    return (urlsplit(url).hostname or "").removeprefix("www.")


def rank_score(source: Source) -> float:
    authority = 1.0 if any(hint in source.url for hint in AUTHORITATIVE_HINTS) else 0.4
    return round(0.7 * min(source.search_score, 1.0) + 0.3 * authority, 4)


async def scope_guard(ctx: Context, state: ResearchState) -> dict:
    decision = await ctx.llm.structured(ScopeDecision, prompts.SCOPE_SYSTEM, f"Question:\n{state['question']}")
    if not decision.in_scope:
        return {"status": "rejected", "rejection_reason": decision.reason, "_detail": "Outside research scope"}
    return {"question": decision.refined_question.strip() or state["question"], "_detail": "Question accepted"}


async def plan(ctx: Context, state: ResearchState) -> dict:
    limit = min(MAX_QUERIES_PER_ROUND, ctx.settings.max_searches)
    output = await ctx.llm.structured(
        ResearchPlan, prompts.PLAN_SYSTEM.format(limit=limit), f"Question:\n{state['question']}"
    )
    queries = list(dict.fromkeys(q.strip() for q in output.subqueries if q.strip()))[:limit] or [state["question"]]
    return {"pending_queries": queries, "_detail": f"{len(queries)} search queries"}


async def search(ctx: Context, state: ResearchState) -> dict:
    searched = state.get("searched_queries", [])
    remaining = ctx.settings.max_searches - len(searched)
    queries = [q for q in state.get("pending_queries", []) if q not in searched][: max(remaining, 0)]
    outcomes = await asyncio.gather(*(ctx.web.search(q) for q in queries), return_exceptions=True)

    sources = dict(state.get("sources", {}))
    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            continue
        for hit in outcome:
            key = _canonical(hit.url)
            if key not in sources and len(sources) < ctx.settings.max_sources:
                source = Source(
                    id=len(sources) + 1,
                    url=hit.url,
                    title=hit.title,
                    domain=_domain(hit.url),
                    published_date=hit.published_date,
                    snippet=hit.snippet,
                    search_score=hit.score,
                )
                source.rank_score = rank_score(source)
                sources[key] = source.model_dump()
    if not sources:
        raise SearchUnavailable("No search results were available")
    new = len(sources) - len(state.get("sources", {}))
    return {
        "sources": sources,
        "searched_queries": searched + queries,
        "pending_queries": [],
        "_detail": f"{len(queries)} searches, {new} new sources",
    }


async def fetch(ctx: Context, state: ResearchState) -> dict:
    """Read the highest-ranked unread sources, keeping any one domain from dominating."""
    all_sources = _sources(state)
    per_domain: dict[str, int] = {}
    for source in all_sources:
        if source.fetched:
            per_domain[source.domain] = per_domain.get(source.domain, 0) + 1

    budget = ctx.settings.max_pages - state.get("pages_fetched", 0)
    selected: list[Source] = []
    for source in sorted((s for s in all_sources if not s.fetched), key=lambda s: -s.rank_score):
        if len(selected) >= budget:
            break
        if per_domain.get(source.domain, 0) < ctx.settings.max_sources_per_domain:
            per_domain[source.domain] = per_domain.get(source.domain, 0) + 1
            selected.append(source)

    semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)

    async def read(source: Source) -> Source:
        async with semaphore:
            page = await ctx.web.fetch(source.url)
        source.fetched = True
        # An unreadable page falls back to the search snippet, which is still real source text.
        source.content = sanitize_untrusted(page.text if page else source.snippet)[: ctx.settings.max_chars_per_source]
        source.published_date = source.published_date or (page.published_date if page else None)
        return source

    done = await asyncio.gather(*(read(source) for source in selected))
    sources = dict(state["sources"])
    for source in done:
        sources[_canonical(source.url)] = source.model_dump()
    return {
        "sources": sources,
        "new_source_ids": [source.id for source in done if source.content],
        "pages_fetched": state.get("pages_fetched", 0) + len(done),
        "_detail": f"{len(done)} pages read",
    }


async def extract_evidence(ctx: Context, state: ResearchState) -> dict:
    by_id = {source.id: source for source in _sources(state)}
    new = [by_id[i] for i in state.get("new_source_ids", [])]
    evidence = list(state.get("evidence", []))
    if not new:
        return {"_detail": "No new text to analyze"}
    batches = [new[i : i + EVIDENCE_BATCH_SOURCES] for i in range(0, len(new), EVIDENCE_BATCH_SOURCES)]

    async def extract(batch: list[Source]) -> EvidenceBatch:
        blocks = "\n\n".join(f'<source id="{s.id}" title="{sanitize_untrusted(s.title)}">\n{s.content}\n</source>' for s in batch)
        return await ctx.llm.structured(
            EvidenceBatch, prompts.EVIDENCE_SYSTEM, f"Research question:\n{state['question']}\n\nSources:\n{blocks}"
        )

    outcomes = await asyncio.gather(*(extract(batch) for batch in batches), return_exceptions=True)
    drafts = [draft for outcome in outcomes if isinstance(outcome, EvidenceBatch) for draft in outcome.items]
    # One failed batch only costs its own sources. Every batch failing is a real failure.
    if not any(isinstance(outcome, EvidenceBatch) for outcome in outcomes):
        raise outcomes[0]
    added, seen = 0, {item["excerpt"] for item in evidence}
    for draft in drafts:
        source = by_id.get(draft.source_id)
        # Evidence must be a real quotation from a source this run actually read.
        excerpt = locate_excerpt(draft.excerpt, source.content) if source else None
        if excerpt and excerpt not in seen:
            seen.add(excerpt)
            item = Evidence(id=len(evidence) + 1, source_id=draft.source_id, claim=draft.claim, excerpt=excerpt)
            evidence.append(item.model_dump())
            added += 1
    return {"evidence": evidence, "_detail": f"{added} evidence excerpts verified against source text"}


def _evidence_block(state: ResearchState) -> str:
    return "\n".join(
        f'<source evidence_id="{e["id"]}" source_number="{e["source_id"]}">{e["excerpt"]}</source>'
        for e in state.get("evidence", [])
    )


async def verify(ctx: Context, state: ResearchState) -> dict:
    if not state.get("evidence"):
        return {"claims": [], "needs_more": True, "follow_ups": [], "iterations": state.get("iterations", 0) + 1,
                "_detail": "No evidence to verify yet"}
    output = await ctx.llm.structured(
        VerificationOutput, prompts.VERIFY_SYSTEM, f"Question:\n{state['question']}\n\nEvidence:\n{_evidence_block(state)}"
    )
    valid = {e["id"] for e in state["evidence"]}
    claims = []
    for claim in output.claims:
        ids = [i for i in claim.evidence_ids if i in valid]
        # A claim with no resolvable evidence cannot keep a positive status, whatever the model said.
        status = claim.status if ids else "unsupported"
        claims.append({"text": claim.text, "status": status, "rationale": claim.rationale, "evidence_ids": ids})
    supported = sum(c["status"] == "supported" for c in claims)
    return {
        "claims": claims,
        "needs_more": output.needs_more_research,
        "follow_ups": output.follow_up_queries,
        "iterations": state.get("iterations", 0) + 1,
        "_detail": f"{supported} of {len(claims)} claims fully supported",
    }


def _should_continue(ctx: Context, state: ResearchState) -> bool:
    settings = ctx.settings
    return (
        state.get("needs_more", False)
        and bool(state.get("follow_ups"))
        and state.get("iterations", 0) < settings.max_iterations
        and len(state.get("searched_queries", [])) < settings.max_searches
        and state.get("pages_fetched", 0) < settings.max_pages
        and ctx.llm.budget_used_ratio < TOKEN_STOP_RATIO
        and time.monotonic() - ctx.started_at < settings.max_runtime_seconds * RUNTIME_STOP_RATIO
    )


async def follow_up(ctx: Context, state: ResearchState) -> dict:
    queries = list(dict.fromkeys(q.strip() for q in state["follow_ups"] if q.strip()))[:MAX_QUERIES_PER_ROUND]
    return {"pending_queries": queries, "_detail": f"{len(queries)} follow-up queries for evidence gaps"}


def _build_result(ctx: Context, state: ResearchState, output: SynthesisOutput, answer: str, title: str) -> dict:
    by_id = {source.id: source for source in _sources(state)}
    evidence = {e["id"]: e for e in state["evidence"]}

    # Sources are numbered by first appearance: answer citations first, then those only claims use.
    claim_source_ids = [
        evidence[i]["source_id"] for claim in state.get("claims", []) for i in claim["evidence_ids"]
    ]
    used = list(dict.fromkeys([i for i in cited_ids(answer) if i in by_id] + claim_source_ids))
    mapping = {old: new for new, old in enumerate(used, start=1)}

    excerpts: dict[int, list[str]] = {}
    for item in state["evidence"]:
        excerpts.setdefault(item["source_id"], []).append(item["excerpt"])

    claims = [
        VerifiedClaim(
            text=claim["text"],
            status=claim["status"],
            rationale=claim["rationale"],
            citations=sorted({mapping[evidence[i]["source_id"]] for i in claim["evidence_ids"]}),
        )
        for claim in state.get("claims", [])
    ]
    sources = [
        CitedSource(
            id=mapping[old],
            url=by_id[old].url,
            title=by_id[old].title,
            domain=by_id[old].domain,
            published_date=by_id[old].published_date,
            excerpts=excerpts.get(old, [])[:4],
        )
        for old in used
    ]
    result = ResearchResult(
        title=title,
        research_question=state["question"],
        answer_markdown=rewrite_citations(answer, mapping),
        claims=claims,
        sources=sources,
        limitations=[item for item in output.limitations if item.strip()],
        models_used=ctx.llm.models_used,
        stats=RunStats(
            searches=len(state.get("searched_queries", [])),
            pages_fetched=state.get("pages_fetched", 0),
            sources_considered=len(by_id),
            iterations=state.get("iterations", 0),
            tokens_used=ctx.llm.tokens_used,
        ),
    )
    return result.model_dump()


async def synthesize(ctx: Context, state: ResearchState) -> dict:
    if not state.get("evidence"):
        return {"status": "insufficient_evidence", "_detail": "No usable evidence found"}

    by_id = {source.id: source for source in _sources(state)}
    claims = "\n".join(f"- [{c['status']}] {c['text']} (evidence: {c['evidence_ids']})" for c in state.get("claims", []))
    numbers = "\n".join(f"[{s.id}] {sanitize_untrusted(s.title)} ({s.domain})" for s in by_id.values())
    user = (
        f"Question:\n{state['question']}\n\nVerified claims:\n{claims}\n\n"
        f"Evidence:\n{_evidence_block(state)}\n\nSource numbers you may cite:\n{numbers}"
    )
    system = prompts.SYNTHESIS_SYSTEM
    for _attempt in range(2):
        output = await ctx.llm.structured(SynthesisOutput, system, user)
        answer = strip_sources_section(output.answer_markdown)
        if any(i in by_id for i in cited_ids(answer)):
            title = clean_title(output.title, state["question"])
            result = _build_result(ctx, state, output, answer, title)
            # Kept apart from the result so the page text stays on the server, for detailed reports.
            urls = {source.id: source.url for source in by_id.values()}
            texts = {
                cited["id"]: source.content
                for cited in result["sources"]
                for source in by_id.values()
                if urls[source.id] == cited["url"] and source.content
            }
            return {
                "status": "completed",
                "result": result,
                "source_texts": texts,
                "_detail": "Cited answer ready",
            }
        system = f"{prompts.SYNTHESIS_SYSTEM}\n\n{prompts.CITATION_REPAIR}"
    return {"status": "insufficient_evidence", "_detail": "Model could not produce a cited answer"}


STEP_LABELS = {
    "scope_guard": "Checking the question",
    "plan": "Planning the research",
    "search": "Searching the web",
    "fetch": "Reading sources",
    "extract_evidence": "Extracting evidence",
    "verify": "Verifying claims",
    "follow_up": "Filling evidence gaps",
    "synthesize": "Writing the answer",
}


def _node(name: str, ctx: Context, func: Callable[[Context, ResearchState], Awaitable[dict]]):
    """Wrap a node so the UI sees its real start, finish, duration, and outcome."""

    async def wrapped(state: ResearchState) -> dict[str, Any]:
        writer = get_stream_writer()
        started = time.monotonic()
        writer({"step": name, "label": STEP_LABELS[name], "status": "running"})
        update = await func(ctx, state)
        detail = update.pop("_detail", None)
        writer(
            {
                "step": name,
                "label": STEP_LABELS[name],
                "status": "done",
                "detail": detail,
                "duration_ms": int((time.monotonic() - started) * 1000),
            }
        )
        return update

    return wrapped


def build_graph(ctx: Context):
    nodes = {
        "scope_guard": scope_guard,
        "plan": plan,
        "search": search,
        "fetch": fetch,
        "extract_evidence": extract_evidence,
        "verify": verify,
        "follow_up": follow_up,
        "synthesize": synthesize,
    }
    graph = StateGraph(ResearchState)
    for name, func in nodes.items():
        graph.add_node(name, _node(name, ctx, func))
    graph.add_edge(START, "scope_guard")
    graph.add_conditional_edges(
        "scope_guard", lambda state: END if state.get("status") == "rejected" else "plan", ["plan", END]
    )
    graph.add_edge("plan", "search")
    graph.add_edge("search", "fetch")
    graph.add_edge("fetch", "extract_evidence")
    graph.add_edge("extract_evidence", "verify")
    graph.add_conditional_edges(
        "verify",
        lambda state: "follow_up" if _should_continue(ctx, state) else "synthesize",
        ["follow_up", "synthesize"],
    )
    graph.add_edge("follow_up", "search")
    graph.add_edge("synthesize", END)
    return graph.compile()
