"""Shared, cached access to the dataset and the selected window."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .data import Dataset, load


@st.cache_resource(show_spinner="Reading pipeline output…")
def get_data() -> Dataset:
    return load()


def current_window(ds: Dataset) -> pd.Timestamp:
    w = st.session_state.get("window")
    return pd.Timestamp(w) if w is not None else ds.windows[-1]
