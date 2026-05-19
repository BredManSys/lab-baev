"""Streamlit session state persistence for SCM KPI Optimizer."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import networkx as nx
import streamlit as st

from graph_generator import graph_summary
from utils import graph_to_edge_records

SESSION_VERSION = 1

DEFAULT_STATE: dict[str, Any] = {
    "graph": None,
    "nodes": [],
    "edges": [],
    "weights": {},
    "optimization_results": {},
    "selected_anchor_kpi": "cost",
    "relaxation_percent": 12.0,
    "reports": {},
    "highlight_path": [],
    "source": 1,
    "target": 9,
}


def _graph_to_serializable(graph: nx.DiGraph | None) -> dict[str, Any] | None:
    if graph is None:
        return None
    return {
        "nodes": list(graph.nodes()),
        "edges": [
            {
                "source": u,
                "target": v,
                "cost": d.get("cost"),
                "time": d.get("time"),
                "risk": d.get("risk"),
            }
            for u, v, d in graph.edges(data=True)
        ],
    }


def _graph_from_serializable(data: dict[str, Any] | None) -> nx.DiGraph | None:
    if not data:
        return None
    g = nx.DiGraph()
    for n in data.get("nodes", []):
        g.add_node(n)
    for e in data.get("edges", []):
        g.add_edge(
            e["source"],
            e["target"],
            cost=e.get("cost", 1),
            time=e.get("time", 1),
            risk=e.get("risk", 1),
        )
    return g


def initialize_session() -> None:
    """Initialize session_state keys with defaults."""
    for key, value in DEFAULT_STATE.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _sync_graph_derived(graph: nx.DiGraph | None) -> None:
    """Update nodes, edges, weights from graph object."""
    if graph is None:
        st.session_state["nodes"] = []
        st.session_state["edges"] = []
        st.session_state["weights"] = {}
        return
    st.session_state["nodes"] = list(graph.nodes())
    st.session_state["edges"] = graph_to_edge_records(graph)
    st.session_state["weights"] = {
        f"{e['source']}-{e['target']}": {
            "cost": e["cost"],
            "time": e["time"],
            "risk": e["risk"],
        }
        for e in st.session_state["edges"]
    }


def set_graph(graph: nx.DiGraph | None) -> None:
    """Store graph in session and sync derived fields."""
    st.session_state["graph"] = graph
    _sync_graph_derived(graph)


def save_session_to_json() -> str:
    """Serialize session to JSON string for download."""
    graph = st.session_state.get("graph")
    payload = {
        "version": SESSION_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "graph": _graph_to_serializable(graph),
        "optimization_results": st.session_state.get("optimization_results", {}),
        "selected_anchor_kpi": st.session_state.get("selected_anchor_kpi", "cost"),
        "relaxation_percent": st.session_state.get("relaxation_percent", 12.0),
        "reports": st.session_state.get("reports", {}),
        "highlight_path": st.session_state.get("highlight_path", []),
        "source": st.session_state.get("source", 1),
        "target": st.session_state.get("target", 9),
        "summary": graph_summary(graph) if graph is not None else {},
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def load_session_from_json(json_str: str) -> tuple[bool, str]:
    """Load session from JSON string. Returns (success, message)."""
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {e}"

    if data.get("version") != SESSION_VERSION:
        return False, f"Unsupported session version (expected {SESSION_VERSION})."

    graph = _graph_from_serializable(data.get("graph"))
    if graph is not None and not nx.is_directed_acyclic_graph(graph):
        return False, "Loaded graph contains cycles (not a DAG)."

    set_graph(graph)
    st.session_state["optimization_results"] = data.get("optimization_results", {})
    st.session_state["selected_anchor_kpi"] = data.get("selected_anchor_kpi", "cost")
    st.session_state["relaxation_percent"] = float(data.get("relaxation_percent", 12.0))
    st.session_state["reports"] = data.get("reports", {})
    st.session_state["highlight_path"] = data.get("highlight_path", [])
    st.session_state["source"] = int(data.get("source", 1))
    st.session_state["target"] = int(data.get("target", 9))
    return True, "Session loaded successfully."


def reset_session() -> None:
    """Clear session to defaults."""
    for key, value in DEFAULT_STATE.items():
        st.session_state[key] = value if key != "graph" else None
    _sync_graph_derived(None)


def render_session_io() -> None:
    """Sidebar widgets: download / upload session JSON."""
    st.sidebar.subheader("Session")
    st.sidebar.download_button(
        "Download session (.json)",
        data=save_session_to_json(),
        file_name="scm_kpi_session.json",
        mime="application/json",
    )
    uploaded = st.sidebar.file_uploader("Upload session JSON", type=["json"])
    if uploaded is not None:
        ok, msg = load_session_from_json(uploaded.getvalue().decode("utf-8"))
        if ok:
            st.sidebar.success(msg)
        else:
            st.sidebar.error(msg)
