"""Models for workflow output. The LLM-facing ones avoid numeric and length constraints
because providers support them unevenly; guardrails enforce limits after the call."""

from typing import Literal

from pydantic import BaseModel, Field

ClaimStatus = Literal["supported", "partially_supported", "conflicting", "unsupported"]


class ScopeDecision(BaseModel):
    in_scope: bool = Field(description="True for a technical research question this tool can answer from public sources.")
    reason: str = Field(description="One short sentence shown to the user when the question is out of scope.")
    refined_question: str = Field(description="The question restated clearly, without changing its meaning.")


class ResearchPlan(BaseModel):
    subqueries: list[str] = Field(description="Focused web search queries, each covering a different aspect.")


class EvidenceDraft(BaseModel):
    source_id: int = Field(description="The id attribute of the source this came from.")
    claim: str = Field(description="The factual claim this passage supports, in your own words.")
    excerpt: str = Field(description="A passage copied word for word from the source, 1-3 sentences.")


class EvidenceBatch(BaseModel):
    items: list[EvidenceDraft]


class ClaimDraft(BaseModel):
    text: str = Field(description="One specific, checkable claim that helps answer the question.")
    status: ClaimStatus
    evidence_ids: list[int] = Field(description="Ids of the evidence items that bear on this claim.")
    rationale: str = Field(description="One sentence on why this status applies.")


class VerificationOutput(BaseModel):
    claims: list[ClaimDraft]
    needs_more_research: bool = Field(description="True only if an important part of the question lacks evidence.")
    follow_up_queries: list[str] = Field(description="Web search queries that would fill the gaps. Empty if none.")


class SynthesisOutput(BaseModel):
    title: str = Field(description="A specific title of 4-10 words naming the subject. Not a question. No markdown.")
    answer_markdown: str = Field(description="The cited answer in Markdown, with citations written like [1].")
    limitations: list[str] = Field(description="Gaps, conflicts, or weak evidence the reader should know about.")


class Evidence(BaseModel):
    id: int
    source_id: int
    claim: str
    excerpt: str


class Source(BaseModel):
    id: int
    url: str
    title: str
    domain: str
    published_date: str | None = None
    snippet: str = ""
    content: str = ""
    search_score: float = 0.0
    rank_score: float = 0.0
    fetched: bool = False


class CitedSource(BaseModel):
    id: int
    url: str
    title: str
    domain: str
    published_date: str | None = None
    excerpts: list[str]


class VerifiedClaim(BaseModel):
    text: str
    status: ClaimStatus
    rationale: str
    citations: list[int]


class RunStats(BaseModel):
    searches: int
    pages_fetched: int
    sources_considered: int
    iterations: int
    tokens_used: int


class ResearchResult(BaseModel):
    title: str
    research_question: str = ""
    answer_markdown: str
    claims: list[VerifiedClaim]
    sources: list[CitedSource]
    limitations: list[str]
    models_used: list[str]
    stats: RunStats
    steps: list[dict] = []
