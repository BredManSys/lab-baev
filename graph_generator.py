"""DAG graph generation and edge manipulation for SCM KPI Optimizer."""

from __future__ import annotations

import random
from itertools import islice
from typing import Any

import networkx as nx

DEFAULT_MIN_WEIGHT = 1
DEFAULT_MAX_WEIGHT = 10


def create_empty_graph() -> nx.DiGraph:
    """Create an empty directed graph with KPI edge attributes."""
    return nx.DiGraph()


def _random_weights(
    rng: random.Random,
    min_weight: float,
    max_weight: float,
    span_ratio: float = 0.0,
) -> dict[str, float]:
    """
    Generate KPI weights with route profiles and trade-offs.

    Profiles make routes more realistic:
    - economy: cheaper, slower, slightly riskier
    - express: faster, more expensive
    - safe: lower risk, moderate cost/time
    - aggressive: fast and cheap, but risky
    - balanced: no strong bias
    """
    spread = max_weight - min_weight
    distance_bias = spread * 0.55 * span_ratio

    profile = rng.choices(
        population=["economy", "express", "safe", "aggressive", "balanced"],
        weights=[0.24, 0.22, 0.20, 0.14, 0.20],
        k=1,
    )[0]

    if profile == "economy":
        base_cost, base_time, base_risk = 0.22, 0.72, 0.58
    elif profile == "express":
        base_cost, base_time, base_risk = 0.78, 0.25, 0.52
    elif profile == "safe":
        base_cost, base_time, base_risk = 0.62, 0.58, 0.22
    elif profile == "aggressive":
        base_cost, base_time, base_risk = 0.34, 0.28, 0.84
    else:
        base_cost, base_time, base_risk = 0.50, 0.50, 0.50

    noise = lambda: rng.uniform(-0.10, 0.10) * spread

    def to_range(v: float) -> float:
        return round(max(min_weight, min(max_weight, v)), 2)

    # Long jumps are usually faster but more expensive and riskier.
    span_cost = distance_bias
    span_time = -spread * 0.25 * span_ratio
    span_risk = distance_bias * 0.85

    cost = min_weight + base_cost * spread + span_cost + noise()
    time = min_weight + base_time * spread + span_time + noise()
    risk = min_weight + base_risk * spread + span_risk + noise()
    return {"cost": to_range(cost), "time": to_range(time), "risk": to_range(risk)}


def _add_edge_with_profile(
    graph: nx.DiGraph,
    u: int,
    v: int,
    rng: random.Random,
    min_weight: float,
    max_weight: float,
    num_nodes: int,
) -> None:
    if graph.has_edge(u, v):
        return
    span_ratio = (v - u) / max(1, (num_nodes - 1))
    graph.add_edge(u, v, **_random_weights(rng, min_weight, max_weight, span_ratio=span_ratio))


def _ensure_minimum_route_diversity(
    graph: nx.DiGraph,
    rng: random.Random,
    min_weight: float,
    max_weight: float,
    num_nodes: int,
) -> None:
    """Ensure at least two distinct source-target routes when possible."""
    source, target = 1, num_nodes
    def _has_two_or_more_paths() -> bool:
        try:
            count = 0
            for _ in nx.all_simple_paths(graph, source=source, target=target, cutoff=num_nodes):
                count += 1
                if count >= 2:
                    return True
            return False
        except nx.NetworkXNoPath:
            return False

    if _has_two_or_more_paths():
        return

    bridge_candidates = [
        (1, min(num_nodes, 3)),
        (2, min(num_nodes, 5)),
        (max(1, num_nodes - 4), num_nodes),
        (max(1, num_nodes - 6), max(1, num_nodes - 2)),
    ]
    for u, v in bridge_candidates:
        if u < v and u in graph and v in graph and not graph.has_edge(u, v):
            _add_edge_with_profile(graph, u, v, rng, min_weight, max_weight, num_nodes)
            if _has_two_or_more_paths():
                return


def _apply_metric_factor(
    graph: nx.DiGraph,
    path: list[int],
    metric: str,
    factor: float,
    min_weight: float,
    max_weight: float,
) -> None:
    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        val = float(graph[u][v].get(metric, min_weight))
        graph[u][v][metric] = round(max(min_weight, min(max_weight, val * factor)), 2)


def _promote_metric_diversity(
    graph: nx.DiGraph,
    num_nodes: int,
    min_weight: float,
    max_weight: float,
    rng: random.Random,
) -> None:
    """
    Reduce chance that one path is simultaneously best for multiple KPIs.
    """
    source, target = 1, num_nodes
    metrics = ("cost", "time", "risk")

    def _best_k_paths(metric: str, k: int = 4) -> list[list[int]]:
        try:
            gen = nx.shortest_simple_paths(graph, source=source, target=target, weight=metric)
            return list(islice(gen, k))
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    # Several rounds of controlled reweighting to separate KPI-optimal paths.
    for _ in range(6):
        path_pool = {m: _best_k_paths(m, k=5) for m in metrics}
        if any(not v for v in path_pool.values()):
            return

        best_paths = {m: path_pool[m][0] for m in metrics}
        unique_best = {tuple(p) for p in best_paths.values()}
        if len(unique_best) == len(metrics):
            return

        # For each metric that shares the same best path with another metric,
        # promote an alternative path and slightly penalize the shared one.
        for metric in metrics:
            current_best = best_paths[metric]
            current_best_key = tuple(current_best)
            duplicate_count = sum(1 for p in best_paths.values() if tuple(p) == current_best_key)
            if duplicate_count <= 1:
                continue

            alternatives = [p for p in path_pool[metric][1:] if tuple(p) != current_best_key]
            if not alternatives:
                continue

            alt = rng.choice(alternatives[: min(3, len(alternatives))])
            up_factor = 1.10 + rng.uniform(0.06, 0.14)
            down_factor = 0.86 - rng.uniform(0.03, 0.08)
            _apply_metric_factor(graph, current_best, metric, up_factor, min_weight, max_weight)
            _apply_metric_factor(graph, alt, metric, down_factor, min_weight, max_weight)


