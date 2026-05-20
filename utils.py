"""Shared helpers for SCM KPI Optimizer."""

from __future__ import annotations

from typing import Any

import networkx as nx
import pandas as pd

KPI_KEYS = ("cost", "time", "risk")

KPI_RU = {"cost": "затраты", "time": "время", "risk": "риск"}

STATUS_RU = {
    "accepted": "принято",
    "conditionally_accepted": "условно принято",
    "rejected": "отклонено",
}

OVERALL_RU = {
    "accepted": "принято",
    "conditionally_accepted": "условно принято",
    "rejected": "отклонено",
}


def edge_label(cost: float, time: float, risk: float) -> str:
    """Format edge KPI label for visualizations."""
    return f"з:{cost:.1f}/в:{time:.1f}/р:{risk:.1f}"


def graph_to_edge_records(graph: nx.DiGraph) -> list[dict[str, Any]]:
    """Convert graph edges to a list of dicts for tables and export."""
    records: list[dict[str, Any]] = []
    for u, v, data in graph.edges(data=True):
        records.append(
            {
                "от": u,
                "до": v,
                "затраты": data.get("cost", 0),
                "время": data.get("time", 0),
                "риск": data.get("risk", 0),
            }
        )
    return records


def edges_to_internal(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map Russian edge records back to internal keys (for compatibility)."""
    out = []
    for e in records:
        out.append(
            {
                "source": e.get("от", e.get("source")),
                "target": e.get("до", e.get("target")),
                "cost": e.get("затраты", e.get("cost")),
                "time": e.get("время", e.get("time")),
                "risk": e.get("риск", e.get("risk")),
            }
        )
    return out


def localize_paths_df(df: pd.DataFrame) -> pd.DataFrame:
    """Rename path ranking columns for UI."""
    if df.empty:
        return df
    rename = {
        "path": "маршрут",
        "total_cost": "затраты",
        "total_time": "время",
        "total_risk": "риск",
        "total_deviation": "сумм. откл., %",
    }
    cols = {k: v for k, v in rename.items() if k in df.columns}
    out = df.rename(columns=cols)
    if "nodes" in out.columns:
        out = out.drop(columns=["nodes"])
    return out


def localize_optimal_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    rename = {
        "kpi": "KPI",
        "path": "маршрут",
        "total_cost": "затраты",
        "total_time": "время",
        "total_risk": "риск",
    }
    out = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    if "KPI" in out.columns:
        out["KPI"] = out["KPI"].map(lambda x: KPI_RU.get(str(x), x))
    return out


def localize_balance_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    rename = {
        "kpi": "KPI",
        "current": "сейчас",
        "optimal": "оптимум",
        "deviation_pct": "отклонение %",
        "status": "статус",
    }
    out = out.rename(columns={k: v for k, v in rename.items() if k in out.columns})
    if "KPI" in out.columns:
        out["KPI"] = out["KPI"].map(lambda x: KPI_RU.get(str(x), x))
    if "статус" in out.columns:
        out["статус"] = out["статус"].map(lambda s: STATUS_RU.get(str(s), s))
    return out


def graph_summary_ru(summary: dict[str, Any]) -> dict[str, str]:
    """Human-readable graph summary for metrics/PDF."""
    return {
        "узлов": str(summary.get("nodes", 0)),
        "рёбер": str(summary.get("edges", 0)),
        "DAG": "да" if summary.get("is_dag") else "нет",
        "путь": "есть" if summary.get("has_path") else "нет",
    }


def ensure_dag(graph: nx.DiGraph) -> bool:
    """Return True if graph is a directed acyclic graph."""
    return nx.is_directed_acyclic_graph(graph)
