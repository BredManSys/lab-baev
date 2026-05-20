"""
SCM KPI Optimizer — веб-приложение Streamlit для анализа транспортной SCM-сети.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from graph_generator import generate_random_dag, graph_summary
from graph_visualizer import (
    visualize_graph_graphviz,
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
from session_manager import initialize_session, render_session_io, reset_session, set_graph
from utils import (
    KPI_RU,
    graph_to_edge_records,
    localize_balance_df,
    localize_optimal_df,
    localize_paths_df,
)

KPI_OPTIONS = ["cost", "time", "risk"]
KPI_LABELS = {"cost": "затраты", "time": "время", "risk": "риск"}

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
graph = st.session_state.get("graph")

with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/supply-chain.png", width=72)
    st.title("Настройки")
    st.markdown(
        "**SCM KPI Optimizer** — приложение для анализа транспортной SCM-сети (DAG) "
        "по показателям **затраты**, **время**, **риск**."
    )
    render_session_io()
    if st.button("Сбросить всё", use_container_width=True):
        reset_session()
        st.rerun()
    st.divider()
    st.session_state["source"] = 1
    st.number_input("Откуда (узел)", min_value=1, value=1, disabled=True)
    max_target = int(max(graph.nodes())) if graph is not None and graph.number_of_nodes() else int(st.session_state["target"])
    st.session_state["target"] = max_target
    st.number_input("Куда (узел)", min_value=1, value=max_target, disabled=True)

st.title("📊 SCM KPI Optimizer")
st.caption(
    "Приложение формирует ориентированный DAG, рассчитывает маршруты по затратам / времени / риску "
    "и подбирает сбалансированный путь с якорным KPI и допустимым отклонением."
)

source = int(st.session_state["source"])
target = int(st.session_state["target"])
edge_font_size = int(st.session_state.get("edge_font_size", 11))
highlight = st.session_state.get("highlight_path") or []

m1, m2, m3, m4 = st.columns(4)
summary = (
    graph_summary(graph, source, target)
    if graph is not None
    else {"nodes": 0, "edges": 0, "is_dag": False, "has_path": False}
)
m1.metric("Узлов", summary.get("nodes", 0))
m2.metric("Рёбер", summary.get("edges", 0))
m3.metric("Это DAG?", "Да" if summary.get("is_dag") else "Нет")
m4.metric(f"Путь {source}→{target}", "Есть" if summary.get("has_path") else "Нет")

tab_graph, tab_opt, tab_kpi = st.tabs(["Граф и визуализация", "Маршруты", "KPI"])

with tab_graph:
    st.subheader("Формирование графа")
    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown("Нажмите кнопку, чтобы сформировать случайный DAG, или загрузите сохранённую сессию.")
    with c2:
        num_nodes = st.slider("Сколько узлов", 9, 24, 12)
        edge_prob = st.slider("Вероятность ребра", 0.1, 0.8, 0.35, 0.05)

    if st.button("Сгенерировать DAG", type="primary", use_container_width=True):
        g = generate_random_dag(
            num_nodes=num_nodes,
            edge_probability=edge_prob,
            random_seed=None,
        )
        set_graph(g)
        st.session_state["optimization_results"] = {}
        st.session_state["highlight_path"] = []
        st.success(f"Граф сформирован: {g.number_of_nodes()} узлов, {g.number_of_edges()} рёбер.")
        st.rerun()

    if graph is not None:
        st.dataframe(pd.DataFrame(graph_to_edge_records(graph)), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Визуализация сети")
    if graph is None:
        st.info("Сформируйте граф выше — изображение появится здесь же.")
    else:
        col_v1, col_v2 = st.columns(2)
        with col_v1:
            backend_ix = ["Graphviz", "Plotly", "Matplotlib", "Pyvis"].index(
                st.session_state.get("viz_backend", "Graphviz")
            )
            st.session_state["viz_backend"] = st.selectbox(
                "Как рисовать граф",
                ["Graphviz", "Plotly", "Matplotlib", "Pyvis"],
                index=backend_ix,
            )
            viz_backend = st.session_state["viz_backend"]
        with col_v2:
            st.session_state["edge_font_size"] = st.slider(
                "Размер шрифта весов",
                min_value=7,
                max_value=22,
                value=int(st.session_state.get("edge_font_size", 11)),
                step=1,
                help="Размер подписей KPI на ребрах.",
            )
        edge_font_size = int(st.session_state.get("edge_font_size", 11))

        path_options = ["— не подсвечивать —"] + [
            " → ".join(map(str, p))
            for p in enumerate_all_paths(graph, source, target)[:20]
        ]
        selected = st.selectbox("Подсветить маршрут", path_options)
        if selected != "— не подсвечивать —":
            highlight = [int(x) for x in selected.split(" → ")]
            st.session_state["highlight_path"] = highlight
        else:
            highlight = []
            st.session_state["highlight_path"] = []

        if viz_backend == "Graphviz":
            dot = visualize_graph_graphviz(graph, highlight_path=highlight or None)
            st.graphviz_chart(dot, use_container_width=True)
        elif viz_backend == "Plotly":
            st.plotly_chart(
                visualize_graph_plotly(
                    graph,
                    highlight_path=highlight or None,
                    edge_font_size=edge_font_size,
                ),
                use_container_width=True,
            )
        elif viz_backend == "Matplotlib":
            fig = visualize_graph_matplotlib(
                graph,
                highlight_path=highlight or None,
                edge_font_size=edge_font_size,
            )
            st.pyplot(fig)
        else:
            html = visualize_graph_pyvis(
                graph,
                highlight_path=highlight or None,
                edge_font_size=edge_font_size,
            )
            st.components.v1.html(html, height=520, scrolling=True)

with tab_opt:
    st.subheader("Оптимизация маршрутов")
    if graph is None:
        st.info("Сначала сформируйте граф.")
    else:
        anchor_ix = KPI_OPTIONS.index(st.session_state.get("selected_anchor_kpi", "cost"))
        st.session_state["selected_anchor_kpi"] = st.selectbox(
            "Якорный KPI (главный критерий)",
            KPI_OPTIONS,
            index=anchor_ix,
            format_func=lambda k: KPI_LABELS[k],
        )
        st.session_state["relaxation_percent"] = st.slider(
            "Допуск по якорю, %",
            10.0,
            15.0,
            float(st.session_state.get("relaxation_percent", 12.0)),
            0.5,
            help="Допустимое отклонение от оптимального значения якорного KPI при подборе сбалансированного маршрута.",
        )

        if st.button("Выполнить оптимизацию", type="primary"):
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
                st.success("Оптимизация выполнена, маршруты рассчитаны.")
            except Exception as e:
                st.error(f"Не удалось выполнить оптимизацию: {e}")

        res = st.session_state.get("optimization_results", {})
        if res:
            balanced = res.get("balanced", {})
            st.markdown("**Сбалансированный маршрут**")
            st.code(" → ".join(map(str, balanced.get("balanced_path", []))))
            st.markdown("**Оптимальный маршрут по якорному KPI**")
            st.code(" → ".join(map(str, balanced.get("optimal_anchor_path", []))))
            bm = balanced.get("balanced_metrics", {})
            o1, o2, o3, o4 = st.columns(4)
            o1.metric("Затраты", f"{bm.get('total_cost', 0):.2f}")
            o2.metric("Время", f"{bm.get('total_time', 0):.2f}")
            o3.metric("Риск", f"{bm.get('total_risk', 0):.2f}")
            o4.metric("Баланс", f"{bm.get('balance_score', 0):.4f}")

            st.markdown("**Визуализация оптимального маршрута (якорный KPI)**")
            viz_backend = st.session_state.get("viz_backend", "Graphviz")
            anchor_optimal_path = balanced.get("optimal_anchor_path", [])
            if viz_backend == "Graphviz":
                dot = visualize_graph_graphviz(graph, highlight_path=anchor_optimal_path or None)
                st.graphviz_chart(dot, use_container_width=True)
            elif viz_backend == "Plotly":
                st.plotly_chart(
                    visualize_graph_plotly(
                        graph,
                        highlight_path=anchor_optimal_path or None,
                        edge_font_size=edge_font_size,
                    ),
                    use_container_width=True,
                )
            elif viz_backend == "Matplotlib":
                fig = visualize_graph_matplotlib(
                    graph,
                    highlight_path=anchor_optimal_path or None,
                    edge_font_size=edge_font_size,
                )
                st.pyplot(fig)
            else:
                html = visualize_graph_pyvis(
                    graph,
                    highlight_path=anchor_optimal_path or None,
                    edge_font_size=edge_font_size,
                )
                st.components.v1.html(html, height=520, scrolling=True)

            st.markdown("**Лучшие маршруты по одному KPI**")
            st.dataframe(
                localize_optimal_df(res.get("optimal_paths")),
                use_container_width=True,
                hide_index=True,
            )
            st.markdown("**Все маршруты (рейтинг)**")
            st.dataframe(
                localize_paths_df(res.get("ranked_paths")),
                use_container_width=True,
                hide_index=True,
            )

with tab_kpi:
    st.subheader("Разбор KPI")
    if graph is None or not st.session_state.get("optimization_results"):
        st.info("Сначала выполните оптимизацию на вкладке «Маршруты».")
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
        v1.metric("Принято", kpi_summary["accepted"])
        v2.metric("Условно принято", kpi_summary["conditionally_accepted"])
        v3.metric("Отклонено", kpi_summary["rejected"])

        if kpi_summary["overall"] != "accepted":
            st.warning(kpi_summary["explanation"])
        else:
            st.success(kpi_summary["explanation"])

        st.dataframe(localize_balance_df(balance_df), use_container_width=True, hide_index=True)
        anchor_ru = KPI_RU.get(anchor_info["anchor_kpi"], anchor_info["anchor_kpi"])
        st.markdown(f"**Совет по якорю:** {anchor_ru} — {anchor_info['reason']}")
        for rec in recommendations:
            st.markdown(f"- {rec}")

        st.session_state["reports"] = {
            "kpi_balance_df": localize_balance_df(balance_df),
            "kpi_summary": kpi_summary,
            "recommendations": recommendations,
            "anchor_info": anchor_info,
        }
