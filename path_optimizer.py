"""Path optimization and ranking for SCM KPI Optimizer."""

from __future__ import annotations

from typing import Any, Literal

import networkx as nx
import pandas as pd

from kpi_analysis import (
    compute_deviations,
    solution_status_from_deviations,
    total_deviation_sum,
)
from utils import KPI_KEYS

AnchorKPI = Literal["cost", "time", "risk"]
KPI = AnchorKPI

RELAXATION_MIN_PCT = 10.0
RELAXATION_MAX_PCT = 25.0
RELAXATION_STEP_PCT = 0.5
MAX_ITERATION_ATTEMPTS = 80


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


_OPTIMAL_FUNCS = {
    "cost": shortest_path_by_cost,
    "time": shortest_path_by_time,
    "risk": shortest_path_by_risk,
}


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


def get_per_kpi_optima(
    graph: nx.DiGraph,
    source: int = 1,
    target: int = 9,
) -> dict[str, float]:
    """Individual optimal totals per KPI (Dijkstra on each weight)."""
    m_cost = calculate_path_metrics(graph, shortest_path_by_cost(graph, source, target))
    m_time = calculate_path_metrics(graph, shortest_path_by_time(graph, source, target))
    m_risk = calculate_path_metrics(graph, shortest_path_by_risk(graph, source, target))
    return {
        "total_cost": m_cost["total_cost"],
        "total_time": m_time["total_time"],
        "total_risk": m_risk["total_risk"],
    }


def enumerate_all_paths(
    graph: nx.DiGraph,
    source: int = 1,
    target: int = 9,
    cutoff: int | None = None,
) -> list[list[int]]:
    """List all simple paths from source to target (networkx.all_simple_paths)."""
    try:
        return list(nx.all_simple_paths(graph, source, target, cutoff=cutoff))
    except nx.NetworkXNoPath:
        return []


def _search_best_relaxed_path(
    graph: nx.DiGraph,
    anchor_kpi: AnchorKPI,
    relaxation_percent: float,
    source: int,
    target: int,
    per_kpi_optima: dict[str, float],
) -> dict[str, Any] | None:
    """
    Among paths satisfying relaxed anchor constraint, pick minimum total deviation.

    total_deviation = cost_dev + time_dev + risk_dev
    """
    anchor_key = f"total_{anchor_kpi}"
    optimal_path = _OPTIMAL_FUNCS[anchor_kpi](graph, source, target)
    anchor_optimal = calculate_path_metrics(graph, optimal_path)[anchor_key]
    anchor_limit = anchor_optimal * (1 + relaxation_percent / 100.0)

    best: dict[str, Any] | None = None
    best_total_dev = float("inf")

    for path in enumerate_all_paths(graph, source, target):
        metrics = calculate_path_metrics(graph, path)
        if metrics[anchor_key] > anchor_limit + 1e-9:
            continue
        deviations = compute_deviations(metrics, per_kpi_optima)
        total_dev = total_deviation_sum(deviations)
        if total_dev < best_total_dev:
            best_total_dev = total_dev
            best = {
                "path": path,
                "metrics": metrics,
                "deviations": deviations,
                "total_deviation": total_dev,
                "solution_status": solution_status_from_deviations(deviations),
                "anchor_optimal": anchor_optimal,
                "anchor_limit": anchor_limit,
                "optimal_anchor_path": optimal_path,
            }
    return best


