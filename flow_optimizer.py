"""Расчёт maximum flow и minimum cost flow (NetworkX)."""

from __future__ import annotations

from typing import Any

import networkx as nx
import pandas as pd

from flow_analysis import inflow_at_node, outflow_at_node, supply_from_demands


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
            cost = float(data.get("cost", 0))
            row["стоимость"] = cost
            row["затраты на ребре"] = round(flow * cost, 4)
        records.append(row)
    return records


def compute_maximum_flow(
    graph: nx.DiGraph,
    source: int,
    sink: int,
) -> dict[str, Any]:
    """
    Максимальный поток nx.maximum_flow(..., capacity="capacity").
    """
    if source not in graph or sink not in graph:
        raise ValueError(f"Узлы s={source} или t={sink} отсутствуют в графе.")

    flow_value, flow_dict = nx.maximum_flow(
        graph,
        _s=source,
        _t=sink,
        capacity="capacity",
    )
    flow_value = float(flow_value)

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
        "flow_value": flow_value,
        "flow_dict": flow_dict,
        "flow_from_source": outflow_at_node(flow_dict, source) - inflow_at_node(flow_dict, graph, source),
        "flow_to_sink": inflow_at_node(flow_dict, graph, sink) - outflow_at_node(flow_dict, sink),
        "edge_df": pd.DataFrame(edge_records),
        "bottlenecks_df": pd.DataFrame(bottlenecks),
        "source": source,
        "sink": sink,
    }


def compute_min_cost_flow(
    graph: nx.DiGraph,
    source: int,
    sink: int,
) -> dict[str, Any]:
    """
    Поток минимальной стоимости: nx.min_cost_flow(..., demand, capacity, weight=cost).
    """
    if source not in graph or sink not in graph:
        raise ValueError(f"Узлы s={source} или t={sink} отсутствуют в графе.")

    demand_sum = sum(float(graph.nodes[n].get("demand", 0)) for n in graph.nodes())
    if abs(demand_sum) > 1e-5:
        raise ValueError(f"Сумма demand должна быть 0 (сейчас {demand_sum:.6f}).")

    try:
        flow_dict = nx.min_cost_flow(
            graph,
            demand="demand",
            capacity="capacity",
            weight="cost",
        )
    except nx.NetworkXUnfeasible as e:
        raise ValueError(f"Задача потока неразрешима: {e}") from e

    total_cost = float(nx.cost_of_flow(graph, flow_dict, weight="cost"))
    flow_from_source = outflow_at_node(flow_dict, source)
    flow_to_sink = inflow_at_node(flow_dict, graph, sink)
    supply = supply_from_demands(graph, source, sink)

    edge_records = _edge_flow_records(graph, flow_dict, include_cost=True)

    return {
        "flow_dict": flow_dict,
        "total_cost": round(total_cost, 4),
        "edge_df": pd.DataFrame(edge_records),
        "source": source,
        "sink": sink,
        "flow_from_source": flow_from_source,
        "flow_to_sink": flow_to_sink,
        "supply": supply,
    }
