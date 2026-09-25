import streamlit as st

from gews_ui import config as C
from gews_ui.components import page_header, scope_banner
from gews_ui.results import get_results
from gews_ui.state import get_data

ds = get_data()
R = get_results(ds.evaluation)

page_header("Scope and limits", "Where the system cannot see, it must say so.")
scope_banner()

a, b = st.columns(2, gap="large")
with a:
    st.markdown("### What GEWS is")
    st.markdown("""
- Decision support for a trained disaster-management officer.
- A ranking of 41 fixed lakes by how far each has drifted from its own multi-year normal.
- An indicator on a scale of weeks to months, updated every 10 days.
- Honest about blindness: where it cannot see, it says *cannot assess*.
""")
with b:
    st.markdown("### What GEWS is not")
    st.markdown("""
- A public alerting system. It issues no alerts, under any configuration.
- A real-time flood warning.
- A flood model. It says nothing about depth or reach downstream.
- A guarantee of safety.
""")

st.markdown("### How a lake's risk is produced")
w = C.FUSION_WEIGHTS
st.markdown(f"""
1. **Can it be assessed?** If observability is below {C.OBSERVABILITY_FLOOR:.2f}, or there are fewer than
   {C.MIN_HISTORY_WINDOWS} windows of history, the lake gets no score and the reason is shown.
2. **Score each signal.** The lake's own fitted model scores the window, giving one 0–1 score per signal.
3. **Fuse.** A weighted p-norm with p = {C.FUSION_P} combines the available signals; weights renormalise if one is missing.
4. **Compare with thresholds.** Watch {C.THRESHOLDS['watch']:.2f}, concern {C.THRESHOLDS['concern']:.2f},
   high {C.THRESHOLDS['high']:.2f}, overridable per lake.
5. **Sort.** Lakes with a score are ranked. Lakes without one are listed separately, never ranked as zero.
""")
st.latex(r"\text{risk} = \left(\frac{\sum_i w_i\, s_i^{3}}{\sum_i w_i}\right)^{1/3}")
st.caption("Weights: " + ", ".join(f"{C.SIGNAL_LABELS[k].lower()} {v:.2f}" for k, v in w.items()) + ".")
st.warning("This ranks unusualness, not danger. A small harmless lake behaving oddly can outrank a large "
           "dangerous lake behaving exactly as it always has.")

st.markdown("### Known limits")
st.markdown(f"""
- The positive class has one member, so no pooled precision or recall is computed.
- Lead time depends on the threshold, and so does its false-alarm cost.
- Even with radar the system is blind for part of the monsoon. Worst measured blind spell: {R['radar']['worst_blind_days']} days.
- Lake area comes from a water index over a fixed 4 km window, not a survey. The change is the usable signal.
- Slow, steady growth is invisible: the model refits yearly, so a steadily growing lake stays normal to it.
- A precursor is not a cause. Drift without failure is common.
- The register covers the largest lakes, not necessarily the most dangerous.
""")

st.markdown("### Terms")
st.dataframe({
    "Term": ["GLOF", "Moraine", "Window", "Observability", "Cannot assess", "Walk-forward",
             "Deseasonalise", "One-class", "p-norm fusion", "InSAR"],
    "Meaning": ["Glacial lake outburst flood", "Ridge of loose rock left by a glacier; here, the dam",
                "One 10-day step; 36 per year, the same for every lake",
                f"How much of a window the satellites could see. Below {C.OBSERVABILITY_FLOOR:.2f}, no score",
                "No score was made. Shown hatched grey, never as low risk",
                "Fit on the past, score forward: how it would have run at the time",
                "Compare this July with previous Julys, not with January",
                "Learns only what normal looks like; needs no failures",
                "Combines five scores so agreement counts but a single spike survives",
                "Radar interferometry: millimetre-scale ground movement"],
}, hide_index=True, width="stretch")
