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
)
from path_optimizer import (
    calculate_path_metrics,
    enumerate_all_paths,
    find_balanced_path,
    optimal_paths_summary,
    rank_paths,
    shortest_path_by_cost,
    shortest_path_by_risk,
    shortest_path_by_time,
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


def _parse_path_string(path_str: str) -> list[int]:
    if not path_str or path_str == "N/A":
        return []
    s = str(path_str).strip()
    sep = " → " if " → " in s else ("→" if "→" in s else "-")
    return [int(x.strip()) for x in s.split(sep)]


def _render_graph_highlight(
    graph,
    path: list[int] | None,
    viz_backend: str,
    edge_font_size: int,
) -> None:
    """Отрисовка графа с подсветкой маршрута (общий блок для нескольких вкладок)."""
    hp = path if path else None
    if viz_backend == "Graphviz":
        st.graphviz_chart(
            visualize_graph_graphviz(graph, highlight_path=hp),
            use_container_width=True,
        )
    elif viz_backend == "Plotly":
        st.plotly_chart(
            visualize_graph_plotly(graph, highlight_path=hp, edge_font_size=edge_font_size),
            use_container_width=True,
        )
    elif viz_backend == "Matplotlib":
        st.pyplot(
            visualize_graph_matplotlib(graph, highlight_path=hp, edge_font_size=edge_font_size)
        )
    else:
        st.components.v1.html(
            visualize_graph_pyvis(graph, highlight_path=hp, edge_font_size=edge_font_size),
            height=520,
            scrolling=True,
        )


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
    st.markdown(
        "**Сценарий (по шагам):**\n"
        "1. Модель сети — генерация и визуализация.\n"
        "2. Оптимумы по KPI — три кратчайших пути (Дейкстра).\n"
        "3. Якорь и допуск — один итоговый маршрут.\n"
        "4. Оценка отклонений — сравнение с оптимумами и пороги 20%/25%."
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
    "Этапная демонстрация: модель сети (источник 1 → сток — последний узел), "
    "отдельные оптимумы по стоимости, времени и риску, затем якорный KPI с допуском 10–15% "
    "и оценка отклонений выбранного маршрута."
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

tab_graph, tab_optima, tab_anchor, tab_kpi = st.tabs(
    [
        "1. Модель сети",
        "2. Оптимумы по KPI",
        "3. Якорь и баланс",
        "4. Оценка отклонений",
    ]
)

with tab_graph:
    st.markdown(
        "**Шаг 1.** Задайте транспортную сеть как DAG: сгенерируйте граф или загрузите сессию. "
        "Проверьте таблицу дуг (веса *c*, *t*, *r* — чем меньше, тем лучше) и визуализацию."
    )
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

        _render_graph_highlight(graph, highlight or None, viz_backend, edge_font_size)

with tab_optima:
    st.markdown(
        "**Шаг 2.** Для каждого критерия отдельно вычисляется кратчайший путь "
        "(алгоритм Дейкстры, `networkx.shortest_path` с весом *cost* / *time* / *risk*). "
        "Сравните три маршрута и при необходимости подсветьте выбранный на схеме."
    )
    st.subheader("Оптимальные маршруты по отдельным KPI")
    if graph is None:
        st.info("Сначала выполните шаг 1: сформируйте граф на вкладке «1. Модель сети».")
    else:
        optimal_df_raw = optimal_paths_summary(graph, source, target)
        st.dataframe(
            localize_optimal_df(optimal_df_raw),
            use_container_width=True,
            hide_index=True,
        )

        paths_by_kpi: dict[str, list[int]] = {}
        for _, row in optimal_df_raw.iterrows():
            k = str(row["kpi"])
            paths_by_kpi[k] = _parse_path_string(str(row.get("path", "")))

        col_a, col_b = st.columns([1, 2])
        with col_a:
            highlight_choice = st.radio(
                "Подсветить на схеме маршрут, оптимальный по",
                ["Не подсвечивать", "затраты (cost)", "время (time)", "риск (risk)"],
                horizontal=False,
            )
        with col_b:
            viz_backend_o = st.session_state.get("viz_backend", "Graphviz")
            edge_fs_o = int(st.session_state.get("edge_font_size", 11))
            if highlight_choice == "Не подсвечивать":
                _render_graph_highlight(graph, None, viz_backend_o, edge_fs_o)
            else:
                key = {"затраты (cost)": "cost", "время (time)": "time", "риск (risk)": "risk"}[
                    highlight_choice
                ]
                ph = paths_by_kpi.get(key, [])
                _render_graph_highlight(graph, ph if ph else None, viz_backend_o, edge_fs_o)

with tab_anchor:
    st.markdown(
        "**Шаг 3.** Выберите **якорный KPI** и допуск **10–15%**. "
        "Сначала считается абсолютный оптимум по якорю, затем задаётся ослаблённый порог. "
        "Среди всех маршрутов, укладывающихся в этот порог, выбирается **один итоговый маршрут** "
        "с минимальной суммой отклонений по затратам, времени и риску (относительно оптимумов шага 2)."
    )
    st.subheader("Маршрут при ослабленном якорном KPI")
    if graph is None:
        st.info("Сначала выполните шаг 1: сформируйте граф.")
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
            route = balanced.get("balanced_path", [])
            st.markdown("**Итоговый маршрут**")
            st.code(" → ".join(map(str, route)) if route else "—")

            anchor_ru = KPI_LABELS.get(str(balanced.get("anchor_kpi", "")), balanced.get("anchor_kpi", ""))
            with st.expander("Как получен маршрут (якорь и допуск)"):
                st.markdown(
                    f"- Якорный KPI: **{anchor_ru}**\n"
                    f"- Абсолютный оптимум по якорю: **{balanced.get('anchor_optimal', 0):.2f}**\n"
                    f"- Допуск: **{balanced.get('relaxation_percent', 0):.1f}%** "
                    f"(порог: **{balanced.get('anchor_limit', 0):.2f}**)\n"
                    f"- Итоговый маршрут — лучший среди путей с якорём ≤ порога "
                    f"по минимальной сумме отклонений остальных KPI.\n"
                    f"- Абсолютный оптимум только по якорю см. на **шаге 2** "
                    f"(отдельная строка таблицы для выбранного KPI)."
                )

            bm = balanced.get("balanced_metrics", {})
            o1, o2, o3, o4 = st.columns(4)
            o1.metric("Затраты", f"{bm.get('total_cost', 0):.2f}")
            o2.metric("Время", f"{bm.get('total_time', 0):.2f}")
            o3.metric("Риск", f"{bm.get('total_risk', 0):.2f}")
            status_ru = {
                "accepted": "принято",
                "conditionally_accepted": "условно",
                "rejected": "отклонено",
            }.get(str(balanced.get("solution_status", "")), "—")
            o4.metric("Статус решения", status_ru)
            st.metric(
                "Суммарное отклонение KPI, %",
                f"{bm.get('total_deviation', 0):.2f}",
                help="Сумма отклонений затрат, времени и риска от индивидуальных оптимумов.",
            )

            st.markdown("**Визуализация итогового маршрута**")
            viz_backend = st.session_state.get("viz_backend", "Graphviz")
            _render_graph_highlight(graph, route or None, viz_backend, edge_font_size)

            st.caption("Три независимых оптимума по одному KPI — на шаге 2.")
            st.markdown("**Все маршруты (рейтинг)**")
            st.dataframe(
                localize_paths_df(res.get("ranked_paths")),
                use_container_width=True,
                hide_index=True,
            )

with tab_kpi:
    st.markdown(
        "**Шаг 4.** Сравните итоговые суммы **маршрута с шага 3** с индивидуальными оптимумами, "
        "оцените отклонения в процентах и правила приёмки: до **20%** — допустимо, до **25%** — условно, "
        "иначе смените якорный KPI или допуск и повторите шаг 3."
    )
    st.subheader("Разбор KPI")
    if graph is None or not st.session_state.get("optimization_results"):
        st.info("Сначала выполните шаг 3: расчёт на вкладке «3. Якорь и баланс».")
    else:
        balanced = st.session_state["optimization_results"]["balanced"]
        current_path = balanced.get("balanced_path", [])
        current_m = calculate_path_metrics(graph, current_path)

        st.markdown("**С чем сравниваем**")
        st.markdown(
            "- **Текущий маршрут** — итоговый путь с шага 3 (ослабленный якорь + минимум суммарного отклонения).\n"
            "- **Оптимум по каждому KPI** — отдельно: минимально возможная сумма по этому показателю среди всех "
            "маршрутов из источника в сток (кратчайший путь по весу `cost`, `time` или `risk`, алгоритм Дейкстры). "
            "Три оптимума в общем случае относятся к **разным** маршрутам; в таблице ниже для каждой строки KPI "
            "в столбце «оптимум» указано именно **индивидуальное** лучшее значение по этому показателю.\n"
            "- **Отклонение %** — отношение прироста к оптимуму в процентах: "
            "(текущий − оптимум) / оптимум × 100. "
            "Чем меньше значение показателя, тем лучше; положительное отклонение означает ухудшение относительно "
            "идеала по данному KPI."
        )

        optimal_m = balanced.get("per_kpi_optima")
        try:
            if not optimal_m:
                p_cost = shortest_path_by_cost(graph, source, target)
                m_cost = calculate_path_metrics(graph, p_cost)
                p_time = shortest_path_by_time(graph, source, target)
                m_time = calculate_path_metrics(graph, p_time)
                p_risk = shortest_path_by_risk(graph, source, target)
                m_risk = calculate_path_metrics(graph, p_risk)
                optimal_m = {
                    "total_cost": m_cost["total_cost"],
                    "total_time": m_time["total_time"],
                    "total_risk": m_risk["total_risk"],
                }
            else:
                p_cost = shortest_path_by_cost(graph, source, target)
                p_time = shortest_path_by_time(graph, source, target)
                p_risk = shortest_path_by_risk(graph, source, target)
            with st.expander("Маршруты, на которых достигаются индивидуальные оптимумы"):
                st.markdown(
                    f"| KPI | Маршрут |\n|-----|--------|\n"
                    f"| Затраты | `{' → '.join(map(str, p_cost))}` |\n"
                    f"| Время | `{' → '.join(map(str, p_time))}` |\n"
                    f"| Риск | `{' → '.join(map(str, p_risk))}` |"
                )
        except Exception:
            optimal_m = current_m

        balance_df = analyze_kpi_balance(current_m, optimal_m)
        kpi_summary = generate_kpi_summary(
            balance_df,
            solution_status=balanced.get("solution_status"),
        )
        recommendations = build_recommendations(
            kpi_summary, {}, balance_df, balanced_result=balanced
        )

        v1, v2, v3 = st.columns(3)
        v1.metric("Принято", kpi_summary["accepted"])
        v2.metric("Условно принято", kpi_summary["conditionally_accepted"])
        v3.metric("Отклонено", kpi_summary["rejected"])

        if kpi_summary["overall"] != "accepted":
            st.warning(kpi_summary["explanation"])
        else:
            st.success(kpi_summary["explanation"])

        st.markdown("**Таблица сравнения** — по каждой строке: текущие суммы сбалансированного маршрута, "
                    "индивидуальный оптимум по этому KPI, отклонение в % и статус (20% / 25%).")
        st.dataframe(localize_balance_df(balance_df), use_container_width=True, hide_index=True)

        used_anchor = balanced.get("requested_anchor_kpi") or balanced.get("anchor_kpi", "cost")
        used_relax = balanced.get("requested_relaxation_percent", balanced.get("relaxation_percent"))
        anchor_ru = KPI_LABELS.get(str(used_anchor), str(used_anchor))
        st.markdown(
            f"**Параметры расчёта (шаг 3):** якорный KPI — **{anchor_ru}**, "
            f"допуск **{float(used_relax):.1f}%**. "
            f"Отклонения в таблице выше относятся **только к итоговому маршруту**, "
            f"а не к среднему по всем путям сети."
        )
        for rec in recommendations:
            st.markdown(f"- {rec}")

        st.session_state["reports"] = {
            "kpi_balance_df": localize_balance_df(balance_df),
            "kpi_summary": kpi_summary,
            "recommendations": recommendations,
            "anchor_kpi_used": used_anchor,
        }
