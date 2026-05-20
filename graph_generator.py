"""DAG graph generation and edge manipulation for SCM KPI Optimizer."""

from __future__ import annotations

import random
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
) -> dict[str, float]:
    return {
        "cost": round(rng.uniform(min_weight, max_weight), 2),
        "time": round(rng.uniform(min_weight, max_weight), 2),
        "risk": round(rng.uniform(min_weight, max_weight), 2),
    }


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
    - Additional edges only from lower to higher node id (DAG)
    - Optional alternative routes via extra edges
    """
    if num_nodes < 9:
        raise ValueError("num_nodes must be at least 9")

    rng = random.Random(random_seed)
    graph = nx.DiGraph()
    graph.add_nodes_from(range(1, num_nodes + 1))

    # Guaranteed backbone path 1 -> ... -> num_nodes
    for u in range(1, num_nodes):
        graph.add_edge(u, u + 1, **_random_weights(rng, min_weight, max_weight))

    # Alternative routes: only forward edges (i < j) to preserve acyclicity
    for i in range(1, num_nodes + 1):
        for j in range(i + 2, num_nodes + 1):
            if rng.random() < edge_probability and not graph.has_edge(i, j):
                graph.add_edge(i, j, **_random_weights(rng, min_weight, max_weight))

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
