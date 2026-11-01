from typing import Literal

from pydantic import BaseModel, Field


class TableDraft(BaseModel):
    title: str
    headers: list[str]
    rows: list[list[str]]


class ChartSeries(BaseModel):
    name: str
    values: list[float]


class ChartDraft(BaseModel):
    title: str
    kind: Literal["bar", "line"]
    unit: str = Field(description="Unit shared by all values, such as 'ms' or '%'. Empty if unitless.")
    labels: list[str] = Field(description="Category or time labels, one per value.")
    series: list[ChartSeries]
    source_ids: list[int] = Field(description="Source numbers the values come from.")


class SectionDraft(BaseModel):
    heading: str
    paragraphs: list[str]


class ReportDraft(BaseModel):
    """What the model supplies. Layout and styling belong entirely to the renderer."""

    title: str
    executive_summary: list[str]
    key_findings: list[str]
    comparison_tables: list[TableDraft]
    charts: list[ChartDraft]
    analysis_sections: list[SectionDraft]
    recommendation: list[str]


class ReportExpansion(BaseModel):
    sections: list[SectionDraft]


class ReportSource(BaseModel):
    id: int
    title: str
    url: str
    domain: str
    published_date: str | None = None


class ReportSpec(BaseModel):
    """Validated content, guaranteed to fit the fixed template."""

    title: str
    question: str
    executive_summary: list[str]
    key_findings: list[str]
    tables: list[TableDraft]
    charts: list[ChartDraft]
    sections: list[SectionDraft]
    recommendation: list[str]
    sources: list[ReportSource]
