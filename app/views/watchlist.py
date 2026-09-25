import streamlit as st

from gews_ui import charts
from gews_ui.components import demo_banner, page_header, scope_banner, summary_strip, watchlist_table
from gews_ui.data import window_label, watchlist
from gews_ui.state import current_window, get_data

ds = get_data()
window = current_window(ds)
ranked, blind = watchlist(ds, window)

page_header(f"Watch-list for {window_label(window)}",
            "Each lake is compared only with its own past. The ranking shows which lakes are behaving "
            "most unlike themselves this window, not which lakes are most dangerous.")
scope_banner()
demo_banner(ds)

at_watch = int((ranked["level"] != "normal").sum())
summary_strip([
    ("lakes scored", str(len(ranked))),
    ("cannot assess", str(len(blind))),
    ("at watch or above", str(at_watch)),
    ("highest risk", f"{ranked['risk'].max():.2f}" if len(ranked) else "none"),
])

watchlist_table(ranked, blind)

st.markdown("### Where they are")
left, right = st.columns([2, 1], gap="large")
with left:
    st.plotly_chart(charts.lake_map(ranked, blind), width="stretch", config={"displayModeBar": False})
with right:
    st.markdown("**Open a lake**")
    options = list(ranked["lake_id"]) + list(blind["lake_id"])
    names = dict(zip(ranked["lake_id"], ranked["name"])) | dict(zip(blind["lake_id"], blind["name"]))
    choice = st.selectbox("Lake", options, format_func=lambda i: names[i], label_visibility="collapsed")
    if st.button("Open lake detail", type="primary", width="stretch"):
        st.session_state["lake_id"] = choice
        st.switch_page("views/lake.py")
    st.caption("Circle size and colour follow the risk score. Grey circles are lakes with no score this window.")
