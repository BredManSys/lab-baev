"""Визуализация сети потоков (Graphviz / Pyvis)."""

from __future__ import annotations

from typing import Any

import networkx as nx
from pyvis.network import Network

PATH_EDGE_COLOR = "#e74c3c"
DEFAULT_EDGE_COLOR = "#95a5a6"
NODE_COLOR = "#3498db"
HIGHLIGHT_NODE_COLOR = "#e67e22"
FLOW_EDGE_COLOR = "#2ecc71"


def _flow_on_edge(
    flow_dict: dict[int, dict[int, float]] | None,
    u: int,
    v: int,
) -> float:
    if not flow_dict:
        return 0.0
    return float(flow_dict.get(u, {}).get(v, 0.0))


def resolve_flow_terminals(
    graph: nx.DiGraph,
    source: int | None = None,
    sink: int | None = None,
) -> tuple[int, int]:
    """Фактические s и t: из аргументов, иначе demand, иначе 0 и max(узел)."""
    if graph.number_of_nodes() == 0:
        return 0, 0
    if source is None:
        suppliers = [
            n
            for n in graph.nodes()
            if float(graph.nodes[n].get("demand", 0)) < -1e-9
        ]
        source = suppliers[0] if suppliers else 0
    if sink is None:
        consumers = [
            n
            for n in graph.nodes()
            if float(graph.nodes[n].get("demand", 0)) > 1e-9
        ]
        sink = consumers[0] if consumers else max(graph.nodes())
    return int(source), int(sink)


def _edge_label_flow(
    capacity: float,
    cost: float,
    flow: float = 0.0,
    show_flow: bool = False,
) -> str:
    if show_flow and flow > 1e-9:
        return f"f:{flow:.1f}/C:{capacity:.0f}/c:{cost:.0f}"
    return f"C:{capacity:.0f}/c:{cost:.0f}"


def visualize_flow_graphviz(
    graph: nx.DiGraph,
    source: int | None = None,
    sink: int | None = None,
    flow_dict: dict[int, dict[int, float]] | None = None,
    highlight_edges: set[tuple[int, int]] | None = None,
) -> str:
    """DOT-схема сети потоков с подсветкой потока."""
    source, sink = resolve_flow_terminals(graph, source, sink)
    if highlight_edges is None and flow_dict:
        highlight_edges = {
            (u, v)
            for u, v, _ in graph.edges(data=True)
            if _flow_on_edge(flow_dict, u, v) > 1e-9
        }
    highlight_edges = highlight_edges or set()

    lines = [
        "digraph FlowNet {",
        '  graph [rankdir=LR, bgcolor="#1e1e1e", splines=true, overlap=false, nodesep=0.5, ranksep=0.8];',
        '  node [shape=circle, style=filled, fontname="Helvetica", fontsize=12, fontcolor="white", color="#dbeafe", fillcolor="#3498db"];',
        '  edge [fontname="Helvetica", fontsize=10, fontcolor="#ecf0f1", color="#95a5a6", arrowsize=0.7];',
    ]

    for n in sorted(graph.nodes()):
        demand = float(graph.nodes[n].get("demand", 0))
        lbl = f"{n}"
        if abs(demand) > 1e-9:
            lbl = f"{n}\\nd={demand:+.0f}"
        attrs = [f'label="{lbl}"']
        if n == source:
            attrs.extend(['shape=doublecircle', 'color="#34d399"'])
        elif n == sink:
            attrs.extend(['shape=doublecircle', 'color="#f87171"'])
        lines.append(f'  "{n}" [{", ".join(attrs)}];')

    show_flow = flow_dict is not None
    for u, v, d in graph.edges(data=True):
        cap = float(d.get("capacity", 0))
        cost = float(d.get("cost", 0))
        flow = _flow_on_edge(flow_dict, u, v)
        lbl = _edge_label_flow(cap, cost, flow, show_flow=show_flow)
        edge_attrs = [f'label="{lbl}"']
        if (u, v) in highlight_edges:
            edge_attrs.extend(['color="#2ecc71"', "penwidth=2.6"])
        lines.append(f'  "{u}" -> "{v}" [{", ".join(edge_attrs)}];')

    lines.append("}")
    return "\n".join(lines)


def visualize_flow_pyvis(
    graph: nx.DiGraph,
    source: int | None = None,
    sink: int | None = None,
    flow_dict: dict[int, dict[int, float]] | None = None,
    edge_font_size: int = 11,
    height: str = "500px",
) -> str:
    """HTML Pyvis для встраивания в Streamlit."""
    source, sink = resolve_flow_terminals(graph, source, sink)
    net = Network(height=height, width="100%", directed=True, bgcolor="#1e1e1e", font_color="white")
    show_flow = flow_dict is not None

    for n in graph.nodes():
        demand = float(graph.nodes[n].get("demand", 0))
        title = f"Узел {n}"
        if abs(demand) > 1e-9:
            title += f", demand={demand:+.1f}"
        color = NODE_COLOR
        if n == source:
            color = "#34d399"
        elif n == sink:
            color = "#f87171"
        net.add_node(n, label=str(n), color=color, title=title)

    for u, v, d in graph.edges(data=True):
        flow = _flow_on_edge(flow_dict, u, v)
        cap = float(d.get("capacity", 0))
        cost = float(d.get("cost", 0))
        lbl = _edge_label_flow(cap, cost, flow, show_flow=show_flow)
        color = FLOW_EDGE_COLOR if show_flow and flow > 1e-9 else DEFAULT_EDGE_COLOR
        width = 3 if show_flow and flow > 1e-9 else 1
        net.add_edge(u, v, label=lbl, title=lbl, color=color, width=width)

    net.set_options(
        f'{{"physics": {{"enabled": true, "solver": "forceAtlas2Based", '
        f'"forceAtlas2Based": {{"gravitationalConstant": -70, "springLength": 140}}, '
        f'"stabilization": {{"iterations": 250}}}}, '
        '"nodes": {"font": {"size": 18}}, '
        f'"edges": {{"arrows": "to", "smooth": {{"enabled": true}}, '
        f'"font": {{"size": {int(edge_font_size)}, "color": "#ecf0f1"}}}}}}'
    )
    return net.generate_html(notebook=False)


def bottleneck_edges_from_flow(
    graph: nx.DiGraph,
    flow_dict: dict[int, dict[int, float]],
) -> set[tuple[int, int]]:
    """Рёбра, на которых поток равен ёмкости."""
    out: set[tuple[int, int]] = set()
    for u, v, data in graph.edges(data=True):
        flow = _flow_on_edge(flow_dict, u, v)
        cap = float(data.get("capacity", 0))
        if cap > 0 and abs(flow - cap) < 1e-6:
            out.add((u, v))
    return out
