"""The fixed report template. ReportLab Platypus owns all layout, so content can never overlap."""

import datetime as dt
import io
import re
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    Image,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from app.report.charts import render_chart
from app.report.models import ChartDraft, ReportSpec, TableDraft

SKY = HexColor("#2A78D6")
SKY_TINT = HexColor("#E3F2FD")
SKY_TEXT = HexColor("#1B5FAF")
PINK = HexColor("#D6417F")
PINK_TINT = HexColor("#FDEEF4")
PINK_WASH = HexColor("#FFF7FA")
INK = HexColor("#27303A")
MUTED = HexColor("#5F6B78")
RULE = HexColor("#D8E1EA")

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN_X = 20 * mm
MARGIN_TOP = 24 * mm
MARGIN_BOTTOM = 20 * mm
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN_X
MAX_CHART_HEIGHT = 170 * mm
# Room needed under a heading for a table's header and first row, so a heading is never stranded.
TABLE_START_HEIGHT = 70 * mm

SANS, BOLD, ITALIC, BOLD_ITALIC = "ReportSans", "ReportSans-Bold", "ReportSans-Italic", "ReportSans-BoldItalic"


def _register_fonts() -> None:
    """DejaVu ships with Matplotlib and covers Latin, Greek, Cyrillic, and technical symbols."""
    if SANS in pdfmetrics.getRegisteredFontNames():
        return
    font_dir = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    for name, filename in (
        (SANS, "DejaVuSans.ttf"),
        (BOLD, "DejaVuSans-Bold.ttf"),
        (ITALIC, "DejaVuSans-Oblique.ttf"),
        (BOLD_ITALIC, "DejaVuSans-BoldOblique.ttf"),
    ):
        pdfmetrics.registerFont(TTFont(name, str(font_dir / filename)))
    pdfmetrics.registerFontFamily(SANS, normal=SANS, bold=BOLD, italic=ITALIC, boldItalic=BOLD_ITALIC)


def _without_missing_glyphs(spec: ReportSpec) -> ReportSpec:
    """Remove characters the font lacks, such as CJK, which would otherwise print as empty boxes."""
    known = pdfmetrics.getFont(SANS).face.charToGlyph
    return ReportSpec.model_validate_json("".join(c for c in spec.model_dump_json() if ord(c) in known))


def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("body", fontName=SANS, fontSize=9.5, leading=14.5, textColor=INK, alignment=TA_LEFT, spaceAfter=7)
    return {
        "body": base,
        "title": ParagraphStyle("title", parent=base, fontName=BOLD, fontSize=21, leading=27, spaceAfter=0),
        "question": ParagraphStyle("question", parent=base, fontSize=9, leading=13.5, textColor=MUTED, spaceAfter=0),
        "eyebrow": ParagraphStyle("eyebrow", parent=base, fontName=BOLD, fontSize=8, leading=11, textColor=PINK, spaceAfter=0),
        "h1": ParagraphStyle(
            "h1", parent=base, fontName=BOLD, fontSize=13.5, leading=18, textColor=SKY_TEXT,
            spaceBefore=16, spaceAfter=7, keepWithNext=1,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base, fontName=BOLD, fontSize=10.5, leading=15, spaceBefore=9, spaceAfter=4, keepWithNext=1,
        ),
        # Table headings use a conditional page break instead: keepWithNext would push a long table
        # to a new page rather than letting it start here and split.
        "h1_flow": ParagraphStyle(
            "h1_flow", parent=base, fontName=BOLD, fontSize=13.5, leading=18, textColor=SKY_TEXT,
            spaceBefore=16, spaceAfter=7,
        ),
        "h2_flow": ParagraphStyle("h2_flow", parent=base, fontName=BOLD, fontSize=10.5, leading=15, spaceBefore=9, spaceAfter=4),
        "bullet": ParagraphStyle("bullet", parent=base, leftIndent=13, bulletIndent=1, spaceAfter=5, bulletColor=PINK),
        "cell": ParagraphStyle("cell", parent=base, fontSize=8, leading=11, spaceAfter=0),
        "head": ParagraphStyle("head", parent=base, fontName=BOLD, fontSize=8, leading=11, textColor=SKY_TEXT, spaceAfter=0),
        "caption": ParagraphStyle("caption", parent=base, fontSize=7.5, leading=10.5, textColor=MUTED, spaceAfter=4),
        "source": ParagraphStyle("source", parent=base, fontSize=8.5, leading=12.5, leftIndent=20, firstLineIndent=-20, spaceAfter=6),
    }


