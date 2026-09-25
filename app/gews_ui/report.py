"""A4 evidence PDF for one lake and one window, with a signature block.

If the lake could not be assessed, the PDF says so and prints no number."""
from __future__ import annotations

import io
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import config as C
from .components import SCOPE_LINE, drivers_text
from .data import blind_spans, longest_blind_days, window_label

INK = colors.HexColor("#15303A")
MUTED = colors.HexColor("#5E7078")
RED = colors.HexColor("#A32E24")


def _chart_png(series: pd.DataFrame, thresholds: dict, selected: pd.Timestamp, events: pd.DataFrame) -> bytes:
    fig, ax = plt.subplots(figsize=(7.2, 2.6), dpi=160)
    for s, e, _ in blind_spans(series):
        ax.axvspan(s, e, facecolor="#E3E7E9", edgecolor="#9AA4A8", hatch="///", linewidth=0)
    ax.plot(series["window_start"], series["risk"], color="#15303A", lw=1.2)  # NaN breaks the line
    for name, v in thresholds.items():
        ax.axhline(v, ls="--", lw=0.8, color={"watch": "#C9921E", "concern": "#C2601C", "high": "#A32E24"}[name])
    for _, ev in events.iterrows():
        ax.axvline(ev["date"], color="#A32E24", lw=1.5)
    ax.axvline(selected, color="#2A6F97", lw=1.2)
    ax.set_ylim(0, 1.02)
    ax.set_ylabel("Risk", fontsize=8)
    ax.tick_params(labelsize=7)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def evidence_pdf(lake: pd.Series, series: pd.DataFrame, window: pd.Timestamp, thresholds: dict,
                 events: pd.DataFrame, data_version: str, is_demo: bool) -> bytes:
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontName="Times-Bold", fontSize=18,
                        textColor=INK, alignment=0, spaceAfter=2)
    body = ParagraphStyle("b", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.5,
                          leading=13, textColor=INK)
    small = ParagraphStyle("s", parent=body, fontSize=8, textColor=MUTED)
    warn = ParagraphStyle("w", parent=body, textColor=RED, fontName="Helvetica-Bold")
    h2 = ParagraphStyle("h2", parent=body, fontName="Times-Bold", fontSize=12, spaceBefore=8, spaceAfter=3)

    row = series.loc[series["window_start"] == window].iloc[0]
    risk = row["risk"]
    level = C.level_for(risk, thresholds)

    story = [Paragraph(f"GEWS evidence sheet: {lake['name']}", h1),
             Paragraph(f"{lake['lake_id']}, {lake['region']}. Window {window_label(window)}. "
                       f"Data version {data_version}.", small),
             Spacer(1, 4), Paragraph(SCOPE_LINE, warn)]
    if is_demo:
        story.append(Paragraph("DEMO DATA: synthetic values, not derived from satellite imagery.", warn))
    story.append(Spacer(1, 6))

    if pd.isna(risk):
        story += [Paragraph("Status: CANNOT ASSESS", h2),
                  Paragraph(f"No score was produced for this window. Reason: <b>{row['abstain_reason']}</b>. "
                            "This is not a statement that the lake is safe; it means the lake could not "
                            "be seen well enough to compare with its own past.", body)]
    else:
        story += [Paragraph(f"Risk {risk:.2f}: {C.LEVEL_LABELS[level]}", h2),
                  Paragraph("The score ranks how far this window sits from this lake's own multi-year "
                            "normal. It measures unusualness, not danger or flood magnitude.", body),
                  Paragraph(f"Main contributing signals: <b>{drivers_text(row['contributing_signals'])}</b>.", body)]
        data = [["Signal", "Anomaly score (0–1)", "Fusion weight"]]
        for s in C.SIGNALS:
            v = row.get(f"score_{s}")
            data.append([C.SIGNAL_LABELS[s], "not seen" if pd.isna(v) else f"{v:.2f}", f"{C.FUSION_WEIGHTS[s]:.2f}"])
        t = Table(data, colWidths=[62 * mm, 50 * mm, 35 * mm])
        t.setStyle(TableStyle([("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
                               ("FONT", (0, 1), (-1, -1), "Helvetica", 8.5),
                               ("TEXTCOLOR", (0, 0), (-1, -1), INK),
                               ("LINEBELOW", (0, 0), (-1, 0), 0.6, INK),
                               ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#D6DEE1")),
                               ("ALIGN", (1, 0), (-1, -1), "RIGHT")]))
        story += [Spacer(1, 6), t]

    obs = row.get("observability")
    story += [Spacer(1, 4), Paragraph(
        f"Observability this window: {'n/a' if pd.isna(obs) else f'{obs:.2f}'} "
        f"(floor {C.OBSERVABILITY_FLOOR:.2f}). Thresholds: watch {thresholds['watch']:.2f}, "
        f"concern {thresholds['concern']:.2f}, high {thresholds['high']:.2f}.", small)]

    story += [Paragraph("Risk history", h2),
              Image(io.BytesIO(_chart_png(series, thresholds, window, events)), width=175 * mm, height=63 * mm),
              Paragraph("Hatched bands are windows with no score (could not see). Gaps are never filled in.", small)]

    story.append(Paragraph(f"Longest blind spell in the record (after model warm-up): "
                           f"{longest_blind_days(series)} days.", small))

    story += [Spacer(1, 14), Paragraph("Officer review", h2)]
    sig = Table([["Reviewed by", "", "Designation", ""], ["Signature", "", "Date", ""],
                 ["Action taken", "", "", ""]],
                colWidths=[28 * mm, 60 * mm, 28 * mm, 59 * mm], rowHeights=[11 * mm, 11 * mm, 18 * mm])
    sig.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
                             ("TEXTCOLOR", (0, 0), (-1, -1), MUTED),
                             ("SPAN", (1, 2), (3, 2)),
                             ("LINEBELOW", (1, 0), (1, 1), 0.5, INK), ("LINEBELOW", (3, 0), (3, 1), 0.5, INK),
                             ("BOX", (1, 2), (3, 2), 0.5, INK), ("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    story += [sig, Spacer(1, 10), Paragraph(
        f"Generated {datetime.now():%d %b %Y %H:%M} by GEWS. Decision support only; never a guarantee of safety. "
        "Where the system cannot see, it says so.", small)]

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=17 * mm, rightMargin=17 * mm,
                      topMargin=15 * mm, bottomMargin=15 * mm,
                      title=f"GEWS evidence {lake['lake_id']} {window:%Y-%m-%d}").build(story)
    return buf.getvalue()
