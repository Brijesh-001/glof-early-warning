import numpy as np
import pandas as pd
import streamlit as st

from gews_ui import charts
from gews_ui import config as C
from gews_ui.components import demo_banner, page_header, summary_strip
from gews_ui.data import lake_series, longest_blind_days
from gews_ui.results import get_results
from gews_ui.state import get_data

ds = get_data()
res = get_results(ds.evaluation)["radar"]

page_header("What we can see",
            "A camera waits for sunlight and cloud stops it. Radar sends its own pulse through cloud. "
            "This page shows how often each lake could be assessed, and where the blind spells are.")
demo_banner(ds)

f = ds.features.copy()
W = C.OBSERVABILITY_WEIGHTS
f["obs_no_radar"] = f["observability"] - W["radar"] * f["obs_radar"]
f["season"] = np.where(f["window_start"].dt.month.isin(list(C.MONSOON_MONTHS)), "Monsoon (Jun–Sep)", "Dry season (Oct–May)")
stats = (f.groupby("season")
         .apply(lambda g: pd.Series({"optical_only": (g["obs_no_radar"] >= C.OBSERVABILITY_FLOOR).mean(),
                                     "combined": (g["observability"] >= C.OBSERVABILITY_FLOOR).mean()}),
                include_groups=False)
         .reset_index().sort_values("season", ascending=False))
mon = f.loc[f["season"].str.startswith("Monsoon")]
gains = mon.groupby("lake_id").apply(lambda g: (g["observability"] - g["obs_no_radar"]).mean(),
                                     include_groups=False)

summary_strip([
    ("monsoon windows seen, optical only", f"{res['monsoon_optical_only_pct']:.1f}%"),
    ("monsoon windows seen, with radar", f"{res['monsoon_combined_pct']:.1f}%"),
    ("monsoon windows recovered", f"{res['recovered_windows']:,} of {res['monsoon_windows']:,}"),
    ("worst blind spell", f"{res['worst_blind_days']} days"),
])
st.caption(f"Headline figures: {get_results(ds.evaluation)['source']}. Charts below are computed live "
           "from the loaded data" + (" (synthetic in demo mode)." if ds.is_demo else "."))

a, b = st.columns(2, gap="large")
with a:
    st.markdown("### Assessable windows, with and without radar")
    st.plotly_chart(charts.assessability_bars(stats), width="stretch", config={"displayModeBar": False})
with b:
    st.markdown("### Gain from radar, per lake")
    st.plotly_chart(charts.gain_histogram(gains), width="stretch", config={"displayModeBar": False})

st.markdown("### Every lake, every window")
st.caption("Blue cells were scored as normal; amber to red cells crossed a threshold. Dark grey cells had no score: cloud, no radar pass, or too little history.")
years = sorted(ds.scores["window_start"].dt.year.unique())
y0, y1 = st.select_slider("Years", options=years, value=(max(years[0], years[-1] - 2), years[-1]))
sc = ds.scores.loc[ds.scores["window_start"].dt.year.between(y0, y1)].merge(ds.lakes[["lake_id", "name"]], on="lake_id")
pivot = sc.pivot_table(index="name", columns="window_start", values="risk", dropna=False, aggfunc="first")
st.plotly_chart(charts.blind_heatmap(pivot), width="stretch")

st.markdown("### Longest blind spell per lake")
st.caption("Excludes the first months of each record, when the model is still collecting history.")
tbl = pd.DataFrame([{"Lake": r["name"], "Region": r["region"],
                     "Longest blind spell (days)": longest_blind_days(lake_series(ds, r["lake_id"])),
                     "Windows with no score (incl. warm-up)": int(ds.scores.loc[ds.scores["lake_id"] == r["lake_id"], "risk"].isna().sum())}
                    for _, r in ds.lakes.iterrows()]).sort_values("Longest blind spell (days)", ascending=False)
st.dataframe(tbl, hide_index=True, width="stretch")