def _inline(text: str) -> str:
    """Convert plain model text to safe Paragraph markup. Escaping first means no tag from content survives."""
    markup = escape(text)
    markup = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", markup)
    markup = re.sub(r"(?<!\*)[*`](?!\s)(.+?)[*`]", r"\1", markup)
    return re.sub(r"\[(\d{1,3})\]", rf'<a href="#src-\1" color="{SKY_TEXT.hexval().replace("0x", "#")}">[\1]</a>', markup)


class _NumberedCanvas(Canvas):
    """Holds pages until the end so the footer can say 'Page x of y'."""

    def __init__(self, *args, report_title: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self._report_title = report_title
        self._saved_pages: list[dict] = []

    def showPage(self):
        self._saved_pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_pages)
        for page in self._saved_pages:
            self.__dict__.update(page)
            self._draw_chrome(total)
            super().showPage()
        super().save()

    def _fit(self, text: str, font: str, size: float, width: float) -> str:
        if pdfmetrics.stringWidth(text, font, size) <= width:
            return text
        while text and pdfmetrics.stringWidth(text + "…", font, size) > width:
            text = text[:-1]
        return text.rstrip() + "…"

    def _draw_chrome(self, total: int) -> None:
        # Sky and pink strip across the page top.
        self.setFillColor(SKY)
        self.rect(0, PAGE_HEIGHT - 5, PAGE_WIDTH * 0.7, 5, stroke=0, fill=1)
        self.setFillColor(PINK)
        self.rect(PAGE_WIDTH * 0.7, PAGE_HEIGHT - 5, PAGE_WIDTH * 0.3, 5, stroke=0, fill=1)

        header_y = PAGE_HEIGHT - 15 * mm
        self.setFont(BOLD, 8)
        self.setFillColor(SKY_TEXT)
        self.drawString(MARGIN_X, header_y, "ResearchOps")
        if self._pageNumber > 1:
            self.setFont(SANS, 7.5)
            self.setFillColor(MUTED)
            self.drawRightString(
                PAGE_WIDTH - MARGIN_X, header_y, self._fit(self._report_title, SANS, 7.5, CONTENT_WIDTH * 0.75)
            )

        footer_y = 11 * mm
        self.setStrokeColor(RULE)
        self.setLineWidth(0.5)
        self.line(MARGIN_X, footer_y + 10, PAGE_WIDTH - MARGIN_X, footer_y + 10)
        self.setFont(SANS, 7.5)
        self.setFillColor(MUTED)
        self.drawString(MARGIN_X, footer_y, f"Generated {dt.date.today():%d %B %Y}")
        self.drawRightString(PAGE_WIDTH - MARGIN_X, footer_y, f"Page {self._pageNumber} of {total}")


def _column_widths(table: TableDraft, total: float) -> list[float]:
    """Give wordier columns more room, while keeping each wide enough that its header words stay whole."""
    count = len(table.headers)
    padding = 12
    weights, floors = [], []
    for c in range(count):
        lengths = [len(table.headers[c]), *(len(row[c]) for row in table.rows)]
        weights.append(max(sum(lengths) / len(lengths), max(lengths) * 0.4, 6))
        word = max(pdfmetrics.stringWidth(w, BOLD, 8) for w in table.headers[c].split() or [""])
        floors.append(max(word + padding, total * 0.5 / count))
    if sum(floors) > total:
        # Headers too long to keep whole at this column count: share the width evenly.
        return [total / count] * count
    spare = total - sum(floors)
    return [floor + spare * weight / sum(weights) for floor, weight in zip(floors, weights)]


def _table(table: TableDraft, styles: dict[str, ParagraphStyle]) -> Table:
    data = [[Paragraph(_inline(h), styles["head"]) for h in table.headers]]
    data += [[Paragraph(_inline(cell), styles["cell"]) for cell in row] for row in table.rows]
    flowable = Table(
        data, colWidths=_column_widths(table, CONTENT_WIDTH), repeatRows=1, splitByRow=1, hAlign="LEFT"
    )
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), SKY_TINT),
        ("LINEBELOW", (0, 0), (-1, 0), 1, SKY),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    commands += [("BACKGROUND", (0, r), (-1, r), PINK_WASH) for r in range(2, len(data), 2)]
    flowable.setStyle(TableStyle(commands))
    return flowable


def _chart(chart: ChartDraft, styles: dict[str, ParagraphStyle]) -> KeepTogether:
    png, ratio = render_chart(chart)
    width = CONTENT_WIDTH
    height = width * ratio
    if height > MAX_CHART_HEIGHT:
        width, height = width * MAX_CHART_HEIGHT / height, MAX_CHART_HEIGHT
    citations = " ".join(f"[{i}]" for i in chart.source_ids)
    return KeepTogether(
        [
            Paragraph(_inline(chart.title), styles["h2"]),
            Image(io.BytesIO(png), width=width, height=height, hAlign="LEFT"),
            Paragraph(_inline(f"Values as stated in sources {citations}"), styles["caption"]),
            Spacer(1, 6),
        ]
    )


