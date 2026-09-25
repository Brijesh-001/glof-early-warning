"""Plotly figures. Rule: gaps are never bridged. Lines break at NaN and
blind windows are drawn as hatched bands labelled 'could not see'."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import config as C
from .data import blind_spans, window_end
from .theme import INK, LAKE, LEVEL_COLOURS, MORAINE, MUTED, RULE

TEN_DAYS_MS = 10 * 24 * 3600 * 1000


def _blind_bars(fig, series, y0=0.0, y1=1.0, row=None, col=None, showlegend=True):
    blind = series.loc[series["risk"].isna()]
    if blind.empty:
        return
    x = blind["window_start"] + pd.Timedelta(days=5)
    fig.add_trace(go.Bar(
        x=x, y=[y1 - y0] * len(blind), base=[y0] * len(blind), width=TEN_DAYS_MS,
        marker=dict(color="rgba(167,176,180,0.18)", line=dict(width=0),
                    pattern=dict(shape="/", fgcolor="rgba(120,132,137,0.55)", size=6, solidity=0.25)),
        name="Could not see", hovertemplate="Could not see: %{customdata}<extra></extra>",
        customdata=blind["abstain_reason"], showlegend=showlegend, legendgroup="blind"),
        row=row, col=col)


def risk_chart(series: pd.DataFrame, thresholds: dict, events: pd.DataFrame,
               selected: pd.Timestamp | None = None, height: int = 380) -> go.Figure:
    fig = go.Figure()
    _blind_bars(fig, series)
    fig.add_trace(go.Scatter(
        x=series["window_start"], y=series["risk"], mode="lines+markers", connectgaps=False,
        line=dict(color=INK, width=2), marker=dict(size=4, color=INK), name="Risk",
        hovertemplate="%{x|%d %b %Y}<br>Risk %{y:.2f}<extra></extra>"))
    for name, v in thresholds.items():
        colour = LEVEL_COLOURS[name]
        fig.add_hline(y=v, line=dict(color=colour, width=1, dash="dash"),
                      annotation=dict(text=f"{name} {v:.2f}", font=dict(color=colour, size=11),
                                      xanchor="left", x=0, yanchor="bottom"))
    for _, e in events.iterrows():
        fig.add_vline(x=e["date"], line=dict(color=LEVEL_COLOURS["high"], width=2))
        fig.add_annotation(x=e["date"], y=1.0, yref="y", text=e["description"], showarrow=False,
                           font=dict(color=LEVEL_COLOURS["high"], size=11), xanchor="right", yanchor="top")
    if selected is not None:
        fig.add_vrect(x0=selected, x1=window_end(selected), fillcolor=LAKE, opacity=0.18, line_width=0)
    fig.update_layout(height=height, yaxis=dict(range=[0, 1.02], title="Risk score"),
                      bargap=0, showlegend=True, hovermode="x unified")
    return fig


def signal_panels(series: pd.DataFrame, raw: bool = False, height: int = 520) -> go.Figure:
    fig = make_subplots(rows=len(C.SIGNALS), cols=1, shared_xaxes=True, vertical_spacing=0.03,
                        subplot_titles=[
                            f"{C.SIGNAL_LABELS[s]}" + (f" ({C.SIGNAL_UNITS[s]})" if raw else "")
                            for s in C.SIGNALS])
    for i, s in enumerate(C.SIGNALS, start=1):
        col = s if raw else f"score_{s}"
        y = series[col]
        fig.add_trace(go.Scatter(x=series["window_start"], y=y, mode="lines+markers", connectgaps=False,
                                 line=dict(color=LAKE if i == 1 else MORAINE, width=1.6),
                                 marker=dict(size=3, color=LAKE if i == 1 else MORAINE),
                                 name=C.SIGNAL_LABELS[s], showlegend=False,
                                 hovertemplate="%{x|%d %b %Y}<br>%{y:.3f}<extra>" + C.SIGNAL_LABELS[s] + "</extra>"),
                      row=i, col=1)
        if not raw:
            fig.update_yaxes(range=[0, 1.02], row=i, col=1)
    for a in fig.layout.annotations:
        a.update(x=0, xanchor="left", font=dict(size=12, color=MUTED))
    fig.update_layout(height=height, margin=dict(l=56, r=24, t=30, b=30))
    return fig


def observability_chart(series: pd.DataFrame, height: int = 260) -> go.Figure:
    fig = go.Figure()
    obs = series["observability"]
    fig.add_trace(go.Scatter(x=series["window_start"], y=obs, mode="lines", connectgaps=False,
                             line=dict(color=LAKE, width=1.5, shape="hv"), fill="tozeroy",
                             fillcolor="rgba(42,111,151,0.12)", name="Observability",
                             hovertemplate="%{x|%d %b %Y}<br>%{y:.2f}<extra></extra>"))
    fig.add_hline(y=C.OBSERVABILITY_FLOOR, line=dict(color=LEVEL_COLOURS["high"], width=1, dash="dot"),
                  annotation=dict(text=f"floor {C.OBSERVABILITY_FLOOR:.2f}: below this, no score",
                                  font=dict(size=11, color=LEVEL_COLOURS["high"]), x=0, xanchor="left"))
    fig.update_layout(height=height, yaxis=dict(range=[0, 1.02], title="Seen"), showlegend=False)
    return fig


def contribution_chart(row: pd.Series) -> go.Figure:
    names, vals, colours = [], [], []
    for s in C.SIGNALS:
        v = row.get(f"score_{s}", np.nan)
        names.append(C.SIGNAL_LABELS[s])
        vals.append(v)
        colours.append(LAKE if pd.notna(v) else "#C9D1D4")
    labels = [f"{v:.2f}" if pd.notna(v) else "not seen" for v in vals]
    fig = go.Figure(go.Bar(y=names, x=[0 if pd.isna(v) else v for v in vals], orientation="h",
                           marker_color=colours, text=labels, textposition="outside",
                           hovertemplate="%{y}: %{text}<extra></extra>"))
    fig.update_layout(height=250, xaxis=dict(range=[0, 1.15], title="Per-signal anomaly score"),
                      yaxis=dict(autorange="reversed"), margin=dict(l=150, r=24, t=10, b=40))
    return fig


def lake_map(ranked: pd.DataFrame, blind: pd.DataFrame, height: int = 460) -> go.Figure:
    fig = go.Figure()
    if len(ranked):
        fig.add_trace(go.Scattermap(
            lat=ranked["lat"], lon=ranked["lon"], mode="markers",
            marker=dict(size=9 + ranked["risk"] * 16, color=[LEVEL_COLOURS[l] for l in ranked["level"]], opacity=0.9),
            text=ranked["name"], customdata=np.stack([ranked["risk"], ranked["level"]], axis=1),
            hovertemplate="<b>%{text}</b><br>Risk %{customdata[0]:.2f} (%{customdata[1]})<extra></extra>",
            name="Scored"))
    if len(blind):
        fig.add_trace(go.Scattermap(
            lat=blind["lat"], lon=blind["lon"], mode="markers",
            marker=dict(size=11, color="#8D989D", opacity=0.9, symbol="circle"),
            text=blind["name"], customdata=blind["abstain_reason"],
            hovertemplate="<b>%{text}</b><br>Cannot assess: %{customdata}<extra></extra>",
            name="Cannot assess"))
    lat = pd.concat([ranked["lat"], blind["lat"]]).mean()
    lon = pd.concat([ranked["lon"], blind["lon"]]).mean()
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=0, b=0),
                      map=dict(style="carto-positron", center=dict(lat=lat, lon=lon), zoom=4.2),
                      legend=dict(y=0.02, x=0.01, bgcolor="rgba(255,255,255,0.85)"))
    return fig


def assessability_bars(stats: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for col, colour, name in [("optical_only", "#9AA5AA", "Optical only"), ("combined", INK, "Optical + radar")]:
        fig.add_trace(go.Bar(x=stats["season"], y=stats[col] * 100, name=name, marker_color=colour,
                             text=[f"{v*100:.1f}%" for v in stats[col]], textposition="outside"))
    fig.update_layout(barmode="group", height=340, yaxis=dict(range=[0, 110], title="Windows assessable (%)"))
    return fig


def gain_histogram(gains: pd.Series) -> go.Figure:
    fig = go.Figure(go.Histogram(x=gains, nbinsx=14, marker_color=LAKE, marker_line=dict(color="white", width=1)))
    fig.add_vline(x=gains.mean(), line=dict(color=LEVEL_COLOURS["high"], width=2),
                  annotation=dict(text=f"mean {gains.mean():.3f}", font=dict(color=LEVEL_COLOURS["high"])))
    fig.update_layout(height=340, xaxis_title="Monsoon observability gain from radar", yaxis_title="Lakes")
    return fig


def blind_heatmap(pivot: pd.DataFrame) -> go.Figure:
    """Lakes × windows. Scored windows coloured by risk, blind windows grey."""
    z = pivot.to_numpy(dtype=float)
    blind = np.where(np.isnan(z), 1.0, np.nan)
    fig = go.Figure()
    fig.add_trace(go.Heatmap(z=blind, x=pivot.columns, y=pivot.index, showscale=False,
                             colorscale=[[0, "#7F8B90"], [1, "#7F8B90"]], hoverinfo="skip"))
    fig.add_trace(go.Heatmap(z=z, x=pivot.columns, y=pivot.index, zmin=0, zmax=1,
                             colorscale=[[0, "#E4EEF3"], [0.49, "#9CC0D3"], [0.5, LEVEL_COLOURS["watch"]],
                                         [0.7, LEVEL_COLOURS["concern"]], [1, LEVEL_COLOURS["high"]]],
                             colorbar=dict(title="Risk", thickness=10),
                             hovertemplate="%{y}<br>%{x|%d %b %Y}<br>Risk %{z:.2f}<extra></extra>"))
    fig.update_layout(height=max(420, 14 * len(pivot)), yaxis=dict(autorange="reversed", tickfont=dict(size=10)),
                      margin=dict(l=130, r=10, t=10, b=30))
    return fig


def detector_bars(det: pd.DataFrame, concern: float) -> go.Figure:
    fig = make_subplots(rows=1, cols=2, subplot_titles=[
        "Peak risk in the run-up (higher is better)", "False-alarm rate on the other lakes (lower is better)"])
    colours = [LEVEL_COLOURS["normal"] if not p else LAKE for p in det["production"]]
    fig.add_trace(go.Bar(x=det["label"], y=det["peak_risk"], marker_color=colours,
                         text=[f"{v:.3f}" for v in det["peak_risk"]], textposition="outside", showlegend=False), 1, 1)
    fig.add_trace(go.Bar(x=det["label"], y=det["false_alarm_pct"], marker_color=colours,
                         text=[f"{v:.2f}%" for v in det["false_alarm_pct"]], textposition="outside", showlegend=False), 1, 2)
    fig.add_hline(y=concern, line=dict(color=LEVEL_COLOURS["concern"], dash="dash", width=1), row=1, col=1)
    fig.update_yaxes(range=[0, 1], row=1, col=1)
    fig.update_yaxes(range=[0, max(det["false_alarm_pct"]) * 1.3 + 0.1], row=1, col=2)
    for a in fig.layout.annotations:
        a.update(font=dict(size=12, color=MUTED))
    fig.update_layout(height=360)
    return fig


def ablation_bars(abl: pd.DataFrame, full: float) -> go.Figure:
    colours = [INK if r == "all five signals" else (LEVEL_COLOURS["high"] if v < full else "#8FA79B")
               for r, v in zip(abl["run"], abl["peak_risk"])]
    labels = [r.replace("without ", "without<br>") for r in abl["run"]]
    fig = go.Figure(go.Bar(x=labels, y=abl["peak_risk"], marker_color=colours,
                           text=[f"{v:.3f}" for v in abl["peak_risk"]], textposition="outside"))
    fig.add_hline(y=full, line=dict(color=INK, dash="dash", width=1))
    fig.update_layout(height=340, xaxis=dict(tickangle=0), yaxis=dict(range=[0, 1], title="Peak risk in the run-up"))
    return fig
