"""
SCM KPI Optimizer — Streamlit web application for transport SCM network analysis.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from graph_generator import generate_random_dag, graph_summary
from graph_visualizer import (
    export_graph_png,
    figure_to_bytes,
    visualize_graph_matplotlib,
    visualize_graph_plotly,
    visualize_graph_pyvis,
)
from kpi_analysis import (
    analyze_kpi_balance,
    build_recommendations,
    generate_kpi_summary,
    recommend_anchor_kpi,
)
from path_optimizer import (
    calculate_path_metrics,
    enumerate_all_paths,
    find_balanced_path,
    optimal_paths_summary,
    rank_paths,
    shortest_path_by_cost,
)
from report_generator import build_results_payload, export_csv, export_json_results, generate_pdf_report
from session_manager import initialize_session, render_session_io, reset_session, set_graph
from utils import graph_to_edge_records

# ——— Page config & styling ———
st.set_page_config(
    page_title="SCM KPI Optimizer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .stApp { background-color: #0e1117; color: #fafafa; }
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #1a1f2e 0%, #252b3b 100%);
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #3d4f6f;
    }
    h1, h2, h3 { color: #e8eef7 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

initialize_session()

# ——— Sidebar ———
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/supply-chain.png", width=72)
    st.title("Settings")
    st.markdown("**SCM KPI Optimizer** — курсовой проект по анализу транспортной SCM-сети (DAG) с KPI: cost, time, risk.")
    render_session_io()
    if st.button("Reset session", use_container_width=True):
        reset_session()
        st.rerun()
    st.divider()
    st.session_state["source"] = st.number_input("Source node", min_value=1, value=int(st.session_state["source"]))
    st.session_state["target"] = st.number_input("Target node", min_value=1, value=int(st.session_state["target"]))
    viz_backend = st.selectbox("Visualization backend", ["Plotly", "Matplotlib", "Pyvis"])

# ——— Header ———
st.title("📊 SCM KPI Optimizer")
st.caption(
    "Анализ ориентированной ациклической транспортной сети: оптимизация маршрутов по cost / time / risk "
    "и сбалансированный выбор пути с учётом anchor KPI."
)

graph = st.session_state.get("graph")
source = int(st.session_state["source"])
target = int(st.session_state["target"])
highlight = st.session_state.get("highlight_path") or []

# ——— Metrics row ———
m1, m2, m3, m4 = st.columns(4)
summary = (
    graph_summary(graph, source, target)
    if graph is not None
    else {"nodes": 0, "edges": 0, "is_dag": False, "has_path": False}
)
m1.metric("Nodes", summary.get("nodes", 0))
m2.metric("Edges", summary.get("edges", 0))
m3.metric("Is DAG", "Yes" if summary.get("is_dag") else "No")
m4.metric(f"Path {source}→{target}", "Yes" if summary.get("has_path") else "No")

tab_setup, tab_viz, tab_opt, tab_kpi, tab_export = st.tabs(
    ["Graph Setup", "Visualization", "Optimization", "KPI Analysis", "Reports & Export"]
)

# ——— TAB 1: Graph Setup ———
with tab_setup:
    st.subheader("Graph Setup")
    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown("Сгенерируйте случайный DAG или загрузите сессию из sidebar.")
    with c2:
        num_nodes = st.slider("Number of nodes", 9, 24, 12)
        edge_prob = st.slider("Edge probability", 0.1, 0.8, 0.35, 0.05)
        seed = st.number_input("Random seed", value=42, step=1)

    if st.button("Generate random DAG", type="primary", use_container_width=True):
        g = generate_random_dag(
            num_nodes=num_nodes,
            edge_probability=edge_prob,
            random_seed=int(seed),
        )
        set_graph(g)
        st.session_state["optimization_results"] = {}
        st.session_state["highlight_path"] = []
        st.success(f"Graph created: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges.")
        st.rerun()

    if graph is not None:
        st.dataframe(pd.DataFrame(graph_to_edge_records(graph)), use_container_width=True, hide_index=True)

# ——— TAB 2: Visualization ———
with tab_viz:
    st.subheader("Network Visualization")
    if graph is None:
        st.info("Сначала сгенерируйте граф на вкладке Graph Setup.")
    else:
        path_options = ["None"] + [
            " → ".join(map(str, p))
            for p in enumerate_all_paths(graph, source, target)[:20]
        ]
        selected = st.selectbox("Highlight path", path_options)
        if selected != "None":
            highlight = [int(x) for x in selected.split(" → ")]
            st.session_state["highlight_path"] = highlight
        else:
            highlight = []
            st.session_state["highlight_path"] = []

        if viz_backend == "Plotly":
            st.plotly_chart(visualize_graph_plotly(graph, highlight_path=highlight or None), use_container_width=True)
        elif viz_backend == "Matplotlib":
            fig = visualize_graph_matplotlib(graph, highlight_path=highlight or None)
            st.pyplot(fig)
        else:
            html = visualize_graph_pyvis(graph, highlight_path=highlight or None)
            st.components.v1.html(html, height=520, scrolling=True)

# ——— TAB 3: Optimization ———
with tab_opt:
    st.subheader("Path Optimization")
    if graph is None:
        st.info("Сначала сгенерируйте граф.")
    else:
        st.session_state["selected_anchor_kpi"] = st.selectbox(
            "Anchor KPI",
            ["cost", "time", "risk"],
            index=["cost", "time", "risk"].index(st.session_state.get("selected_anchor_kpi", "cost")),
        )
        st.session_state["relaxation_percent"] = st.slider(
            "Relaxation %", 10.0, 15.0, float(st.session_state.get("relaxation_percent", 12.0)), 0.5,
        )

        if st.button("Run optimization", type="primary"):
            anchor = st.session_state["selected_anchor_kpi"]
            relax = st.session_state["relaxation_percent"]
            try:
                balanced = find_balanced_path(graph, anchor, relax, source, target)
                paths = enumerate_all_paths(graph, source, target)
                ranked = rank_paths(graph, paths)
                optimal_df = optimal_paths_summary(graph, source, target)
                st.session_state["optimization_results"] = {
                    "balanced": balanced,
                    "ranked_paths": ranked,
                    "optimal_paths": optimal_df,
                }
                st.session_state["highlight_path"] = balanced.get("balanced_path", [])
                st.success("Optimization complete.")
            except Exception as e:
                st.error(f"Optimization failed: {e}")

        res = st.session_state.get("optimization_results", {})
        if res:
            balanced = res.get("balanced", {})
            st.markdown("**Balanced path**")
            st.code(" → ".join(map(str, balanced.get("balanced_path", []))))
            bm = balanced.get("balanced_metrics", {})
            o1, o2, o3, o4 = st.columns(4)
            o1.metric("Total cost", f"{bm.get('total_cost', 0):.2f}")
            o2.metric("Total time", f"{bm.get('total_time', 0):.2f}")
            o3.metric("Total risk", f"{bm.get('total_risk', 0):.2f}")
            o4.metric("Balance score", f"{bm.get('balance_score', 0):.4f}")

            st.markdown("**Optimal paths by single KPI**")
            st.dataframe(res.get("optimal_paths"), use_container_width=True, hide_index=True)
            st.markdown("**Ranked paths**")
            st.dataframe(res.get("ranked_paths"), use_container_width=True, hide_index=True)

# ——— TAB 4: KPI Analysis ———
with tab_kpi:
    st.subheader("KPI Analysis")
    if graph is None or not st.session_state.get("optimization_results"):
        st.info("Сначала выполните оптимизацию на вкладке Optimization.")
    else:
        balanced = st.session_state["optimization_results"]["balanced"]
        current_path = balanced.get("balanced_path", [])
        current_m = calculate_path_metrics(graph, current_path)
        try:
            optimal_path = shortest_path_by_cost(graph, source, target)
            optimal_m = calculate_path_metrics(graph, optimal_path)
        except Exception:
            optimal_m = current_m

        balance_df = analyze_kpi_balance(current_m, optimal_m)
        kpi_summary = generate_kpi_summary(balance_df)
        ranked_df = st.session_state["optimization_results"].get("ranked_paths", pd.DataFrame())
        paths_metrics = []
        if not ranked_df.empty and "nodes" in ranked_df.columns:
            for nodes in ranked_df["nodes"]:
                paths_metrics.append(calculate_path_metrics(graph, nodes))
        anchor_info = recommend_anchor_kpi(paths_metrics or [current_m])
        recommendations = build_recommendations(kpi_summary, anchor_info, balance_df)

        v1, v2, v3 = st.columns(3)
        v1.metric("Accepted KPIs", kpi_summary["accepted"])
        v2.metric("Conditional", kpi_summary["conditionally_accepted"])
        v3.metric("Rejected", kpi_summary["rejected"])
        st.warning(kpi_summary["explanation"]) if kpi_summary["overall"] != "accepted" else st.success(kpi_summary["explanation"])

        st.dataframe(balance_df, use_container_width=True, hide_index=True)
        st.markdown(f"**Recommended anchor:** {anchor_info['anchor_kpi']} — {anchor_info['reason']}")
        for rec in recommendations:
            st.markdown(f"- {rec}")

        st.session_state["reports"] = {
            "kpi_balance_df": balance_df,
            "kpi_summary": kpi_summary,
            "recommendations": recommendations,
            "anchor_info": anchor_info,
        }

# ——— TAB 5: Reports & Export ———
with tab_export:
    st.subheader("Reports & Export")
    if graph is None:
        st.info("Нет данных для экспорта.")
    else:
        edge_df = pd.DataFrame(graph_to_edge_records(graph))
        res = st.session_state.get("optimization_results", {})
        reports = st.session_state.get("reports", {})
        optimal_df = res.get("optimal_paths", optimal_paths_summary(graph, source, target))
        ranked_df = res.get("ranked_paths", pd.DataFrame())
        balance_df = reports.get("kpi_balance_df", pd.DataFrame())
        kpi_summary = reports.get("kpi_summary", {})
        recommendations = reports.get("recommendations", [])
        balanced = res.get("balanced", {})
        anchor = st.session_state.get("selected_anchor_kpi", "cost")
        relax = st.session_state.get("relaxation_percent", 12.0)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir = Path("exports")

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            if st.button("Generate PDF report"):
                pdf_path = export_dir / f"scm_report_{ts}.pdf"
                generate_pdf_report(
                    pdf_path,
                    graph_summary=summary,
                    edge_df=edge_df,
                    optimal_paths_df=optimal_df,
                    kpi_balance_df=balance_df,
                    kpi_summary=kpi_summary,
                    recommendations=recommendations,
                    graph=graph,
                    highlight_path=st.session_state.get("highlight_path"),
                    anchor_kpi=anchor,
                    relaxation_percent=relax,
                    balanced_result=balanced,
                )
                st.session_state["last_pdf"] = str(pdf_path)
                st.success(f"PDF saved: {pdf_path}")

        with col_b:
            csv_path = export_dir / f"edges_{ts}.csv"
            if st.button("Export edges CSV"):
                export_csv(edge_df, csv_path)
                st.success(f"CSV saved: {csv_path}")

        with col_c:
            if st.button("Export results JSON"):
                payload = build_results_payload(
                    graph_summary=summary,
                    optimal_paths_df=optimal_df,
                    ranked_paths_df=ranked_df,
                    kpi_balance_df=balance_df,
                    kpi_summary=kpi_summary,
                    balanced_result=balanced,
                    anchor_kpi=anchor,
                    relaxation_percent=relax,
                )
                json_path = export_dir / f"results_{ts}.json"
                export_json_results(payload, json_path)
                st.success(f"JSON saved: {json_path}")

        if "last_pdf" in st.session_state and Path(st.session_state["last_pdf"]).exists():
            with open(st.session_state["last_pdf"], "rb") as f:
                st.download_button("Download PDF", f, file_name=Path(st.session_state["last_pdf"]).name)

        png_path = Path("temp") / f"graph_{ts}.png"
        if st.button("Export graph PNG"):
            export_graph_png(graph, png_path, highlight_path=st.session_state.get("highlight_path"))
            with open(png_path, "rb") as f:
                st.download_button("Download PNG", f, file_name=png_path.name)