def _title_block(spec: ReportSpec, styles: dict[str, ParagraphStyle]) -> Table:
    block = Table(
        [
            [Paragraph("TECHNICAL RESEARCH REPORT", styles["eyebrow"])],
            [Paragraph(escape(spec.title), styles["title"])],
            [Paragraph(f"Research question: {escape(spec.question)}", styles["question"])],
        ],
        colWidths=[CONTENT_WIDTH],
    )
    block.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SKY_TINT),
                ("LINEBEFORE", (0, 0), (0, -1), 3, PINK),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, 0), 14),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
                ("TOPPADDING", (0, 1), (-1, 1), 2),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
                ("TOPPADDING", (0, 2), (-1, 2), 0),
                ("BOTTOMPADDING", (0, 2), (-1, 2), 14),
            ]
        )
    )
    return block


def _callout(paragraphs: list[str], styles: dict[str, ParagraphStyle]) -> Table:
    """A tinted box with one row per paragraph, so a long summary can still break across pages."""
    box = Table([[Paragraph(_inline(p), styles["body"])] for p in paragraphs], colWidths=[CONTENT_WIDTH])
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PINK_TINT),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 5),
            ]
        )
    )
    return box


def _story(spec: ReportSpec, styles: dict[str, ParagraphStyle]) -> list:
    story: list = [_title_block(spec, styles), Spacer(1, 4)]

    story.append(Paragraph("Executive Summary", styles["h1"]))
    story.append(_callout(spec.executive_summary, styles))

    if spec.key_findings:
        story.append(Paragraph("Key Findings", styles["h1"]))
        story += [Paragraph(_inline(finding), styles["bullet"], bulletText="•") for finding in spec.key_findings]

    if spec.tables or spec.charts:
        heading = (
            "Comparison Tables and Charts" if spec.tables and spec.charts else "Comparison Tables" if spec.tables else "Charts"
        )
        story += [CondPageBreak(TABLE_START_HEIGHT), Paragraph(heading, styles["h1_flow"] if spec.tables else styles["h1"])]
        for index, table in enumerate(spec.tables):
            # The first table's check already ran above its section heading, so the two stay together.
            story += [
                CondPageBreak(TABLE_START_HEIGHT if index else 0),
                Paragraph(_inline(table.title), styles["h2_flow"]),
                _table(table, styles),
                Spacer(1, 10),
            ]
        story += [_chart(chart, styles) for chart in spec.charts]

    if spec.sections:
        story.append(Paragraph("Detailed Analysis", styles["h1"]))
        for section in spec.sections:
            story.append(Paragraph(_inline(section.heading), styles["h2"]))
            story += [Paragraph(_inline(p), styles["body"]) for p in section.paragraphs]

    if spec.recommendation:
        story.append(Paragraph("Recommendation", styles["h1"]))
        story.append(_callout(spec.recommendation, styles))

    story.append(Paragraph("Sources", styles["h1"]))
    for source in spec.sources:
        date = f", {escape(source.published_date)}" if source.published_date else ""
        url = escape(source.url, {'"': "&quot;"})
        sky = SKY_TEXT.hexval().replace("0x", "#")
        story.append(
            Paragraph(
                f'<a name="src-{source.id}"/>[{source.id}] <b>{escape(source.title)}</b> '
                f"({escape(source.domain)}{date})<br/>"
                f'<a href="{url}" color="{sky}">{url}</a>',
                styles["source"],
            )
        )
    return story


def render_report(spec: ReportSpec) -> tuple[bytes, int]:
    """Return the PDF and its page count."""
    _register_fonts()
    spec = _without_missing_glyphs(spec)
    styles = _styles()
    buffer = io.BytesIO()
    document = BaseDocTemplate(
        buffer,
        pagesize=A4,
        title=spec.title,
        author="ResearchOps",
        subject=spec.question,
        leftMargin=MARGIN_X,
        rightMargin=MARGIN_X,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
    )
    frame = Frame(
        MARGIN_X, MARGIN_BOTTOM, CONTENT_WIDTH, PAGE_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )
    document.addPageTemplates([PageTemplate(id="page", frames=[frame], pagesize=A4)])

    def canvas_maker(*args, **kwargs):
        return _NumberedCanvas(*args, report_title=spec.title, **kwargs)

    document.build(_story(spec, styles), canvasmaker=canvas_maker)
    return buffer.getvalue(), document.page
