"""Graph visualization backends for SCM KPI Optimizer."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import networkx as nx
import plotly.graph_objects as go
from pyvis.network import Network

from utils import edge_label

DEFAULT_FIGSIZE = (12, 8)
PATH_EDGE_COLOR = "#e74c3c"
DEFAULT_EDGE_COLOR = "#95a5a6"
NODE_COLOR = "#3498db"
HIGHLIGHT_NODE_COLOR = "#e67e22"


def _edge_labels(graph: nx.DiGraph) -> dict[tuple[int, int], str]:
    labels: dict[tuple[int, int], str] = {}
    for u, v, d in graph.edges(data=True):
        labels[(u, v)] = edge_label(d.get("cost", 0), d.get("time", 0), d.get("risk", 0))
    return labels


def visualize_graph_graphviz(
    graph: nx.DiGraph,
    highlight_path: list[int] | None = None,
) -> str:
    """Render directed graph as Graphviz DOT source."""
    path_nodes = set(highlight_path or [])
    path_edges: set[tuple[int, int]] = set()
    if highlight_path and len(highlight_path) > 1:
        path_edges = {(highlight_path[i], highlight_path[i + 1]) for i in range(len(highlight_path) - 1)}

    source = min(graph.nodes()) if graph.number_of_nodes() else None
    target = max(graph.nodes()) if graph.number_of_nodes() else None
    lines = [
        "digraph SCM {",
        '  graph [rankdir=LR, bgcolor="#1e1e1e", splines=true, overlap=false, nodesep=0.5, ranksep=0.8];',
        '  node [shape=circle, style=filled, fontname="Helvetica", fontsize=12, fontcolor="white", color="#dbeafe", fillcolor="#3498db"];',
        '  edge [fontname="Helvetica", fontsize=10, fontcolor="#ecf0f1", color="#95a5a6", arrowsize=0.7];',
    ]

    for n in sorted(graph.nodes()):
        attrs: list[str] = [f'label="{n}"']
        if n in path_nodes:
            attrs.extend(['fillcolor="#e67e22"', 'penwidth=2.0'])
        if n == source:
            attrs.extend(['shape=doublecircle', 'color="#34d399"'])
        elif n == target:
            attrs.extend(['shape=doublecircle', 'color="#f87171"'])
        lines.append(f'  "{n}" [{", ".join(attrs)}];')

    for u, v, d in graph.edges(data=True):
        lbl = f'c:{d.get("cost", 0):.1f}  t:{d.get("time", 0):.1f}  r:{d.get("risk", 0):.1f}'
        edge_attrs = [f'label="{lbl}"']
        if (u, v) in path_edges:
            edge_attrs.extend(['color="#e74c3c"', "penwidth=2.6"])
        lines.append(f'  "{u}" -> "{v}" [{", ".join(edge_attrs)}];')

    lines.append("}")
    return "\n".join(lines)


def _layout(graph: nx.DiGraph) -> dict[int, tuple[float, float]]:
    if graph.number_of_nodes() == 0:
        return {}
    try:
        # Use force-directed layout as the default for all graphs:
        # it produces a natural transport-network shape and avoids line-like stacking.
        n = max(1, graph.number_of_nodes())
        k = max(1.25, 4.0 / (n ** 0.5))
        base_graph = graph.to_undirected() if nx.is_directed_acyclic_graph(graph) else graph
        return nx.spring_layout(base_graph, seed=42, k=k, iterations=450)
    except nx.NetworkXError:
        return nx.circular_layout(graph, scale=2.5)


def _layout_with_density(graph: nx.DiGraph, density: float = 1.0) -> dict[int, tuple[float, float]]:
    """Return layout scaled by density factor: higher density -> more spacing."""
    pos = _layout(graph)
    scale = max(0.6, min(2.2, float(density)))
    return {node: (x * scale, y * scale) for node, (x, y) in pos.items()}


def visualize_graph_matplotlib(
    graph: nx.DiGraph,
    highlight_path: list[int] | None = None,
    figsize: tuple[float, float] = DEFAULT_FIGSIZE,
    density: float = 1.0,
    edge_font_size: int = 9,
) -> plt.Figure:
    """Render directed graph with matplotlib; highlight optional path."""
    node_count = max(1, graph.number_of_nodes())
    fig_w = max(figsize[0], 12 + node_count * 0.4)
    fig_h = max(figsize[1], 7 + node_count * 0.22)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), facecolor="#1e1e1e")
    ax.set_facecolor("#2d2d2d")
    pos = _layout_with_density(graph, density=density)

    path_edges: set[tuple[int, int]] = set()
    path_nodes: set[int] = set()
    if highlight_path and len(highlight_path) > 1:
        path_edges = {(highlight_path[i], highlight_path[i + 1]) for i in range(len(highlight_path) - 1)}
        path_nodes = set(highlight_path)

    nx.draw_networkx_nodes(
        graph,
        pos,
        nodelist=list(graph.nodes()),
        node_color=[HIGHLIGHT_NODE_COLOR if n in path_nodes else NODE_COLOR for n in graph.nodes()],
        node_size=700,
        ax=ax,
    )
    nx.draw_networkx_labels(graph, pos, font_color="white", font_size=10, ax=ax)

    default_edges = [e for e in graph.edges() if e not in path_edges]
    highlight_edges = [e for e in graph.edges() if e in path_edges]

    if default_edges:
        nx.draw_networkx_edges(
            graph, pos, edgelist=default_edges, edge_color=DEFAULT_EDGE_COLOR,
            arrows=True, arrowsize=18, width=1.5, ax=ax,
        )
    if highlight_edges:
        nx.draw_networkx_edges(
            graph, pos, edgelist=highlight_edges, edge_color=PATH_EDGE_COLOR,
            arrows=True, arrowsize=22, width=3.0, ax=ax,
        )

    labels = _edge_labels(graph)
    nx.draw_networkx_edge_labels(
        graph,
        pos,
        edge_labels=labels,
        font_color="#ecf0f1",
        font_size=edge_font_size,
        label_pos=0.52,
        rotate=False,
        bbox={
            "facecolor": "#111827",
            "edgecolor": "#d1d5db",
            "boxstyle": "round,pad=0.25",
            "alpha": 0.85,
        },
        ax=ax,
    )
    ax.set_title("SCM-сеть (Matplotlib)", color="white", fontsize=14)
    ax.axis("off")
    fig.tight_layout()
    return fig


def visualize_graph_plotly(
    graph: nx.DiGraph,
    highlight_path: list[int] | None = None,
    density: float = 1.0,
    edge_font_size: int = 10,
) -> go.Figure:
    """Interactive Plotly visualization with optional path highlight."""
    pos = _layout_with_density(graph, density=density)
    path_edges: set[tuple[int, int]] = set()
    if highlight_path and len(highlight_path) > 1:
        path_edges = {(highlight_path[i], highlight_path[i + 1]) for i in range(len(highlight_path) - 1)}

    edge_traces: list[go.Scatter] = []
    label_x: list[float] = []
    label_y: list[float] = []
    label_texts: list[str] = []
    for u, v, d in graph.edges(data=True):
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        color = PATH_EDGE_COLOR if (u, v) in path_edges else DEFAULT_EDGE_COLOR
        lbl = edge_label(d.get("cost", 0), d.get("time", 0), d.get("risk", 0))
        edge_traces.append(
            go.Scatter(
                x=[x0, x1, None], y=[y0, y1, None],
                mode="lines",
                line=dict(width=3 if (u, v) in path_edges else 1.5, color=color),
                hoverinfo="text",
                hovertext=f"{u} → {v}: {lbl}",
                showlegend=False,
            )
        )
        label_x.append((x0 + x1) / 2)
        label_y.append((y0 + y1) / 2)
        label_texts.append(lbl)

    edge_label_trace = go.Scatter(
        x=label_x,
        y=label_y,
        mode="text",
        text=label_texts,
        textposition="middle center",
        textfont=dict(size=edge_font_size, color="#f3f4f6"),
        hoverinfo="skip",
        showlegend=False,
    )

    node_x = [pos[n][0] for n in graph.nodes()]
    node_y = [pos[n][1] for n in graph.nodes()]
    node_trace = go.Scatter(
        x=node_x, y=node_y, mode="markers+text",
        text=[str(n) for n in graph.nodes()],
        textposition="middle center",
        marker=dict(size=28, color=NODE_COLOR, line=dict(width=2, color="white")),
        showlegend=False,
    )

    fig = go.Figure(data=edge_traces + [edge_label_trace, node_trace])
    fig.update_layout(
        title="SCM-сеть (Plotly)",
        showlegend=False,
        paper_bgcolor="#1e1e1e",
        plot_bgcolor="#2d2d2d",
        font=dict(color="white"),
        xaxis=dict(showgrid=False, zeroline=False, visible=False),
        yaxis=dict(showgrid=False, zeroline=False, visible=False),
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return fig


def visualize_graph_pyvis(
    graph: nx.DiGraph,
    highlight_path: list[int] | None = None,
    height: str = "500px",
    density: float = 1.0,
    edge_font_size: int = 15,
) -> str:
    """Build pyvis HTML string for embedded Streamlit display."""
    net = Network(height=height, width="100%", directed=True, bgcolor="#1e1e1e", font_color="white")
    path_nodes: set[int] = set(highlight_path or [])
    path_edges: set[tuple[int, int]] = set()
    if highlight_path and len(highlight_path) > 1:
        path_edges = {(highlight_path[i], highlight_path[i + 1]) for i in range(len(highlight_path) - 1)}

    for n in graph.nodes():
        net.add_node(
            n, label=str(n),
            color=HIGHLIGHT_NODE_COLOR if n in path_nodes else NODE_COLOR,
            title=f"Node {n}",
        )

    for u, v, d in graph.edges(data=True):
        lbl = edge_label(d.get("cost", 0), d.get("time", 0), d.get("risk", 0))
        net.add_edge(
            u, v, label=lbl, title=lbl,
            color=PATH_EDGE_COLOR if (u, v) in path_edges else DEFAULT_EDGE_COLOR,
            width=3 if (u, v) in path_edges else 1,
        )

    density = max(0.6, min(2.2, float(density)))
    spring_len = int(140 * density)
    gravity = int(-70 * density)
    net.set_options(
        f'{{"physics": {{"enabled": true, "solver": "forceAtlas2Based", "forceAtlas2Based": {{"gravitationalConstant": {gravity}, "springLength": {spring_len}, "springConstant": 0.04}}, "stabilization": {{"iterations": 250}}}}, '
        '"nodes": {"font": {"size": 18}}, '
        f'"edges": {{"arrows": "to", "smooth": {{"enabled": true, "type": "dynamic"}}, "font": {{"size": {int(edge_font_size)}, "color": "#ecf0f1", "strokeWidth": 3, "strokeColor": "#111827"}}}}}}'
    )
    return net.generate_html(notebook=False)


def export_graph_png(
    graph: nx.DiGraph,
    filepath: str | Path,
    highlight_path: list[int] | None = None,
    density: float = 1.0,
    edge_font_size: int = 9,
    dpi: int = 150,
) -> Path:
    """Save matplotlib figure to PNG."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig = visualize_graph_matplotlib(
        graph,
        highlight_path=highlight_path,
        density=density,
        edge_font_size=edge_font_size,
    )
    fig.savefig(path, dpi=dpi, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return path


def figure_to_bytes(fig: plt.Figure, dpi: int = 150) -> bytes:
    """Convert matplotlib figure to PNG bytes for Streamlit / PDF."""
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
