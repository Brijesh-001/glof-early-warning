"""Small HTML building blocks rendered with st.markdown."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from . import config as C
from .theme import LEVEL_COLOURS

SCOPE_LINE = "Decision support only. This system never issues a public alert."


def page_header(title: str, sub: str | None = None) -> None:
    st.markdown(f"# {html.escape(title)}")
    if sub:
        st.markdown(f'<p class="gews-sub">{html.escape(sub)}</p>', unsafe_allow_html=True)


def scope_banner() -> None:
    st.markdown(f'<div class="gews-scope" role="note">{SCOPE_LINE}</div>', unsafe_allow_html=True)


def demo_banner(ds) -> None:
    if ds.is_demo:
        st.markdown(
            '<div class="gews-demo" role="note"><b>Demo data.</b> No pipeline output was found in '
            '<code>data/processed/</code>, so every number here is synthetic. Run the pipeline '
            '(or set <code>GEWS_DATA_DIR</code>) to see real lake scores.</div>',
            unsafe_allow_html=True)
    for w in ds.warnings:
        st.warning(w)


def level_chip(level: str) -> str:
    if level == "normal":  # quiet: colour is reserved for levels that need attention
        return '<span class="gews-level" style="color:#5E7078;padding-left:0">Normal</span>'
    return (f'<span class="gews-level" style="background:{LEVEL_COLOURS[level]}">'
            f'{C.LEVEL_LABELS[level]}</span>')


def drivers_text(contrib: str) -> str:
    names = [C.SIGNAL_LABELS.get(x, x) for x in str(contrib).split(";") if x]
    return ", ".join(names) if names else "—"


def summary_strip(items: list[tuple[str, str]]) -> None:
    cells = "".join(f"<div><b>{html.escape(v)}</b><span>{html.escape(k)}</span></div>" for k, v in items)
    st.markdown(f'<div class="gews-strip">{cells}</div>', unsafe_allow_html=True)


def watchlist_table(ranked: pd.DataFrame, blind: pd.DataFrame) -> None:
    rows = []
    w = C.THRESHOLDS
    ticks = "".join(f'<u style="left:{v*100:.0f}%"></u>' for v in w.values())
    for _, r in ranked.iterrows():
        colour = LEVEL_COLOURS[r["level"]]
        rows.append(
            "<tr>"
            f'<td class="num">{int(r["rank"])}</td>'
            f'<td><span class="gews-lake">{html.escape(r["name"])}</span></td>'
            f'<td class="gews-region gews-hide-sm">{html.escape(str(r["region"]))}</td>'
            f'<td class="gews-riskcell"><span class="gews-bar" aria-hidden="true"><i style="width:{r["risk"]*100:.1f}%;background:{colour}"></i>{ticks}</span>'
            f'<span class="gews-risk" style="color:{colour}">{r["risk"]:.2f}</span></td>'
            f'<td>{level_chip(r["level"])}</td>'
            f'<td class="gews-driver gews-hide-sm">{html.escape(drivers_text(r["contributing_signals"]))}</td>'
            "</tr>")
    for _, r in blind.iterrows():
        rows.append(
            '<tr class="gews-blind">'
            '<td class="num">—</td>'
            f'<td><span class="gews-lake">{html.escape(r["name"])}</span></td>'
            f'<td class="gews-region gews-hide-sm">{html.escape(str(r["region"]))}</td>'
            '<td class="gews-riskcell"><span class="gews-noscore">No score</span></td>'
            f'<td>{level_chip("abstain")}</td>'
            f'<td class="gews-driver">{html.escape(str(r["abstain_reason"]))}</td>'
            "</tr>")
    table = (
        '<table class="gews-table"><thead><tr>'
        '<th class="num">Rank</th><th>Lake</th><th class="gews-hide-sm">Region</th>'
        '<th>Risk (unusualness vs its own past)</th><th>Level</th><th class="gews-hide-sm">Why</th>'
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table>'
        '<p class="gews-note">Hatched rows are not safe lakes. They are lakes the satellites could '
        'not see well enough this window, so no score was made. The reason is shown on the right. '
        'Tick marks on each bar sit at the watch, concern and high thresholds.</p>')
    st.markdown(table, unsafe_allow_html=True)
