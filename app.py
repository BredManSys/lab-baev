"""
SCM KPI Optimizer — веб-приложение Streamlit для анализа транспортной SCM-сети.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from graph_generator import generate_random_dag, graph_summary
from graph_visualizer import (
    export_graph_png,
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

with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/supply-chain.png", width=72)
    st.title("Настройки")
    st.markdown(
        "**SCM KPI Optimizer** — курсовая: копаем транспортную SCM-сеть (DAG) "
        "и смотрим KPI: **затраты**, **время**, **риск**."
    )
    render_session_io()
    if st.button("Сбросить всё", use_container_width=True):
        reset_session()
        st.rerun()
    st.divider()
    st.session_state["source"] = st.number_input(
        "Откуда (узел)", min_value=1, value=int(st.session_state["source"])
    )
    st.session_state["target"] = st.number_input(
        "Куда (узел)", min_value=1, value=int(st.session_state["target"])
    )
    viz_backend = st.selectbox("Как рисовать граф", ["Plotly", "Matplotlib", "Pyvis"])

st.title("📊 SCM KPI Optimizer")
st.caption(
    "Крутим ориентированный DAG, ищем маршруты по затратам / времени / риску "
    "и подбираем сбалансированный путь с якорным KPI и допуском."
)

graph = st.session_state.get("graph")
source = int(st.session_state["source"])
target = int(st.session_state["target"])
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

tab_setup, tab_viz, tab_opt, tab_kpi, tab_export = st.tabs(
    ["Граф", "Картинка", "Маршруты", "KPI", "Выгрузка"]
)

with tab_setup:
    st.subheader("Настройка графа")
    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown("Нажми кнопку — соберём случайный DAG. Или подгрузи сессию слева.")
    with c2:
        num_nodes = st.slider("Сколько узлов", 9, 24, 12)
        edge_prob = st.slider("Вероятность ребра", 0.1, 0.8, 0.35, 0.05)
        seed = st.number_input("Сид рандома", value=42, step=1)

    if st.button("Сгенерить DAG", type="primary", use_container_width=True):
        g = generate_random_dag(
            num_nodes=num_nodes,
            edge_probability=edge_prob,
            random_seed=int(seed),
        )
        set_graph(g)
        st.session_state["optimization_results"] = {}
        st.session_state["highlight_path"] = []
        st.success(f"Готово: {g.number_of_nodes()} узлов, {g.number_of_edges()} рёбер.")
        st.rerun()

    if graph is not None:
        st.dataframe(pd.DataFrame(graph_to_edge_records(graph)), use_container_width=True, hide_index=True)

with tab_viz:
    st.subheader("Визуализация сети")
    if graph is None:
        st.info("Сначала сгенери граф на вкладке «Граф».")
    else:
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

        if viz_backend == "Plotly":
            st.plotly_chart(
                visualize_graph_plotly(graph, highlight_path=highlight or None),
                use_container_width=True,
            )
        elif viz_backend == "Matplotlib":
            fig = visualize_graph_matplotlib(graph, highlight_path=highlight or None)
            st.pyplot(fig)
        else:
            html = visualize_graph_pyvis(graph, highlight_path=highlight or None)
            st.components.v1.html(html, height=520, scrolling=True)

with tab_opt:
    st.subheader("Оптимизация маршрутов")
    if graph is None:
        st.info("Сначала сгенери граф.")
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
            help="На сколько % можно просесть по якорю, пока ищем баланс по остальным KPI.",
        )

        if st.button("Погнали оптимизацию", type="primary"):
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
                st.success("Готово, маршруты посчитаны.")
            except Exception as e:
                st.error(f"Не вышло: {e}")

        res = st.session_state.get("optimization_results", {})
        if res:
            balanced = res.get("balanced", {})
            st.markdown("**Сбалансированный маршрут**")
            st.code(" → ".join(map(str, balanced.get("balanced_path", []))))
            bm = balanced.get("balanced_metrics", {})
            o1, o2, o3, o4 = st.columns(4)
            o1.metric("Затраты", f"{bm.get('total_cost', 0):.2f}")
            o2.metric("Время", f"{bm.get('total_time', 0):.2f}")
            o3.metric("Риск", f"{bm.get('total_risk', 0):.2f}")
            o4.metric("Баланс", f"{bm.get('balance_score', 0):.4f}")

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
        st.info("Сначала жми «Погнали оптимизацию» на вкладке «Маршруты».")
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
        v1.metric("Норм", kpi_summary["accepted"])
        v2.metric("Терпимо", kpi_summary["conditionally_accepted"])
        v3.metric("Плохо", kpi_summary["rejected"])

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

with tab_export:
    st.subheader("Отчёты и выгрузка")
    if graph is None:
        st.info("Пока нечего выгружать — нужен граф.")
    else:
        edge_df = pd.DataFrame(graph_to_edge_records(graph))
        res = st.session_state.get("optimization_results", {})
        reports = st.session_state.get("reports", {})
        optimal_df = localize_optimal_df(
            res.get("optimal_paths", optimal_paths_summary(graph, source, target))
        )
        ranked_df = localize_paths_df(res.get("ranked_paths", pd.DataFrame()))
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
            if st.button("Собрать PDF"):
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
                st.success(f"PDF лёг сюда: {pdf_path}")

        with col_b:
            csv_path = export_dir / f"edges_{ts}.csv"
            if st.button("Выгрузить рёбра в CSV"):
                export_csv(edge_df, csv_path)
                st.success(f"CSV: {csv_path}")

        with col_c:
            if st.button("Выгрузить JSON с результатами"):
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
                st.success(f"JSON: {json_path}")

        if "last_pdf" in st.session_state and Path(st.session_state["last_pdf"]).exists():
            with open(st.session_state["last_pdf"], "rb") as f:
                st.download_button("Скачать PDF", f, file_name=Path(st.session_state["last_pdf"]).name)

        png_path = Path("temp") / f"graph_{ts}.png"
        if st.button("Сохранить картинку графа (PNG)"):
            export_graph_png(graph, png_path, highlight_path=st.session_state.get("highlight_path"))
            with open(png_path, "rb") as f:
                st.download_button("Скачать PNG", f, file_name=png_path.name)