def find_balanced_path(
    graph: nx.DiGraph,
    anchor_kpi: AnchorKPI,
    relaxation_percent: float = 12.0,
    source: int = 1,
    target: int = 9,
) -> dict[str, Any]:
    """
    Course-methodology balanced path selection.

    1. Dijkstra: absolute optimum for anchor KPI.
    2. Relaxation: allowed_anchor = optimal * (1 + relaxation%/100).
    3. Enumerate all simple paths; keep paths with anchor <= allowed.
    4. For each candidate: compute totals and deviations vs per-KPI optima.
    5. Select path with minimum sum of deviations (cost + time + risk).
    6. Classify solution: all dev <=20% accepted; all <=25% conditional; else rejected.
    7. If no acceptable solution: iterative loop — increase relaxation or try other anchors.
    """
    per_kpi_optima = get_per_kpi_optima(graph, source, target)
    user_relax = max(RELAXATION_MIN_PCT, min(RELAXATION_MAX_PCT, float(relaxation_percent)))

    anchors_order: list[AnchorKPI] = [anchor_kpi] + [
        a for a in ("cost", "time", "risk") if a != anchor_kpi
    ]

    best_acceptable: dict[str, Any] | None = None
    best_fallback: dict[str, Any] | None = None
    iterations = 0
    used_anchor = anchor_kpi
    used_relax = user_relax

    for anchor in anchors_order:
        relax = user_relax
        while relax <= RELAXATION_MAX_PCT + 1e-9:
            iterations += 1
            if iterations > MAX_ITERATION_ATTEMPTS:
                break
            cand = _search_best_relaxed_path(
                graph, anchor, relax, source, target, per_kpi_optima
            )
            used_anchor = anchor
            used_relax = relax
            if cand is None:
                relax += RELAXATION_STEP_PCT
                continue

            if best_fallback is None or cand["total_deviation"] < best_fallback["total_deviation"]:
                best_fallback = {**cand, "anchor_kpi": anchor, "relaxation_percent": relax}

            if cand["solution_status"] in ("accepted", "conditionally_accepted"):
                if (
                    best_acceptable is None
                    or cand["total_deviation"] < best_acceptable["total_deviation"]
                ):
                    best_acceptable = {**cand, "anchor_kpi": anchor, "relaxation_percent": relax}
                break

            relax += RELAXATION_STEP_PCT

        if best_acceptable is not None:
            break
        if iterations > MAX_ITERATION_ATTEMPTS:
            break

    chosen = best_acceptable if best_acceptable is not None else best_fallback
    if chosen is None:
        optimal_path = _OPTIMAL_FUNCS[anchor_kpi](graph, source, target)
        metrics = calculate_path_metrics(graph, optimal_path)
        deviations = compute_deviations(metrics, per_kpi_optima)
        chosen = {
            "path": optimal_path,
            "metrics": metrics,
            "deviations": deviations,
            "total_deviation": total_deviation_sum(deviations),
            "solution_status": solution_status_from_deviations(deviations),
            "anchor_optimal": metrics[f"total_{anchor_kpi}"],
            "anchor_limit": metrics[f"total_{anchor_kpi}"],
            "optimal_anchor_path": optimal_path,
            "anchor_kpi": anchor_kpi,
            "relaxation_percent": user_relax,
        }

    return {
        "anchor_kpi": used_anchor,
        "relaxation_percent": round(used_relax, 1),
        "requested_anchor_kpi": anchor_kpi,
        "requested_relaxation_percent": user_relax,
        "anchor_optimal": chosen["anchor_optimal"],
        "anchor_limit": chosen["anchor_limit"],
        "optimal_anchor_path": chosen["optimal_anchor_path"],
        "balanced_path": chosen["path"],
        "balanced_metrics": {
            "total_cost": round(chosen["metrics"]["total_cost"], 2),
            "total_time": round(chosen["metrics"]["total_time"], 2),
            "total_risk": round(chosen["metrics"]["total_risk"], 2),
            "total_deviation": chosen["total_deviation"],
        },
        "deviations": chosen["deviations"],
        "solution_status": chosen["solution_status"],
        "per_kpi_optima": per_kpi_optima,
        "iterations": iterations,
    }


def rank_paths(
    graph: nx.DiGraph,
    paths: list[list[int]],
    source: int = 1,
    target: int = 9,
) -> pd.DataFrame:
    """Rank paths by total KPI deviation (lower is better)."""
    per_kpi_optima = get_per_kpi_optima(graph, source, target)
    rows: list[dict[str, Any]] = []
    for path in paths:
        m = calculate_path_metrics(graph, path)
        devs = compute_deviations(m, per_kpi_optima)
        rows.append(
            {
                "path": " → ".join(map(str, path)),
                "nodes": path,
                "total_cost": round(m["total_cost"], 2),
                "total_time": round(m["total_time"], 2),
                "total_risk": round(m["total_risk"], 2),
                "total_deviation": total_deviation_sum(devs),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(["total_deviation", "total_cost"]).reset_index(drop=True)


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
