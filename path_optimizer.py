"""Path optimization and ranking for SCM KPI Optimizer."""

from __future__ import annotations

from typing import Any, Literal

import networkx as nx
import pandas as pd

from utils import KPI_KEYS

AnchorKPI = Literal["cost", "time", "risk"]
KPI = AnchorKPI


def _weight_attr(kpi: KPI) -> str:
    return kpi


def shortest_path_by_cost(graph: nx.DiGraph, source: int = 1, target: int = 9) -> list[int]:
    """Shortest path minimizing total cost (Dijkstra)."""
    return nx.shortest_path(graph, source, target, weight="cost")


def shortest_path_by_time(graph: nx.DiGraph, source: int = 1, target: int = 9) -> list[int]:
    """Shortest path minimizing total time (Dijkstra)."""
    return nx.shortest_path(graph, source, target, weight="time")


def shortest_path_by_risk(graph: nx.DiGraph, source: int = 1, target: int = 9) -> list[int]:
    """Shortest path minimizing total risk (Dijkstra)."""
    return nx.shortest_path(graph, source, target, weight="risk")


def calculate_path_metrics(graph: nx.DiGraph, path: list[int]) -> dict[str, float]:
    """Sum cost, time, and risk along a node path."""
    total_cost = total_time = total_risk = 0.0
    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        data = graph[u][v]
        total_cost += float(data.get("cost", 0))
        total_time += float(data.get("time", 0))
        total_risk += float(data.get("risk", 0))
    return {"total_cost": total_cost, "total_time": total_time, "total_risk": total_risk}


def enumerate_all_paths(
    graph: nx.DiGraph,
    source: int = 1,
    target: int = 9,
    cutoff: int | None = None,
) -> list[list[int]]:
    """List all simple paths from source to target."""
    try:
        return list(nx.all_simple_paths(graph, source, target, cutoff=cutoff))
    except nx.NetworkXNoPath:
        return []


def _balance_score(metrics: dict[str, float]) -> float:
    """Lower is better: normalized spread across KPIs."""
    values = [metrics["total_cost"], metrics["total_time"], metrics["total_risk"]]
    if max(values) == 0:
        return 0.0
    normalized = [v / max(values) for v in values]
    return float(sum(normalized) / len(normalized))


def find_balanced_path(
    graph: nx.DiGraph,
    anchor_kpi: AnchorKPI,
    relaxation_percent: float = 12.0,
    source: int = 1,
    target: int = 9,
) -> dict[str, Any]:
    """
    Find path with best balance among paths within relaxed anchor KPI bound.

    Anchor optimal path is computed via Dijkstra on anchor weight.
    Other KPIs may exceed optimal by at most relaxation_percent (%).
    Among feasible paths, pick lowest balance score.
    """
    optimal_funcs = {
        "cost": shortest_path_by_cost,
        "time": shortest_path_by_time,
        "risk": shortest_path_by_risk,
    }
    optimal_path = optimal_funcs[anchor_kpi](graph, source, target)
    optimal_metrics = calculate_path_metrics(graph, optimal_path)
    anchor_key = f"total_{anchor_kpi}"
    anchor_optimal = optimal_metrics[anchor_key]
    anchor_limit = anchor_optimal * (1 + relaxation_percent / 100.0)

    candidates: list[dict[str, Any]] = []
    for path in enumerate_all_paths(graph, source, target):
        metrics = calculate_path_metrics(graph, path)
        if metrics[anchor_key] <= anchor_limit + 1e-9:
            metrics["balance_score"] = _balance_score(metrics)
            metrics["path"] = path
            candidates.append(metrics)

    if not candidates:
        best = {**optimal_metrics, "balance_score": _balance_score(optimal_metrics), "path": optimal_path}
    else:
        best = min(candidates, key=lambda m: m["balance_score"])

    return {
        "anchor_kpi": anchor_kpi,
        "relaxation_percent": relaxation_percent,
        "anchor_optimal": anchor_optimal,
        "anchor_limit": anchor_limit,
        "optimal_anchor_path": optimal_path,
        "balanced_path": best["path"],
        "balanced_metrics": {k: best[k] for k in ("total_cost", "total_time", "total_risk", "balance_score")},
    }


def rank_paths(graph: nx.DiGraph, paths: list[list[int]]) -> pd.DataFrame:
    """Build ranked DataFrame of paths with KPI totals and balance score."""
    rows: list[dict[str, Any]] = []
    for path in paths:
        m = calculate_path_metrics(graph, path)
        rows.append(
            {
                "path": " → ".join(map(str, path)),
                "nodes": path,
                "total_cost": round(m["total_cost"], 2),
                "total_time": round(m["total_time"], 2),
                "total_risk": round(m["total_risk"], 2),
                "balance_score": round(_balance_score(m), 4),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(["balance_score", "total_cost"]).reset_index(drop=True)


def optimal_paths_summary(graph: nx.DiGraph, source: int = 1, target: int = 9) -> pd.DataFrame:
    """DataFrame of single-KPI optimal paths."""
    rows = []
    for kpi, func in (
        ("cost", shortest_path_by_cost),
        ("time", shortest_path_by_time),
        ("risk", shortest_path_by_risk),
    ):
        try:
            path = func(graph, source, target)
            m = calculate_path_metrics(graph, path)
            rows.append(
                {
                    "kpi": kpi,
                    "path": " → ".join(map(str, path)),
                    "total_cost": m["total_cost"],
                    "total_time": m["total_time"],
                    "total_risk": m["total_risk"],
                }
            )
        except nx.NetworkXNoPath:
            rows.append({"kpi": kpi, "path": "N/A", "total_cost": None, "total_time": None, "total_risk": None})
    return pd.DataFrame(rows)
