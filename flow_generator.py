"""Случайная генерация сети потоков для ЧАСТИ 2 (Maximum / Min Cost Flow)."""

from __future__ import annotations

import random
from typing import Any

import networkx as nx

DEFAULT_SOURCE = 0
DEFAULT_SINK = 4
DEFAULT_NUM_NODES = 5
MIN_CAPACITY = 5
MAX_CAPACITY = 40
MIN_COST = 1
MAX_COST = 15


def create_empty_flow_graph() -> nx.DiGraph:
    """Пустой ориентированный граф с атрибутами потоковой сети."""
    return nx.DiGraph()


def _assign_demands(
    graph: nx.DiGraph,
    source: int,
    sink: int,
    supply_amount: float,
) -> dict[int, float]:
    """
    Спрос/предложение (конвенция NetworkX min_cost_flow):
    source — отрицательный demand (узел отдаёт поток),
    sink — положительный (узел принимает).
    """
    demands: dict[int, float] = {n: 0.0 for n in graph.nodes()}
    demands[source] = -float(supply_amount)
    demands[sink] = float(supply_amount)
    for n, d in demands.items():
        graph.nodes[n]["demand"] = d
    return demands


def validate_flow_network(
    graph: nx.DiGraph,
    source: int = DEFAULT_SOURCE,
    sink: int = DEFAULT_SINK,
) -> tuple[bool, list[str]]:
    """Проверка корректности сети для max flow и min cost flow."""
    issues: list[str] = []
    if graph.number_of_nodes() == 0:
        return False, ["Граф пуст."]
    if source not in graph or sink not in graph:
        issues.append(f"Источник {source} или сток {sink} отсутствуют в графе.")
    if not nx.has_path(graph, source, sink):
        issues.append(f"Нет пути от {source} к {sink}.")
    for u, v, data in graph.edges(data=True):
        cap = data.get("capacity")
        if cap is None or float(cap) <= 0:
            issues.append(f"Ребро ({u},{v}): некорректная ёмкость.")
        cost = data.get("cost")
        if cost is None or float(cost) < 0:
            issues.append(f"Ребро ({u},{v}): некорректная стоимость.")
    total_demand = sum(float(graph.nodes[n].get("demand", 0)) for n in graph.nodes())
    if abs(total_demand) > 1e-6:
        issues.append(f"Сумма demands должна быть 0 (сейчас {total_demand:.4f}).")
    return len(issues) == 0, issues


def flow_network_summary(
    graph: nx.DiGraph,
    source: int = DEFAULT_SOURCE,
    sink: int = DEFAULT_SINK,
) -> dict[str, Any]:
    """Сводка по сети потоков."""
    ok, issues = validate_flow_network(graph, source, sink)
    demands = {n: float(graph.nodes[n].get("demand", 0)) for n in graph.nodes()}
    caps = [float(d.get("capacity", 0)) for _, _, d in graph.edges(data=True)]
    costs = [float(d.get("cost", 0)) for _, _, d in graph.edges(data=True)]
    return {
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "source": source,
        "sink": sink,
        "has_path": nx.has_path(graph, source, sink) if graph.number_of_nodes() else False,
        "is_valid": ok,
        "validation_issues": issues,
        "supply_amount": abs(demands.get(source, 0)),
        "total_capacity_out_source": sum(
            float(graph[source][v].get("capacity", 0))
            for v in graph.successors(source)
        ),
        "min_capacity": min(caps) if caps else 0,
        "max_capacity": max(caps) if caps else 0,
        "min_cost": min(costs) if costs else 0,
        "max_cost": max(costs) if costs else 0,
        "demands": demands,
    }


