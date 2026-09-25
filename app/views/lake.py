import html

import pandas as pd
import streamlit as st

from gews_ui import charts
from gews_ui import config as C
from gews_ui.components import demo_banner, drivers_text, level_chip, page_header, scope_banner
from gews_ui.data import lake_series, longest_blind_days, thresholds_for, watchlist, window_label
from gews_ui.report import evidence_pdf
from gews_ui.state import current_window, get_data

ds = get_data()
window = current_window(ds)
lakes = ds.lakes.sort_values("name")
ids = list(lakes["lake_id"])
_ranked, _ = watchlist(ds, window)
default = st.session_state.get("lake_id", _ranked["lake_id"].iloc[0] if len(_ranked) else ids[0])

top = st.columns([2, 1])
with top[1]:
    lake_id = st.selectbox("Lake", ids, index=ids.index(default) if default in ids else 0,
                           format_func=lambda i: lakes.set_index("lake_id").loc[i, "name"])
    st.session_state["lake_id"] = lake_id

lake = lakes.set_index("lake_id").loc[lake_id]
lake_full = lake.copy()
lake_full["lake_id"] = lake_id
series = lake_series(ds, lake_id)
thr = thresholds_for(ds.lakes, lake_id)
row = series.loc[series["window_start"] == window].iloc[0]
level = C.level_for(row["risk"], thr)
events = ds.events.loc[ds.events["lake_id"] == lake_id] if len(ds.events) else ds.events

with top[0]:
    page_header(lake["name"], f"{lake_id}, {lake['region']}. Showing {window_label(window)}.")
scope_banner()
demo_banner(ds)

a, b, c = st.columns([1.1, 1.2, 1], gap="large")
with a:
    st.markdown("### This window")
    if pd.isna(row["risk"]):
        st.markdown(f"{level_chip('abstain')}", unsafe_allow_html=True)
        st.markdown(f"No score. **{html.escape(str(row['abstain_reason']).capitalize())}.**")
        st.caption("This does not mean the lake is safe. It means it could not be seen well enough "
                   "this window to compare with its own past.")
    else:
        st.markdown(f'<div class="gews-serif" style="font-size:3rem;font-weight:700;line-height:1">'
                    f'{row["risk"]:.2f}</div>{level_chip(level)}', unsafe_allow_html=True)
        st.markdown(f"Main reasons: **{drivers_text(row['contributing_signals'])}**")
with b:
    st.markdown("### Per-signal scores")
    if pd.isna(row["risk"]):
        st.caption("No per-signal scores: the model does not run on a window it cannot see.")
    else:
        st.plotly_chart(charts.contribution_chart(row), width="stretch", config={"displayModeBar": False})
        st.caption("Grey bars were not seen this window; the fusion weights renormalise without them.")
with c:
    st.markdown("### Lake")
    elev = lake.get("elevation_m")
    area = lake.get("area_ref_km2")
    obs = row.get("observability")
    st.markdown(
        '<dl class="gews-kv">'
        f"<dt>Elevation</dt><dd>{'—' if pd.isna(elev) else f'{int(elev):,} m'}</dd>"
        f"<dt>Reference area</dt><dd>{'—' if pd.isna(area) else f'{area:.2f} km²'}</dd>"
        f"<dt>Seen this window</dt><dd>{'—' if pd.isna(obs) else f'{obs:.2f}'}</dd>"
        f"<dt>Longest blind spell</dt><dd>{longest_blind_days(series)} days</dd>"
        f"<dt>Thresholds</dt><dd>{thr['watch']:.2f} / {thr['concern']:.2f} / {thr['high']:.2f}</dd>"
        "</dl>", unsafe_allow_html=True)
    pdf = evidence_pdf(lake_full, series, window, thr, events, ds.data_version, ds.is_demo)
    st.download_button("Export evidence PDF", pdf, file_name=f"GEWS_{lake_id}_{window:%Y-%m-%d}.pdf",
                       mime="application/pdf", type="primary", width="stretch")

st.markdown("### Risk over time")
years = sorted(series["window_start"].dt.year.unique())
y0, y1 = st.select_slider("Years shown", options=years, value=(max(years[0], years[-1] - 2), years[-1]))
view = series.loc[series["window_start"].dt.year.between(y0, y1)]
st.plotly_chart(charts.risk_chart(view, thr, events, selected=window), width="stretch")
st.caption("Hatched bands are windows with no score. The line is never drawn across them: "
           "a line across a gap would turn 'we could not see' into 'nothing was happening'.")

st.markdown("### Signals")
raw = st.toggle("Show raw measurements instead of anomaly scores", value=False)
st.plotly_chart(charts.signal_panels(view, raw=raw), width="stretch")

st.markdown("### How much we could see")
st.plotly_chart(charts.observability_chart(view), width="stretch", config={"displayModeBar": False})
