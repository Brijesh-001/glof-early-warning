"""Visual identity: glacier ink on ice paper, a lake blue, and a risk ramp
that only warms as risk rises. 'Cannot assess' is hatched grey everywhere —
never green, never blank, never a low number."""
from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

INK = "#15303A"        # glacier ink — text, dark surfaces
PAPER = "#F3F6F7"      # ice paper — page background
SURFACE = "#FFFFFF"
RULE = "#D6DEE1"
MUTED = "#5E7078"
LAKE = "#2A6F97"       # lake blue — data lines, primary action
MORAINE = "#7D7266"    # moraine — secondary data

LEVEL_COLOURS = {
    "normal": "#6C8C9C",
    "watch": "#C9921E",
    "concern": "#C2601C",
    "high": "#A32E24",
    "abstain": "#A7B0B4",
}

SERIF = "'Spectral', Georgia, 'Times New Roman', serif"
SANS = "'Public Sans', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700&family=Spectral:wght@500;600;700&display=swap');

html, body, [class*="css"], .stApp, .stMarkdown, button, input, select, textarea {{
  font-family: {SANS};
  font-feature-settings: "tnum" 1;
}}
.stApp {{ background: {PAPER}; color: {INK}; }}
h1, h2, h3, .gews-serif {{ font-family: {SERIF} !important; color: {INK}; letter-spacing: -0.01em; }}
h1 {{ font-weight: 700; font-size: 2.1rem !important; line-height: 1.15; }}
h2 {{ font-weight: 600; font-size: 1.45rem !important; }}
h3 {{ font-weight: 600; font-size: 1.15rem !important; }}
section[data-testid="stSidebar"] {{ background: {INK}; }}
section[data-testid="stSidebar"] * {{ color: #E6EEF1; }}
section[data-testid="stSidebar"] a[aria-current="page"] {{ background: rgba(255,255,255,.10); }}
section[data-testid="stSidebar"] [data-baseweb="select"] *,
section[data-testid="stSidebar"] input {{ color: {INK}; }}
.block-container {{ padding-top: 2.2rem; max-width: 1280px; }}
:focus-visible {{ outline: 3px solid {LAKE} !important; outline-offset: 2px; }}

/* The one standing message */
.gews-scope {{
  border-left: 4px solid {LEVEL_COLOURS['high']};
  background: #FBEDEB; color: #6E1F18; padding: .6rem .9rem; border-radius: 2px;
  font-weight: 600; font-size: .92rem; margin: .2rem 0 1rem;
}}
.gews-demo {{
  border: 1px dashed {MORAINE}; background: #F7F3EE; color: #4E463D;
  padding: .55rem .9rem; border-radius: 2px; font-size: .88rem; margin-bottom: .8rem;
}}
.gews-sub {{ color: {MUTED}; font-size: .98rem; margin-top: -.4rem; margin-bottom: 1rem; max-width: 72ch; }}

/* Summary strip */
.gews-strip {{ display: flex; gap: 2.2rem; flex-wrap: wrap; margin: .4rem 0 1.2rem; }}
.gews-strip div {{ min-width: 7rem; }}
.gews-strip b {{ display: block; font-family: {SERIF}; font-size: 1.9rem; line-height: 1; color: {INK}; }}
.gews-strip span {{ color: {MUTED}; font-size: .85rem; }}

/* Watch-list */
.gews-table {{ width: 100%; border-collapse: collapse; background: {SURFACE}; border: 1px solid {RULE}; }}
.gews-table th {{ text-align: left; font-weight: 600; font-size: .8rem; color: {MUTED};
  padding: .55rem .8rem; border-bottom: 1px solid {RULE}; background: #F8FAFB; }}
.gews-table td {{ padding: .6rem .8rem; border-bottom: 1px solid #EDF1F2; font-size: .93rem; vertical-align: middle; }}
td.gews-riskcell {{ white-space: nowrap; }}
.gews-table td.num {{ text-align: right; width: 3rem; color: {MUTED}; }}
.gews-lake {{ font-weight: 600; }}
.gews-region {{ color: {MUTED}; }}
.gews-bar {{ position: relative; height: .55rem; width: 9rem; background: #EDF1F2; border-radius: 1px;
  display: inline-block; vertical-align: middle; margin-right: .6rem; }}
.gews-bar i {{ position: absolute; left: 0; top: 0; bottom: 0; border-radius: 1px; }}
.gews-bar u {{ position: absolute; top: -3px; bottom: -3px; width: 1px; background: {INK}; opacity: .35; }}
.gews-risk {{ font-weight: 700; display: inline-block; width: 2.6rem; }}
.gews-level {{ white-space: nowrap; display: inline-block; padding: .1rem .5rem; border-radius: 2px; font-size: .8rem; font-weight: 600; color: #fff; }}
.gews-driver {{ color: {INK}; font-size: .88rem; }}
tr.gews-blind td {{
  background: repeating-linear-gradient(135deg, #F1F3F4 0 7px, #E6EAEC 7px 9px);
  color: #56646A;
}}
tr.gews-blind .gews-lake {{ font-weight: 500; }}
.gews-noscore {{ font-weight: 600; letter-spacing: .01em; }}
.gews-note {{ font-size: .85rem; color: {MUTED}; margin-top: .5rem; }}
.gews-kv {{ display: grid; grid-template-columns: max-content 1fr; gap: .25rem 1rem; font-size: .92rem; }}
.gews-kv dt {{ color: {MUTED}; }} .gews-kv dd {{ margin: 0; font-weight: 600; }}
@media (max-width: 760px) {{ .gews-bar {{ width: 4.5rem; }} .gews-hide-sm {{ display: none; }} }}
@media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; animation: none !important; }} }}
</style>
"""

pio.templates["gews"] = go.layout.Template(
    layout=dict(
        font=dict(family=SANS, color=INK, size=13),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        colorway=[LAKE, MORAINE, "#4F9A8F", "#9A6FB0", "#C9921E"],
        xaxis=dict(gridcolor="#EDF1F2", linecolor=RULE, zeroline=False, ticks="outside", tickcolor=RULE),
        yaxis=dict(gridcolor="#EDF1F2", linecolor=RULE, zeroline=False),
        margin=dict(l=56, r=24, t=40, b=40),
        hoverlabel=dict(font=dict(family=SANS), bgcolor=SURFACE, bordercolor=RULE),
        legend=dict(orientation="h", y=1.08, x=0, bgcolor="rgba(0,0,0,0)"),
        title=dict(font=dict(family=SERIF, size=16, color=INK), x=0, xanchor="left"),
    )
)
pio.templates.default = "gews"
