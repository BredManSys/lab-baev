"""Shared helpers for SCM KPI Optimizer."""

from __future__ import annotations

from typing import Any

import networkx as nx

KPI_KEYS = ("cost", "time", "risk")


def edge_label(cost: float, time: float, risk: float) -> str:
    """Format edge KPI label for visualizations."""
    return f"c:{cost:.1f}/t:{time:.1f}/r:{risk:.1f}"


def graph_to_edge_records(graph: nx.DiGraph) -> list[dict[str, Any]]:
    """Convert graph edges to a list of dicts for tables and export."""
    records: list[dict[str, Any]] = []
    for u, v, data in graph.edges(data=True):
        records.append(
            {
                "source": u,
                "target": v,
                "cost": data.get("cost", 0),
                "time": data.get("time", 0),
                "risk": data.get("risk", 0),
            }
        )
    return records


def ensure_dag(graph: nx.DiGraph) -> bool:
    """Return True if graph is a directed acyclic graph."""
    return nx.is_directed_acyclic_graph(graph)
