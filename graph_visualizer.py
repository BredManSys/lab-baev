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


def _layout(graph: nx.DiGraph) -> dict[int, tuple[float, float]]:
    try:
        return nx.spring_layout(graph, seed=42, k=1.5)
    except nx.NetworkXError:
        return nx.circular_layout(graph)


def visualize_graph_matplotlib(
    graph: nx.DiGraph,
    highlight_path: list[int] | None = None,
    figsize: tuple[float, float] = DEFAULT_FIGSIZE,
) -> plt.Figure:
    """Render directed graph with matplotlib; highlight optional path."""
    fig, ax = plt.subplots(figsize=figsize, facecolor="#1e1e1e")
    ax.set_facecolor("#2d2d2d")
    pos = _layout(graph)

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
        graph, pos, edge_labels=labels, font_color="#ecf0f1", font_size=7, ax=ax,
    )
    ax.set_title("SCM Network (Matplotlib)", color="white", fontsize=14)
    ax.axis("off")
    fig.tight_layout()
    return fig


def visualize_graph_plotly(
    graph: nx.DiGraph,
    highlight_path: list[int] | None = None,
) -> go.Figure:
    """Interactive Plotly visualization with optional path highlight."""
    pos = _layout(graph)
    path_edges: set[tuple[int, int]] = set()
    if highlight_path and len(highlight_path) > 1:
        path_edges = {(highlight_path[i], highlight_path[i + 1]) for i in range(len(highlight_path) - 1)}

    edge_traces: list[go.Scatter] = []
    for u, v, d in graph.edges(data=True):
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        color = PATH_EDGE_COLOR if (u, v) in path_edges else DEFAULT_EDGE_COLOR
        lbl = edge_label(d.get("cost", 0), d.get("time", 0), d.get("risk", 0))
        edge_traces.append(
            go.Scatter(
                x=[x0, x1, None], y=[y0, y1, None],
                mode="lines+text",
                line=dict(width=3 if (u, v) in path_edges else 1.5, color=color),
                text=[None, lbl, None],
                textposition="middle center",
                textfont=dict(size=8, color="#ecf0f1"),
                hoverinfo="text",
                hovertext=f"{u} → {v}: {lbl}",
                showlegend=False,
            )
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

    fig = go.Figure(data=edge_traces + [node_trace])
    fig.update_layout(
        title="SCM Network (Plotly)",
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

    net.set_options(
        '{"physics": {"enabled": true, "stabilization": {"iterations": 100}}, '
        '"edges": {"arrows": "to", "font": {"size": 10, "color": "#ecf0f1"}}}'
    )
    return net.generate_html(notebook=False)


def export_graph_png(
    graph: nx.DiGraph,
    filepath: str | Path,
    highlight_path: list[int] | None = None,
    dpi: int = 150,
) -> Path:
    """Save matplotlib figure to PNG."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig = visualize_graph_matplotlib(graph, highlight_path=highlight_path)
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