def generate_random_flow_network(
    num_nodes: int = DEFAULT_NUM_NODES,
    edge_probability: float = 0.45,
    source: int = DEFAULT_SOURCE,
    sink: int | None = None,
    min_capacity: float = MIN_CAPACITY,
    max_capacity: float = MAX_CAPACITY,
    min_cost: float = MIN_COST,
    max_cost: float = MAX_COST,
    random_seed: int | None = None,
) -> nx.DiGraph:
    """
    Случайная ориентированная сеть потоков (0-based узлы).

    Гарантии:
    - узлы 0 .. num_nodes-1;
    - опорный путь source → ... → sink;
    - у рёбер capacity и cost;
    - demands: предложение в source, спрос в sink (сумма 0).
    """
    if num_nodes < 3:
        raise ValueError("num_nodes must be at least 3")
    if sink is None:
        sink = num_nodes - 1
    if source >= sink:
        raise ValueError("source must be less than sink for default topology")

    rng = random.Random(random_seed)
    graph = nx.DiGraph()
    graph.add_nodes_from(range(num_nodes))

    def add_flow_edge(u: int, v: int) -> None:
        if graph.has_edge(u, v):
            return
        capacity = int(round(rng.uniform(min_capacity, max_capacity)))
        cost = int(round(rng.uniform(min_cost, max_cost)))
        graph.add_edge(u, v, capacity=capacity, cost=cost, weight=cost)

    # Опорный путь source → sink
    path = list(range(source, sink + 1))
    for i in range(len(path) - 1):
        add_flow_edge(path[i], path[i + 1])

    # Дополнительные рёбра (u < v — без циклов «назад», сеть остаётся понятной)
    for u in range(num_nodes):
        for v in range(u + 2, num_nodes):
            if u == v:
                continue
            if rng.random() < edge_probability:
                add_flow_edge(u, v)

    # Гарантия пути source → sink
    if not nx.has_path(graph, source, sink):
        for i in range(source, sink):
            add_flow_edge(i, i + 1)

    # Объём предложения/спроса — не больше максимального потока (иначе min cost flow неразрешим)
    try:
        max_flow_value, _ = nx.maximum_flow(
            graph, _s=source, _t=sink, capacity="capacity"
        )
    except nx.NetworkXError:
        max_flow_value = 0.0
    max_flow_value = float(max_flow_value)
    if max_flow_value < 1e-6:
        raise RuntimeError("Сеть не пропускает поток от источника к стоку.")

    # Берём 60–95% от max flow, чтобы задача min cost была разрешима с запасом
    supply = int(round(rng.uniform(max_flow_value * 0.6, max_flow_value * 0.95)))
    supply = max(1, min(supply, int(max_flow_value)))

    _assign_demands(graph, source, sink, supply)

    ok, issues = validate_flow_network(graph, source, sink)
    if not ok:
        raise RuntimeError(f"Сгенерированная сеть некорректна: {'; '.join(issues)}")

    return graph


def flow_graph_to_edge_records(graph: nx.DiGraph) -> list[dict[str, Any]]:
    """Таблица рёбер для UI."""
    records: list[dict[str, Any]] = []
    for u, v, data in graph.edges(data=True):
        records.append(
            {
                "от": u,
                "до": v,
                "ёмкость": data.get("capacity", 0),
                "стоимость": data.get("cost", 0),
            }
        )
    return records


def flow_sink_for_nodes(num_nodes: int, source: int = DEFAULT_SOURCE) -> int:
    """Сток по умолчанию — последний узел (0 … n−1)."""
    if num_nodes < 2:
        raise ValueError("num_nodes must be at least 2")
    sink = num_nodes - 1
    if source >= sink:
        raise ValueError("source must be less than sink")
    return sink


def flow_demands_to_records(
    graph: nx.DiGraph,
    source: int = DEFAULT_SOURCE,
    sink: int | None = None,
) -> list[dict[str, Any]]:
    """Таблица demands с ролями узлов для UI."""
    if sink is None and graph.number_of_nodes():
        sink = max(graph.nodes())
    records: list[dict[str, Any]] = []
    for n in sorted(graph.nodes()):
        d = float(graph.nodes[n].get("demand", 0))
        if n == source:
            role = "источник (s)"
            meaning = f"отдаёт {abs(d):.0f} ед." if d < 0 else "—"
        elif sink is not None and n == sink:
            role = "сток (t)"
            meaning = f"принимает {d:.0f} ед." if d > 0 else "—"
        elif abs(d) < 1e-9:
            role = "транзит"
            meaning = "баланс 0 (вход = выход)"
        elif d < 0:
            role = "поставщик"
            meaning = f"отдаёт {abs(d):.0f} ед."
        else:
            role = "потребитель"
            meaning = f"принимает {d:.0f} ед."
        records.append(
            {
                "узел": n,
                "demand": d,
                "роль": role,
                "смысл": meaning,
            }
        )
    return records


DEMAND_HELP_MARKDOWN = """
**Demand** — сколько потока узел **отдаёт** или **принимает** (нужно для *min cost flow*).

| Знак | Роль в NetworkX | Что означает |
|------|-----------------|--------------|
| **< 0** | источник / поставщик | узел **отправляет** поток в сеть (как завод) |
| **> 0** | сток / потребитель | узел **забирает** поток из сети (как склад) |
| **= 0** | транзит | только пропускает: сумма входов = сумма выходов |

**Пример:** demand₀ = −15, demand₄ = +15 → по сети нужно провести **15** единиц из узла **0** в узел **4**.  
Сумма demand по всем узлам = **0** (поток нигде не «исчезает»).

Для **maximum flow** demand не используется — там задаются только **ёмкости** рёбер и пара *(источник, сток)*.
"""
