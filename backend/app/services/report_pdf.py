"""Renders the trip metrics and the model commentary as a PDF."""
from __future__ import annotations

import datetime as dt
import io
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table
from reportlab.platypus.tables import TableStyle

_FONT = "DejaVu"
_registered = False
_ASSETS = Path(__file__).resolve().parents[3] / "frontend" / "src" / "assets"


def _to_int32(value: int) -> int:
    value &= 0xFFFFFFFF
    if value >= 0x80000000:
        value -= 0x100000000
    return value


def bus_variant(vehicle_id: str) -> str:
    """Matches the dashboard: about a quarter of boards use the second photo."""
    digest = 0
    for char in str(vehicle_id):
        digest = _to_int32((_to_int32(digest) << 5) - digest + ord(char))
    return "v2" if abs(digest) % 4 == 0 else "v1"


def _ensure_font() -> None:
    global _registered
    if _registered:
        return
    path = Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf"
    pdfmetrics.registerFont(TTFont(_FONT, str(path)))
    _registered = True


def _chart(xs: list, ys: list[float], title: str, ylabel: str, color: str) -> io.BytesIO:
    fig, ax = plt.subplots(figsize=(7.2, 2.6), dpi=120)
    ax.plot(xs, ys, color=color, linewidth=1.6)
    ax.set_title(title, fontname="DejaVu Sans", fontsize=11)
    ax.set_ylabel(ylabel, fontname="DejaVu Sans", fontsize=9)
    ax.tick_params(labelsize=8)
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate(rotation=30, ha="right")
    fig.tight_layout()
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png")
    plt.close(fig)
    buffer.seek(0)
    return buffer


def _speed_chart(metrics: dict) -> io.BytesIO | None:
    series = metrics["series"]["speed"]
    if len(series) < 2:
        return None
    times = [dt.datetime.fromisoformat(point["t"]) for point in series]
    speeds = [point["speed_kmh"] for point in series]
    return _chart(times, speeds, "Скорость по ходу рейса", "км/ч", "#267ca3")


def stop_tick_indexes(labels: list[str]) -> list[int]:
    """Indexes that stay apart on the delay chart. A full label per bar overlaps."""
    count = len(labels)
    if count <= 1:
        return list(range(count))
    usable = 6.0
    slot = usable / count

    def half_width(label: str) -> float:
        return len(label) * 0.075 + 0.08

    chosen: list[int] = []
    occupied_until = -1.0
    for index, label in enumerate(labels):
        center = (index + 0.5) * slot
        half = half_width(label)
        if center - half >= occupied_until:
            chosen.append(index)
            occupied_until = center + half
    last = count - 1
    if chosen[-1] != last:
        last_center = (last + 0.5) * slot
        previous = chosen[-1]
        previous_end = (previous + 0.5) * slot + half_width(labels[previous])
        if last_center - half_width(labels[last]) >= previous_end:
            chosen.append(last)
        else:
            chosen[-1] = last
    return chosen


def _delay_chart(metrics: dict) -> io.BytesIO | None:
    stops = metrics["schedule"]["matched_stops"]
    if not stops:
        return None
    fig, ax = plt.subplots(figsize=(7.2, 2.6), dpi=120)
    labels = [str(stop["seq"]) for stop in stops]
    positions = list(range(len(stops)))
    delays = [stop["delay_s"] / 60 for stop in stops]
    colors = ["#ff453a" if value > 2 else "#30d158" if value < -1 else "#ffd60a" for value in delays]
    ax.bar(positions, delays, color=colors, width=0.72)
    ticks = stop_tick_indexes(labels)
    ax.set_xticks(ticks)
    ax.set_xticklabels([labels[index] for index in ticks], fontname="DejaVu Sans", fontsize=8)
    ax.set_xlim(-0.6, len(stops) - 0.4)
    ax.axhline(0, color="#666666", linewidth=0.8)
    ax.set_title("Отклонение на пройденных остановках", fontname="DejaVu Sans", fontsize=11)
    ax.set_xlabel("Номер остановки", fontname="DejaVu Sans", fontsize=9)
    ax.set_ylabel("мин", fontname="DejaVu Sans", fontsize=9)
    ax.tick_params(axis="y", labelsize=8)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png")
    plt.close(fig)
    buffer.seek(0)
    return buffer


