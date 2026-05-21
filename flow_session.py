"""Состояние сессии Streamlit для ЧАСТИ 2 (потоки), отдельно от ЧАСТИ 1."""

from __future__ import annotations

from typing import Any

import networkx as nx
import streamlit as st

FLOW_DEFAULT_STATE: dict[str, Any] = {
    "flow_graph": None,
    "flow_source": 0,
    "flow_sink": 4,
    "flow_max_result": None,
    "flow_mcf_result": None,
    "flow_viz_backend": "Graphviz",
}


def initialize_flow_session() -> None:
    """Инициализация ключей ЧАСТИ 2 без затрагивания ЧАСТИ 1."""
    for key, value in FLOW_DEFAULT_STATE.items():
        if key not in st.session_state:
            st.session_state[key] = value


def set_flow_graph(graph: nx.DiGraph | None) -> None:
    st.session_state["flow_graph"] = graph
    st.session_state["flow_max_result"] = None
    st.session_state["flow_mcf_result"] = None


def reset_flow_session() -> None:
    for key, value in FLOW_DEFAULT_STATE.items():
        st.session_state[key] = value if key != "flow_graph" else None
