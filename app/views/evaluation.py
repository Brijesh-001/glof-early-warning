import pandas as pd
import streamlit as st

from gews_ui import charts
from gews_ui import config as C
from gews_ui.components import demo_banner, page_header
from gews_ui.data import lake_series, thresholds_for
from gews_ui.results import get_results
from gews_ui.state import get_data

ds = get_data()
R = get_results(ds.evaluation)
ev = R["event"]
cutoff = pd.Timestamp(ev["date"])

page_header("How it was tested",
            f"There is one confirmed moraine-dam failure in the study period: {ev['name']}, "
            f"{cutoff:%d %B %Y}. So no pooled precision or recall is reported. The tests below use "
            "walk-forward scores only, and thresholds and weights were frozen before they ran.")
demo_banner(ds)
st.caption(f"Numbers on this page: {R['source']}.")

st.markdown("### The retrospective test is negative")
r = R["retrospective"]
a, b = st.columns([1.6, 1], gap="large")
with a:
    series = lake_series(ds, ev["lake_id"])
    pre = series.loc[(series["window_start"] < cutoff) & (series["window_start"] >= cutoff - pd.DateOffset(months=12))]
    events = ds.events.loc[ds.events["lake_id"] == ev["lake_id"]] if len(ds.events) else ds.events
    st.plotly_chart(charts.risk_chart(pre, thresholds_for(ds.lakes, ev["lake_id"]), events),
                    width="stretch")
    if ds.is_demo:
        st.caption("The line is synthetic in demo mode. The results on the right are the reported ones.")
with b:
    for name in ["high", "concern", "watch"]:
        x = r[name]
        thr = C.THRESHOLDS[name]
        if x["crossed"]:
            st.markdown(f"**{name.capitalize()} ({thr:.2f})**: crossed {x['lead_days']} days before the event, "
                        f"at a cost of {x['false_alarm_days_per_lake_year']} false-alarm days per lake-year.")
        else:
            st.markdown(f"**{name.capitalize()} ({thr:.2f})**: never crossed.")
    st.markdown(f"Risk peaked about {r['peak_months_before']} months before the outburst and then fell. "
                "Going into the event, the score was moving down.")
    st.info("A lead time without its false-alarm rate is not a result, so the two are always shown together.")

st.markdown("### Why the miss is an instrument limit")
p = R["precursor"]
st.markdown(
    f"The documented precursor was moraine creep of {p['documented_mm_per_yr'][0]}–{p['documented_mm_per_yr'][1]} mm/yr "
    f"({p['reference']}). The glacier-velocity product used here has a noise floor of about "
    f"{p['its_live_noise_mm_per_yr']/1000:.0f} m/yr, far above that signal, so no threshold could have recovered it. "
    f"InSAR resolves around {p['insar_resolves_mm_per_yr']} mm/yr, which makes it the specified next sensor.")

st.markdown("### Why Isolation Forest")
det = pd.DataFrame(R["detectors"])
st.plotly_chart(charts.detector_bars(det, C.THRESHOLDS["concern"]), width="stretch",
                config={"displayModeBar": False})
st.caption("All detectors ran on the same data. Isolation Forest gave the loudest run-up with no false alarms "
           "on the other 40 lakes. The z-score baseline nearly matches it on peak risk, but its false-alarm rate rules it out.")

st.markdown("### Which signals carry the score")
abl = pd.DataFrame(R["ablation"])
full = float(abl.loc[abl["run"] == "all five signals", "peak_risk"].iloc[0])
st.plotly_chart(charts.ablation_bars(abl, full), width="stretch", config={"displayModeBar": False})
st.caption("Each run removes one signal and re-runs the pipeline. Removing lake area drops the peak most. "
           "Removing speed-up acceleration or radar change raises it, so those were damping the score.")
