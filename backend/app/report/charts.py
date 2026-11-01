"""Chart rendering. Uses Matplotlib's object API, which is safe outside the main thread."""

import io
import textwrap

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from app.report.models import ChartDraft

# Fixed order, so a series keeps its identity across charts. Checked with a colorblind-safety validator.
SERIES_COLORS = ("#2A78D6", "#D6417F", "#6250D6")
MARKERS = ("o", "s", "^")
INK = "#27303A"
MUTED = "#5F6B78"
GRID = "#E6EAEE"
FONT = "DejaVu Sans"
FIGURE_WIDTH = 6.8
DPI = 220


def _format_value(value: float, unit: str) -> str:
    text = f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}".rstrip("0").rstrip(".")
    if not unit:
        return text
    return f"{text}{unit}" if unit in {"%", "$"} else f"{text} {unit}"


def _style_axes(ax) -> None:
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0, colors=MUTED, labelsize=8)


def _bar_chart(figure: Figure, chart: ChartDraft) -> None:
    ax = figure.add_subplot()
    count, series_count = len(chart.labels), len(chart.series)
    group = 0.76
    height = group / series_count
    for s, series in enumerate(chart.series):
        offset = (s - (series_count - 1) / 2) * height
        positions = [i + offset for i in range(count)]
        # The white edge leaves a small gap between neighbouring bars.
        bars = ax.barh(
            positions, series.values, height=height, color=SERIES_COLORS[s],
            edgecolor="white", linewidth=1.2, label=series.name,
        )
        labels = [_format_value(value, chart.unit) for value in series.values]
        ax.bar_label(bars, labels=labels, padding=4, fontsize=7.5, color=INK, fontfamily=FONT)
    ax.set_yticks(range(count), [textwrap.fill(label, 26) for label in chart.labels], color=INK)
    ax.invert_yaxis()
    # Headroom so the value labels stay inside the plot.
    ax.margins(x=0.2)
    # Every bar carries its value, so no value axis or gridlines are needed.
    _style_axes(ax)
    ax.tick_params(axis="x", labelbottom=False)


def _line_chart(figure: Figure, chart: ChartDraft) -> None:
    ax = figure.add_subplot()
    positions = list(range(len(chart.labels)))
    for s, series in enumerate(chart.series):
        ax.plot(
            positions, series.values, color=SERIES_COLORS[s], linewidth=2, marker=MARKERS[s],
            markersize=6, markeredgecolor="white", markeredgewidth=1.2, label=series.name,
        )
    ax.set_xticks(positions, [textwrap.fill(label, 12) for label in chart.labels], color=INK)
    ax.margins(x=0.06, y=0.15)
    if chart.unit:
        ax.set_ylabel(chart.unit, color=MUTED, fontsize=8)
    _style_axes(ax)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def render_chart(chart: ChartDraft) -> tuple[bytes, float]:
    """Return PNG bytes and height/width ratio. Constrained layout prevents overlapping labels."""
    if chart.kind == "bar":
        rows = len(chart.labels) * max(len(chart.series), 1)
        height = min(max(1.5, 0.42 * rows + 0.6), 7.0)
    else:
        height = 3.3
    figure = Figure(figsize=(FIGURE_WIDTH, height), dpi=DPI, layout="constrained", facecolor="white")
    FigureCanvasAgg(figure)
    (_bar_chart if chart.kind == "bar" else _line_chart)(figure, chart)
    if len(chart.series) > 1:
        figure.legend(
            loc="outside upper left", ncols=len(chart.series), frameon=False,
            prop={"family": FONT, "size": 8}, labelcolor=INK,
        )
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", facecolor="white")
    return buffer.getvalue(), height / FIGURE_WIDTH
