"""GEWS dashboard entry point.

    streamlit run app/app.py
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

st.set_page_config(page_title="GEWS watch-list", page_icon="🏔️", layout="wide",
                   initial_sidebar_state="expanded")

from gews_ui import theme  # noqa: E402  (registers plotly template)
from gews_ui.data import window_label  # noqa: E402
from gews_ui.state import get_data  # noqa: E402

st.markdown(theme.CSS, unsafe_allow_html=True)

ds = get_data()

pages = [
    st.Page("views/watchlist.py", title="Watch-list", icon=":material/list_alt:", default=True),
    st.Page("views/lake.py", title="Lake detail", icon=":material/water:"),
    st.Page("views/seeing.py", title="What we can see", icon=":material/satellite_alt:"),
    st.Page("views/evaluation.py", title="How it was tested", icon=":material/science:"),
    st.Page("views/about.py", title="Scope and limits", icon=":material/info:"),
]
nav = st.navigation(pages)

with st.sidebar:
    st.markdown('<div class="gews-serif" style="font-size:1.6rem;font-weight:700;line-height:1">GEWS</div>'
                '<div style="opacity:.75;font-size:.85rem;margin-bottom:1rem">Glacial lake outburst '
                'early-warning, 41 Himalayan lakes</div>', unsafe_allow_html=True)
    windows = ds.windows
    if "window" not in st.session_state:
        st.session_state["window"] = windows[-1]
    st.select_slider("10-day window", options=windows, key="window", format_func=window_label,
                     help="All pages show this window. The newest window is selected when the app opens.")
    st.caption(f"Data version: {ds.data_version}")
    st.caption(f"Source: {ds.source}")
    if ds.is_demo:
        st.caption("Demo mode: synthetic data")

nav.run()