def generate_random_dag(
    num_nodes: int = 12,
    edge_probability: float = 0.35,
    min_weight: float = DEFAULT_MIN_WEIGHT,
    max_weight: float = DEFAULT_MAX_WEIGHT,
    random_seed: int | None = 42,
) -> nx.DiGraph:
    """
    Generate a random directed acyclic graph with KPI edge weights.

    Guarantees:
    - At least 9 nodes (raises ValueError otherwise)
    - Backbone path 1 -> 2 -> ... -> num_nodes
    - Additional branch/express edges to create diverse route options
    - Additional edges only from lower to higher node id (DAG)
    - KPI values with realistic trade-off profiles on edges
    """
    if num_nodes < 9:
        raise ValueError("num_nodes must be at least 9")

    rng = random.Random(random_seed)
    graph = nx.DiGraph()
    graph.add_nodes_from(range(1, num_nodes + 1))

    # Guaranteed backbone path 1 -> ... -> num_nodes
    for u in range(1, num_nodes):
        _add_edge_with_profile(graph, u, u + 1, rng, min_weight, max_weight, num_nodes)

    # Alternative routes: forward skip edges (i < j) to preserve acyclicity
    max_skip = max(3, min(5, num_nodes // 3 + 2))
    for i in range(1, num_nodes):
        for jump in range(2, max_skip + 1):
            j = i + jump
            if j > num_nodes:
                break
            # Slight bias toward shorter skips for richer but interpretable route sets.
            jump_penalty = 0.85 ** (jump - 2)
            p = min(0.95, edge_probability * jump_penalty)
            if rng.random() < p:
                _add_edge_with_profile(graph, i, j, rng, min_weight, max_weight, num_nodes)

    # A few corridor edges from early to mid/late levels add meaningful strategic choices.
    corridor_count = max(1, num_nodes // 7)
    for _ in range(corridor_count):
        u = rng.randint(1, max(2, num_nodes // 3))
        max_v = min(num_nodes - 1, u + max(4, num_nodes // 2))
        if max_v <= u + 2:
            continue
        v = rng.randint(u + 3, max_v)
        if u < v:
            _add_edge_with_profile(graph, u, v, rng, min_weight, max_weight, num_nodes)

    _ensure_minimum_route_diversity(graph, rng, min_weight, max_weight, num_nodes)
    _promote_metric_diversity(graph, num_nodes, min_weight, max_weight, rng)

    assert nx.is_directed_acyclic_graph(graph)
    assert nx.has_path(graph, 1, num_nodes)
    return graph


def add_edge(
    graph: nx.DiGraph,
    source: int,
    target: int,
    cost: float | None = None,
    time: float | None = None,
    risk: float | None = None,
) -> nx.DiGraph:
    """Add a directed edge if it does not create a cycle."""
    if source == target:
        raise ValueError("Self-loops are not allowed")
    graph.add_edge(source, target)
    if not nx.is_directed_acyclic_graph(graph):
        graph.remove_edge(source, target)
        raise ValueError(f"Edge ({source}, {target}) would create a cycle")

    rng = random.Random()
    weights = _random_weights(rng, DEFAULT_MIN_WEIGHT, DEFAULT_MAX_WEIGHT)
    graph[source][target]["cost"] = cost if cost is not None else weights["cost"]
    graph[source][target]["time"] = time if time is not None else weights["time"]
    graph[source][target]["risk"] = risk if risk is not None else weights["risk"]
    return graph


def remove_edge(graph: nx.DiGraph, source: int, target: int) -> nx.DiGraph:
    """Remove an edge if it exists."""
    if graph.has_edge(source, target):
        graph.remove_edge(source, target)
    return graph


def update_edge_weights(
    graph: nx.DiGraph,
    source: int,
    target: int,
    cost: float | None = None,
    time: float | None = None,
    risk: float | None = None,
) -> nx.DiGraph:
    """Update KPI weights on an existing edge."""
    if not graph.has_edge(source, target):
        raise ValueError(f"Edge ({source}, {target}) does not exist")
    if cost is not None:
        graph[source][target]["cost"] = cost
    if time is not None:
        graph[source][target]["time"] = time
    if risk is not None:
        graph[source][target]["risk"] = risk
    return graph


def graph_summary(graph: nx.DiGraph, source: int = 1, target: int | None = None) -> dict[str, Any]:
    """Return basic graph statistics."""
    if target is None and graph.number_of_nodes() > 0:
        target = max(graph.nodes())
    has_path = False
    if graph.number_of_nodes() > 0 and source in graph and target in graph:
        try:
            has_path = nx.has_path(graph, source, target)
        except nx.NodeNotFound:
            has_path = False
    return {
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "is_dag": nx.is_directed_acyclic_graph(graph),
        "has_path": has_path,
        "source": source,
        "target": target,
    }