def _facts(metrics: dict) -> list[str]:
    telemetry = metrics["telemetry"]
    speed = telemetry["speed_kmh"]
    schedule = metrics["schedule"]
    current = metrics["current"]
    lines = [
        f"Период: {metrics['period']['from']} — {metrics['period']['to']}",
        f"Точек телеметрии: {telemetry['points']}, достоверных GPS: {telemetry['valid_fraction']}",
        f"Пробег: {telemetry['distance_km']} км. Скорость: средняя {speed['mean']} км/ч, "
        f"медиана {speed['median']}, максимум {speed['max']}.",
        f"Стоянок: {telemetry['stopped_episodes']}, доля времени стоянки {telemetry['stopped_fraction']}, "
        f"самая длинная {telemetry['longest_stop_s']} с.",
        f"Остановок в расписании: {schedule['stops_total']}, сопоставлено с GPS: {schedule['stops_passed']}. "
        f"Среднее отклонение: {schedule['mean_delay_s']} с, максимум: {schedule['max_delay_s']} с.",
    ]
    if current:
        lines.append(
            f"Текущий прогноз: {current['predicted_delay_s']} с, риск {current['risk_level']}, "
            f"источник {current['source']}."
        )
    else:
        lines.append("Прогноза модели по этому борту пока нет.")
    return lines


def _fitted_image(path: Path, width: float, height: float) -> Image | str:
    if not path.is_file():
        return ""
    return Image(str(path), width=width, height=height, kind="proportional")


def _header(metrics: dict, title: ParagraphStyle, caption: ParagraphStyle) -> list:
    vehicle_id = str(metrics["vehicle_id"])
    text = [
        Paragraph(escape(f"Отчёт по борту {vehicle_id}"), title),
        Spacer(1, 1 * mm),
        Paragraph("Мосгортранс", caption),
    ]
    logo = _fitted_image(_ASSETS / "mostrans-logo.png", 14 * mm, 14 * mm)
    photo = _fitted_image(_ASSETS / f"bus-{bus_variant(vehicle_id)}-front.png", 26 * mm, 26 * mm)
    table = Table([[logo, text, photo]], colWidths=[18 * mm, 128 * mm, 28 * mm])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 0), (2, 0), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 3 * mm),
        ("RIGHTPADDING", (1, 0), (1, 0), 2 * mm),
        ("RIGHTPADDING", (2, 0), (2, 0), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    rule = HRFlowable(
        width="100%", thickness=0.4, color=colors.HexColor("#d1d5db"),
        spaceBefore=2 * mm, spaceAfter=3 * mm,
    )
    return [table, rule]


def render_trip_pdf(metrics: dict, analysis: str) -> bytes:
    _ensure_font()
    body = ParagraphStyle("body", fontName=_FONT, fontSize=10, leading=14, textColor="#1f2937")
    title = ParagraphStyle("title", fontName=_FONT, fontSize=16, leading=20, textColor="#111827")
    caption = ParagraphStyle("caption", fontName=_FONT, fontSize=9, leading=12, textColor="#6b7280")
    small = ParagraphStyle("small", fontName=_FONT, fontSize=9, leading=12, textColor="#374151")
    story = _header(metrics, title, caption)
    for line in _facts(metrics):
        story.append(Paragraph(escape(line), small))
        story.append(Spacer(1, 1.5 * mm))
    for chart in (_speed_chart(metrics), _delay_chart(metrics)):
        if chart is None:
            continue
        story.append(Spacer(1, 3 * mm))
        story.append(Image(chart, width=170 * mm, height=62 * mm))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Анализ", title))
    story.append(Spacer(1, 2 * mm))
    for paragraph in analysis.split("\n"):
        text = paragraph.strip()
        if text:
            story.append(Paragraph(escape(text), body))
            story.append(Spacer(1, 2 * mm))
    buffer = io.BytesIO()
    SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, title="Отчёт по рейсу").build(story)
    return buffer.getvalue()
