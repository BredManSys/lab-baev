"""Расчёт maximum flow и minimum cost flow (NetworkX)."""

from __future__ import annotations

from typing import Any

import networkx as nx
import pandas as pd

from flow_generator import DEFAULT_SINK, DEFAULT_SOURCE


def _edge_flow_records(
    graph: nx.DiGraph,
    flow_dict: dict[int, dict[int, float]],
    include_cost: bool = False,
) -> list[dict[str, Any]]:
    """Распределение потока по рёбрам (только flow > 0)."""
    records: list[dict[str, Any]] = []
    for u, v, data in graph.edges(data=True):
        flow = float(flow_dict.get(u, {}).get(v, 0.0))
        if flow <= 1e-9:
            continue
        row: dict[str, Any] = {
            "от": u,
            "до": v,
            "поток": round(flow, 4),
            "ёмкость": float(data.get("capacity", 0)),
        }
        if include_cost:
            row["стоимость"] = float(data.get("cost", 0))
            row["затраты на ребре"] = round(flow * float(data.get("cost", 0)), 4)
        records.append(row)
    return records


def compute_maximum_flow(
    graph: nx.DiGraph,
    source: int = DEFAULT_SOURCE,
    sink: int = DEFAULT_SINK,
) -> dict[str, Any]:
    """
    Максимальный поток nx.maximum_flow.

    Возвращает value, flow_dict, таблицу рёбер, узкие места.
    """
    flow_value, flow_dict = nx.maximum_flow(
        graph,
        _s=source,
        _t=sink,
        capacity="capacity",
    )
    edge_records = _edge_flow_records(graph, flow_dict)
    bottlenecks: list[dict[str, Any]] = []
    for u, v, data in graph.edges(data=True):
        flow = float(flow_dict.get(u, {}).get(v, 0.0))
        cap = float(data.get("capacity", 0))
        if cap > 0 and abs(flow - cap) < 1e-6:
            bottlenecks.append(
                {
                    "от": u,
                    "до": v,
                    "поток": round(flow, 4),
                    "ёмкость": cap,
                }
            )

    return {
        "flow_value": float(flow_value),
        "flow_dict": flow_dict,
        "edge_df": pd.DataFrame(edge_records),
        "bottlenecks_df": pd.DataFrame(bottlenecks),
        "source": source,
        "sink": sink,
    }


def compute_min_cost_flow(graph: nx.DiGraph) -> dict[str, Any]:
    """
    Поток минимальной стоимости (nx.min_cost_flow).

    Узлы: demand; рёбра: capacity, cost (weight).
    """
    try:
        flow_dict = nx.min_cost_flow(
            graph,
            demand="demand",
            capacity="capacity",
            weight="cost",
        )
    except nx.NetworkXUnfeasible as e:
        raise ValueError(f"Задача потока неразрешима: {e}") from e

    total_cost = 0.0
    for u in flow_dict:
        for v, flow in flow_dict[u].items():
            if flow > 1e-9 and graph.has_edge(u, v):
                total_cost += flow * float(graph[u][v].get("cost", 0))

    edge_records = _edge_flow_records(graph, flow_dict, include_cost=True)

    return {
        "flow_dict": flow_dict,
        "total_cost": round(total_cost, 4),
        "edge_df": pd.DataFrame(edge_records),
    }


def localize_max_flow_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    rename = {
        "from": "от",
        "to": "до",
        "flow": "поток",
        "capacity": "ёмкость",
    }
    return df.rename(columns={k: v for k, v in rename.items() if k in df.columns})


def localize_min_cost_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    rename = {
        "edge_cost": "затраты на ребре",
    }
    return df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
