"""
SCM KPI Optimizer — веб-приложение Streamlit для анализа транспортной SCM-сети.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from graph_generator import generate_random_dag, graph_summary
from graph_visualizer import visualize_graph_graphviz, visualize_graph_pyvis
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
from flow_analysis import (
    check_capacity_constraints,
    check_demand_satisfaction,
    check_flow_conservation,
    compare_flow_results,
    max_flow_summary_text,
    min_cost_flow_summary_text,
)
from flow_generator import (
    DEFAULT_SOURCE,
    DEMAND_HELP_MARKDOWN,
    flow_demands_to_records,
    flow_graph_to_edge_records,
    flow_network_summary,
    flow_sink_for_nodes,
    generate_random_flow_network,
)
from flow_optimizer import compute_maximum_flow, compute_min_cost_flow
from flow_session import initialize_flow_session, set_flow_graph
from flow_visualizer import visualize_flow_graphviz, visualize_flow_pyvis
from session_manager import initialize_session, render_session_io, reset_session, set_graph
from utils import (
    KPI_LABELS,
    graph_to_edge_records,
    localize_balance_df,
    localize_optimal_df,
    localize_paths_df,
)

KPI_OPTIONS = ["cost", "time", "risk"]
VIZ_BACKENDS = ["Graphviz", "Pyvis"]

STEP_GOALS = {
    1: (
        "**Цель:** сформировать ориентированную транспортную сеть (DAG) с весами на дугах "
        "— *затраты (c)*, *время (t)*, *риск (r)* в шкале 1–10 (меньше — лучше). "
        "Источник — узел **1**, сток — **последний** узел графа."
    ),
    2: (
        "**Цель:** для каждого KPI отдельно найти кратчайший маршрут алгоритмом **Дейкстры** "
        "(три независимых «идеала» по затратам, времени и риску). Эти значения — эталон для шагов 3–4."
    ),
    3: (
        "**Цель:** выбрать **якорный KPI** и допуск **10–15%**, отобрать маршруты с якорём не хуже порога "
        "и получить **один итоговый маршрут** с минимальной суммой отклонений по всем KPI."
    ),
    4: (
        "**Цель:** сравнить итоговый маршрут с индивидуальными оптимумами (шаг 2), "
        "оценить отклонения в % и вердикт: ≤20% — принято, ≤25% — условно, иначе — отклонено."
    ),
}

FLOW_STEP_GOALS = {
    1: (
        "**Цель:** построить **модель сети** — ориентированный граф: на рёбрах **ёмкость C** и **стоимость c**, "
        "на узлах **demand** (для min cost). Источник **s = 0**, сток **t = n−1**."
    ),
    2: (
        "**Цель:** на той же сети решить **maximum flow** — максимальный объём потока **s → t** "
        "при ограничениях ёмкостей (NetworkX `maximum_flow`)."
    ),
    3: (
        "**Цель:** на той же сети решить **min cost flow** — провести заданный объём из **s** в **t** "
        "с **минимальной суммарной стоимостью** (NetworkX `min_cost_flow`)."
    ),
}


def _parse_path_string(path_str: str) -> list[int]:
    if not path_str or path_str == "N/A":
        return []
    s = str(path_str).strip()
    sep = " → " if " → " in s else ("→" if "→" in s else "-")
    return [int(x.strip()) for x in s.split(sep)]


def _step_banner(step: int) -> None:
    st.info(STEP_GOALS[step])


def _flow_step_banner(step: int) -> None:
    st.info(FLOW_STEP_GOALS[step])


def _flow_roadmap(has_graph: bool, has_max: bool, has_mcf: bool) -> None:
    """Индикатор этапов ЧАСТИ 2 для навигации."""
    labels = ["① Модель", "② Max flow", "③ Min cost", "④ Сравнение"]
    flags = [has_graph, has_max, has_mcf, has_max and has_mcf]
    cols = st.columns(4)
    for col, label, done in zip(cols, labels, flags):
        with col:
            st.metric(label, "готово" if done else "ожидает")


def _render_flow_highlight(
    flow_graph,
    flow_dict: dict | None,
    viz_backend: str,
    edge_font_size: int,
) -> None:
    """Отрисовка сети потоков (Graphviz или Pyvis) с подсветкой потока на рёбрах."""
    if viz_backend == "Pyvis":
        st.components.v1.html(
            visualize_flow_pyvis(
                flow_graph,
                flow_dict=flow_dict,
                edge_font_size=edge_font_size,
            ),
            height=520,
            scrolling=True,
        )
    else:
        st.graphviz_chart(
            visualize_flow_graphviz(flow_graph, flow_dict=flow_dict),
            use_container_width=True,
        )


def _render_graph_highlight(
    graph,
    path: list[int] | None,
    viz_backend: str,
    edge_font_size: int,
) -> None:
    """Отрисовка графа (Graphviz или Pyvis) с подсветкой маршрута."""
    hp = path if path else None
    if viz_backend == "Pyvis":
        st.components.v1.html(
            visualize_graph_pyvis(graph, highlight_path=hp, edge_font_size=edge_font_size),
            height=520,
            scrolling=True,
        )
    else:
        st.graphviz_chart(
            visualize_graph_graphviz(graph, highlight_path=hp),
            use_container_width=True,
        )


def _get_viz_settings() -> tuple[str, int]:
    """Текущие настройки визуализации из session_state."""
    if "viz_backend" not in st.session_state:
        st.session_state["viz_backend"] = "Graphviz"
    if "edge_font_size" not in st.session_state:
        st.session_state["edge_font_size"] = 11
    return st.session_state["viz_backend"], int(st.session_state["edge_font_size"])


def _viz_controls_editor() -> tuple[str, int]:
    """Виджеты визуализации — только на этапе ① (иначе дублируются id виджетов)."""
    if "viz_backend" not in st.session_state:
        st.session_state["viz_backend"] = "Graphviz"
    if "edge_font_size" not in st.session_state:
        st.session_state["edge_font_size"] = 11
    col1, col2 = st.columns(2)
    with col1:
        st.selectbox(
            "Способ отображения",
            VIZ_BACKENDS,
            key="viz_backend",
            help="Graphviz — схема слева направо; Pyvis — интерактивный граф.",
        )
    with col2:
        st.slider(
            "Размер подписей на рёбрах",
            min_value=7,
            max_value=22,
            step=1,
            key="edge_font_size",
        )
    return _get_viz_settings()


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
initialize_flow_session()

with st.sidebar:
    st.title("SCM KPI Optimizer")
    st.caption("Курсовая работа: транспортная SCM-сеть и KPI маршрутов")
    st.markdown(
        "Приложение ведёт по **этапам** слева направо по вкладкам (①–④ — KPI, ⑤ — потоки). "
        "На каждом этапе указана цель; для KPI переходите **1 → 2 → 3 → 4**, для потоков — вкладка **⑤**."
    )
    st.divider()
    render_session_io()
    if st.button("Сбросить всё", use_container_width=True):
        reset_session()
        st.rerun()
    st.divider()
    st.markdown("**Маршрутизация в сети**")
    st.session_state["source"] = 1
    st.number_input("Источник (узел)", min_value=1, value=1, disabled=True)
    _g = st.session_state.get("graph")
    max_target = (
        int(max(_g.nodes()))
        if _g is not None and _g.number_of_nodes()
        else int(st.session_state["target"])
    )
    st.session_state["target"] = max_target
    st.number_input("Сток (узел)", min_value=1, value=max_target, disabled=True)

graph = st.session_state.get("graph")
source = int(st.session_state["source"])
target = int(st.session_state["target"])

st.title("Оптимизация транспортной SCM-сети")
st.markdown(
    "Модель — **ориентированный ациклический граф (DAG)**. На каждой дуге три показателя: "
    "**затраты**, **время**, **риск**. Далее — поиск оптимальных и сбалансированных маршрутов "
    "по методике курсовой работы."
)

tab_graph, tab_optima, tab_anchor, tab_kpi, tab_flow = st.tabs(
    [
        "① Модель сети",
        "② Оптимумы по KPI",
        "③ Итоговый маршрут",
        "④ Оценка KPI",
        "⑤ Потоки",
    ]
)

# ——— Шаг 1 ———
with tab_graph:
    _step_banner(1)

    st.subheader("Генерация графа")
    gen_left, gen_right = st.columns([3, 2])
    with gen_left:
        st.markdown(
            "Создайте случайную сеть или загрузите сохранённую сессию (боковая панель). "
            "После генерации ниже появятся **сводка**, таблица дуг и схема."
        )
    with gen_right:
        num_nodes = st.slider("Число узлов", 9, 24, 12, key="gen_num_nodes")
        edge_prob = st.slider("Вероятность доп. ребра", 0.1, 0.8, 0.35, 0.05, key="gen_edge_prob")

    if st.button("Сгенерировать граф", type="primary", use_container_width=True):
        g = generate_random_dag(
            num_nodes=num_nodes,
            edge_probability=edge_prob,
            random_seed=None,
        )
        set_graph(g)
        st.session_state["optimization_results"] = {}
        st.session_state["highlight_path"] = []
        st.success("Граф сформирован.")
        st.rerun()

    if graph is None:
        st.warning("Граф ещё не создан. Нажмите «Сгенерировать граф» или загрузите сессию.")
    else:
        summary = graph_summary(graph, source, target)
        st.subheader("Сводка по графу")
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Узлов", summary.get("nodes", 0))
        s2.metric("Рёбер", summary.get("edges", 0))
        s3.metric("Тип", "DAG" if summary.get("is_dag") else "Не DAG")
        s4.metric(f"Путь {source}→{target}", "есть" if summary.get("has_path") else "нет")

        st.subheader("Таблица дуг")
        st.dataframe(
            pd.DataFrame(graph_to_edge_records(graph)),
            use_container_width=True,
            hide_index=True,
        )

        st.divider()
        st.subheader("Схема сети")
        viz_backend, edge_font_size = _viz_controls_editor()

        path_options = ["Без подсветки"] + [
            " → ".join(map(str, p))
            for p in enumerate_all_paths(graph, source, target)[:20]
        ]
        selected = st.selectbox(
            "Подсветить маршрут (опционально)",
            path_options,
            key="path_highlight_step1",
        )
        if selected != "Без подсветки":
            highlight = [int(x) for x in selected.split(" → ")]
            st.session_state["highlight_path"] = highlight
        else:
            highlight = []
            st.session_state["highlight_path"] = []

        _render_graph_highlight(graph, highlight or None, viz_backend, edge_font_size)

# ——— Шаг 2 ———
with tab_optima:
    _step_banner(2)

    if graph is None:
        st.warning("Сначала выполните этап **① Модель сети**.")
    else:
        st.subheader("Три оптимальных маршрута")
        optimal_df_raw = optimal_paths_summary(graph, source, target)
        st.dataframe(
            localize_optimal_df(optimal_df_raw),
            use_container_width=True,
            hide_index=True,
        )

        paths_by_kpi: dict[str, list[int]] = {}
        for _, row in optimal_df_raw.iterrows():
            paths_by_kpi[str(row["kpi"])] = _parse_path_string(str(row.get("path", "")))

        st.subheader("Схема с подсветкой")
        st.caption(
            f"Отображение: **{st.session_state.get('viz_backend', 'Graphviz')}** "
            f"(настройки — на этапе ①)."
        )
        viz_backend, edge_font_size = _get_viz_settings()
        col_a, col_b = st.columns([1, 3])
        with col_a:
            highlight_choice = st.radio(
                "Подсветить маршрут",
                ["Без подсветки", "по затратам", "по времени", "по риску"],
                key="path_highlight_step2",
            )
        with col_b:
            key_map = {
                "по затратам": "cost",
                "по времени": "time",
                "по риску": "risk",
            }
            if highlight_choice == "Без подсветки":
                _render_graph_highlight(graph, None, viz_backend, edge_font_size)
            else:
                ph = paths_by_kpi.get(key_map[highlight_choice], [])
                _render_graph_highlight(graph, ph if ph else None, viz_backend, edge_font_size)

# ——— Шаг 3 ———
with tab_anchor:
    _step_banner(3)

    if graph is None:
        st.warning("Сначала выполните этап **① Модель сети**.")
    else:
        st.subheader("Параметры расчёта")
        if "selected_anchor_kpi" not in st.session_state:
            st.session_state["selected_anchor_kpi"] = "cost"
        if "relaxation_percent" not in st.session_state:
            st.session_state["relaxation_percent"] = 12.0
        p1, p2 = st.columns(2)
        with p1:
            st.selectbox(
                "Якорный KPI",
                KPI_OPTIONS,
                format_func=lambda k: KPI_LABELS[k],
                key="selected_anchor_kpi",
                help="Главный критерий, для которого задаётся допуск от абсолютного оптимума.",
            )
        with p2:
            st.slider(
                "Допуск по якорю, %",
                10.0,
                15.0,
                0.5,
                key="relaxation_percent",
            )

        if st.button("Рассчитать итоговый маршрут", type="primary", use_container_width=True):
            try:
                balanced = find_balanced_path(
                    graph,
                    st.session_state["selected_anchor_kpi"],
                    st.session_state["relaxation_percent"],
                    source,
                    target,
                )
                paths = enumerate_all_paths(graph, source, target)
                st.session_state["optimization_results"] = {
                    "balanced": balanced,
                    "ranked_paths": rank_paths(graph, paths, source, target),
                    "optimal_paths": optimal_paths_summary(graph, source, target),
                }
                st.session_state["highlight_path"] = balanced.get("balanced_path", [])
                st.success("Расчёт выполнен. Перейдите на этап **④ Оценка KPI**.")
            except Exception as e:
                st.error(f"Ошибка расчёта: {e}")

        res = st.session_state.get("optimization_results", {})
        if res:
            balanced = res.get("balanced", {})
            route = balanced.get("balanced_path", [])

            st.subheader("Результат")
            st.markdown("**Маршрут:**")
            st.code(" → ".join(map(str, route)) if route else "—")

            bm = balanced.get("balanced_metrics", {})
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Затраты", f"{bm.get('total_cost', 0):.2f}")
            m2.metric("Время", f"{bm.get('total_time', 0):.2f}")
            m3.metric("Риск", f"{bm.get('total_risk', 0):.2f}")
            status_ru = {
                "accepted": "принято",
                "conditionally_accepted": "условно",
                "rejected": "отклонено",
            }.get(str(balanced.get("solution_status", "")), "—")
            m4.metric("Предварительный статус", status_ru)

            anchor_ru = KPI_LABELS.get(str(balanced.get("anchor_kpi", "")), "")
            with st.expander("Подробности расчёта"):
                st.markdown(
                    f"- Якорь: **{anchor_ru}** · оптимум по якорю: **{balanced.get('anchor_optimal', 0):.2f}** · "
                    f"допуск **{balanced.get('relaxation_percent', 0):.1f}%** · "
                    f"порог **{balanced.get('anchor_limit', 0):.2f}**\n"
                    f"- Суммарное отклонение от оптимумов (шаг 2): **{bm.get('total_deviation', 0):.2f}%**"
                )

            st.subheader("Схема итогового маршрута")
            st.caption(
                f"Отображение: **{st.session_state.get('viz_backend', 'Graphviz')}** "
                f"(настройки — на этапе ①)."
            )
            viz_backend, edge_font_size = _get_viz_settings()
            _render_graph_highlight(graph, route or None, viz_backend, edge_font_size)

            with st.expander("Дополнительно: все маршруты (рейтинг)"):
                st.dataframe(
                    localize_paths_df(res.get("ranked_paths")),
                    use_container_width=True,
                    hide_index=True,
                )
        elif graph is not None:
            st.info("Задайте якорный KPI и допуск, затем нажмите «Рассчитать итоговый маршрут».")

# ——— Шаг 4 ———
with tab_kpi:
    _step_banner(4)

    if graph is None:
        st.warning("Сначала выполните этап **① Модель сети**.")
    elif not st.session_state.get("optimization_results"):
        st.warning("Сначала выполните этап **③ Итоговый маршрут**.")
    else:
        balanced = st.session_state["optimization_results"]["balanced"]
        current_path = balanced.get("balanced_path", [])
        current_m = calculate_path_metrics(graph, current_path)

        st.subheader("Итоговый маршрут")
        st.code(" → ".join(map(str, current_path)) if current_path else "—")

        optimal_m = balanced.get("per_kpi_optima")
        try:
            if not optimal_m:
                m_cost = calculate_path_metrics(graph, shortest_path_by_cost(graph, source, target))
                m_time = calculate_path_metrics(graph, shortest_path_by_time(graph, source, target))
                m_risk = calculate_path_metrics(graph, shortest_path_by_risk(graph, source, target))
                optimal_m = {
                    "total_cost": m_cost["total_cost"],
                    "total_time": m_time["total_time"],
                    "total_risk": m_risk["total_risk"],
                }
            p_cost = shortest_path_by_cost(graph, source, target)
            p_time = shortest_path_by_time(graph, source, target)
            p_risk = shortest_path_by_risk(graph, source, target)
            with st.expander("Эталонные маршруты (шаг 2)"):
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

        st.subheader("Вердикт")
        overall_ru = {
            "accepted": "Принято",
            "conditionally_accepted": "Условно принято",
            "rejected": "Отклонено",
        }.get(str(kpi_summary["overall"]), "—")

        if kpi_summary["overall"] == "accepted":
            st.success(f"**{overall_ru}** — все KPI в пределах 20% от индивидуальных оптимумов.")
        elif kpi_summary["overall"] == "conditionally_accepted":
            st.warning(f"**{overall_ru}** — есть KPI в диапазоне 20–25%.")
        else:
            st.error(f"**{overall_ru}** — измените якорь или допуск на этапе ③ и пересчитайте.")

        c1, c2, c3 = st.columns(3)
        c1.metric("KPI ≤ 20%", kpi_summary["accepted"])
        c2.metric("KPI 20–25%", kpi_summary["conditionally_accepted"])
        c3.metric("KPI > 25%", kpi_summary["rejected"])

        st.subheader("Сравнение с оптимумами")
        st.caption(
            "По каждому KPI: сумма по итоговому маршруту, индивидуальный оптимум (шаг 2), "
            "отклонение %, статус строки."
        )
        st.dataframe(localize_balance_df(balance_df), use_container_width=True, hide_index=True)

        used_anchor = balanced.get("requested_anchor_kpi") or balanced.get("anchor_kpi", "cost")
        used_relax = balanced.get("requested_relaxation_percent", balanced.get("relaxation_percent"))
        st.caption(
            f"Параметры этапа ③: якорь — **{KPI_LABELS.get(str(used_anchor), used_anchor)}**, "
            f"допуск — **{float(used_relax):.1f}%**."
        )

        with st.expander("Пояснения"):
            for rec in recommendations:
                st.markdown(f"- {rec}")

        st.session_state["reports"] = {
            "kpi_balance_df": localize_balance_df(balance_df),
            "kpi_summary": kpi_summary,
            "recommendations": recommendations,
            "anchor_kpi_used": used_anchor,
        }

# ——— ЧАСТЬ 2: Потоки ———
with tab_flow:
    flow_graph = st.session_state.get("flow_graph")
    flow_source = int(st.session_state.get("flow_source", DEFAULT_SOURCE))
    flow_sink = int(st.session_state.get("flow_sink", 4))
    max_res = st.session_state.get("flow_max_result")
    mcf_res = st.session_state.get("flow_mcf_result")

    st.subheader("ЧАСТЬ 2. Сетевые потоки")
    st.markdown(
        "Отдельная модель от вкладок ①–④ (KPI-маршруты). Здесь строится **одна ориентированная сеть**, "
        "на которой последовательно решаются **две задачи**:"
    )
    st.markdown(
        "| Этап | Что строим / считаем | Данные на рёбрах | Данные на узлах |\n"
        "|------|----------------------|------------------|------------------|\n"
        "| **① Модель** | случайный граф потоков | ёмкость **C**, стоимость **c** | **demand** (для min cost) |\n"
        "| **② Max flow** | максимальный объём **s → t** | поток **f** ≤ C | — |\n"
        "| **③ Min cost** | тот же объём с min Σ c·f | поток **f** ≤ C | баланс demand |\n"
        "| **④ Сравнение** | вывод по двум постановкам | — | — |"
    )

    with st.expander("Что такое demand и знак «минус/плюс»?", expanded=False):
        st.markdown(DEMAND_HELP_MARKDOWN)

    _flow_roadmap(flow_graph is not None, max_res is not None, mcf_res is not None)

    # ——— ① Модель сети ———
    st.divider()
    _flow_step_banner(1)
    st.subheader("① Модель сети (генерация)")

    gen_left, gen_right = st.columns([2, 1])
    with gen_left:
        flow_num_nodes = st.slider(
            "Число узлов",
            min_value=4,
            max_value=12,
            key="flow_num_nodes",
            help="Узлы нумеруются 0, 1, …, n−1. Источник s = 0, сток t = n−1.",
        )
        flow_edge_prob = st.slider(
            "Вероятность доп. ребра",
            0.15,
            0.75,
            0.45,
            0.05,
            key="flow_gen_edge_prob",
        )
    with gen_right:
        preview_sink = flow_sink_for_nodes(flow_num_nodes, flow_source)
        st.markdown("**Топология (фикс.)**")
        st.metric("Источник s", flow_source)
        st.metric("Сток t", preview_sink)
        st.caption(f"Опорный путь: **{' → '.join(map(str, range(flow_source, preview_sink + 1)))}**")

    if st.button("Сгенерировать случайный граф", type="primary", use_container_width=True, key="btn_gen_flow"):
        try:
            g_flow = generate_random_flow_network(
                num_nodes=flow_num_nodes,
                edge_probability=flow_edge_prob,
                source=flow_source,
                sink=preview_sink,
                random_seed=None,
            )
            set_flow_graph(
                g_flow,
                source=flow_source,
                sink=preview_sink,
                num_nodes=flow_num_nodes,
            )
            st.success(f"Сеть сформирована: {flow_num_nodes} узлов, s={flow_source}, t={preview_sink}.")
            st.rerun()
        except Exception as e:
            st.error(f"Ошибка генерации: {e}")

    if flow_graph is None:
        st.warning("Модель ещё не построена. Задайте число узлов и нажмите «Сгенерировать случайный граф».")
    else:
        model_nodes = int(st.session_state.get("flow_model_nodes", flow_graph.number_of_nodes()))
        if flow_graph.number_of_nodes() != flow_num_nodes:
            st.warning(
                f"В слайдере **{flow_num_nodes}** узлов, в сохранённой модели — **{model_nodes}**. "
                "Перегенерируйте граф, чтобы обновить топологию."
            )
        fsummary = flow_network_summary(flow_graph, flow_source, flow_sink)
        st.markdown(
            f"**Текущая модель:** узлы **0…{fsummary.get('nodes', 0) - 1}**, "
            f"дуги с (**C**, **c**), баланс спроса **{fsummary.get('supply_amount', 0):.0f}** ед. "
            f"(из **s={flow_source}** в **t={flow_sink}**)."
        )
        f1, f2, f3, f4, f5 = st.columns(5)
        f1.metric("Узлов", fsummary.get("nodes", 0))
        f2.metric("Рёбер", fsummary.get("edges", 0))
        f3.metric(f"Путь s→t", "есть" if fsummary.get("has_path") else "нет")
        f4.metric("Объём F (min cost)", f"{fsummary.get('supply_amount', 0):.0f}")
        f5.metric("Модель OK", "да" if fsummary.get("is_valid") else "нет")

        t_edges, t_dem, t_legend = st.tabs(["Рёбра (C, c)", "Узлы (demand)", "Обозначения"])
        with t_edges:
            st.caption("Каждая дуга **u → v**: максимальный поток **C**, стоимость единицы **c**.")
            st.dataframe(
                pd.DataFrame(flow_graph_to_edge_records(flow_graph)),
                use_container_width=True,
                hide_index=True,
            )
        with t_dem:
            st.caption("Баланс для min cost flow: **demand_s < 0**, **demand_t > 0**, транзит = 0.")
            st.dataframe(
                pd.DataFrame(flow_demands_to_records(flow_graph, flow_source, flow_sink)),
                use_container_width=True,
                hide_index=True,
            )
        with t_legend:
            st.markdown(
                "- **s** (зелёный) — источник, узел 0\n"
                "- **t** (красный) — сток, последний узел\n"
                "- Подпись на дуге: **C** — ёмкость, **c** — стоимость; после расчёта добавляется **f** — поток\n"
                "- Max flow использует только **C**; min cost — **C**, **c** и **demand**"
            )

        st.subheader("Схема модели (без потока)")
        if "flow_viz_backend" not in st.session_state:
            st.session_state["flow_viz_backend"] = st.session_state.get("viz_backend", "Graphviz")
        fc1, fc2 = st.columns(2)
        with fc1:
            flow_viz = st.selectbox(
                "Способ отображения",
                VIZ_BACKENDS,
                key="flow_viz_backend",
            )
        with fc2:
            flow_font = st.slider(
                "Размер подписей на рёбрах",
                min_value=7,
                max_value=22,
                step=1,
                key="flow_edge_font_size",
                value=int(st.session_state.get("edge_font_size", 11)),
            )
        _render_flow_highlight(flow_graph, None, flow_viz, flow_font)

        # ——— ② Maximum Flow ———
        st.divider()
        _flow_step_banner(2)
        st.subheader("② Maximum flow")
        st.caption(
            "Вопрос задачи: *сколько единиц потока максимум можно провести из s в t?* "
            "Demands **не участвуют** — только ёмкости рёбер."
        )

        if st.button(
            "Рассчитать максимальный поток",
            type="primary",
            use_container_width=True,
            key="btn_max_flow",
        ):
            try:
                st.session_state["flow_max_result"] = compute_maximum_flow(
                    flow_graph, flow_source, flow_sink
                )
                st.success("Maximum flow рассчитан.")
                st.rerun()
            except Exception as e:
                st.error(f"Ошибка расчёта: {e}")

        max_res = st.session_state.get("flow_max_result")
        if max_res:
            m1, m2, m3 = st.columns(3)
            m1.metric("Макс. поток |f|", f"{max_res.get('flow_value', 0):.0f}")
            bdf = max_res.get("bottlenecks_df", pd.DataFrame())
            n_bn = len(bdf) if bdf is not None and not bdf.empty else 0
            m2.metric("Bottleneck-рёбер", n_bn)
            m3.metric("Пара (s, t)", f"{flow_source} → {flow_sink}")

            checks_cap = check_capacity_constraints(flow_graph, max_res["flow_dict"])
            checks_bal = check_flow_conservation(
                flow_graph, max_res["flow_dict"], flow_source, flow_sink
            )
            st.markdown(max_flow_summary_text(max_res, checks_cap, checks_bal))

            st.markdown("**Поток на рёбрах** (f > 0)")
            st.dataframe(
                max_res.get("edge_df", pd.DataFrame()),
                use_container_width=True,
                hide_index=True,
            )

            with st.expander("Узкие места и проверки"):
                st.markdown("**Bottleneck** — рёбра, где f = C.")
                if n_bn:
                    st.dataframe(bdf, use_container_width=True, hide_index=True)
                else:
                    st.caption("Нет полностью загруженных рёбер.")
                st.markdown("**Ёмкости**")
                st.dataframe(checks_cap, use_container_width=True, hide_index=True)
                st.markdown("**Баланс в узлах**")
                st.dataframe(checks_bal, use_container_width=True, hide_index=True)

            st.caption("Зелёные дуги — ненулевой поток (max flow).")
            _render_flow_highlight(
                flow_graph,
                max_res.get("flow_dict"),
                st.session_state.get("flow_viz_backend", "Graphviz"),
                int(st.session_state.get("flow_edge_font_size", 11)),
            )
        else:
            st.info("Сначала постройте модель (①), затем запустите расчёт max flow.")

        # ——— ③ Min Cost Flow ———
        st.divider()
        _flow_step_banner(3)
        st.subheader("③ Minimum cost flow")
        st.caption(
            f"Вопрос задачи: *как провести **{fsummary.get('supply_amount', 0):.0f}** ед. из s в t "
            f"с минимальной суммой c·f?* Используются **demand**, **C** и **c**."
        )

        if st.button(
            "Рассчитать поток минимальной стоимости",
            type="primary",
            use_container_width=True,
            key="btn_mcf",
        ):
            try:
                st.session_state["flow_mcf_result"] = compute_min_cost_flow(flow_graph)
                st.success("Min cost flow рассчитан.")
                st.rerun()
            except Exception as e:
                st.error(f"Ошибка расчёта: {e}")

        mcf_res = st.session_state.get("flow_mcf_result")
        if mcf_res:
            c1, c2, c3 = st.columns(3)
            c1.metric("Стоимость Σ c·f", f"{mcf_res.get('total_cost', 0):.0f}")
            edge_df = mcf_res.get("edge_df", pd.DataFrame())
            c2.metric("Рёбер с f > 0", len(edge_df) if edge_df is not None else 0)
            c3.metric("Σ demand", "0 ✓")

            checks_dem = check_demand_satisfaction(flow_graph, mcf_res["flow_dict"])
            checks_cap_mcf = check_capacity_constraints(flow_graph, mcf_res["flow_dict"])
            st.markdown(
                min_cost_flow_summary_text(
                    float(mcf_res.get("total_cost", 0)),
                    checks_dem,
                    checks_cap_mcf,
                )
            )

            st.markdown("**Поток на рёбрах** (min cost)")
            st.dataframe(edge_df, use_container_width=True, hide_index=True)

            with st.expander("Баланс demand и ёмкости"):
                st.dataframe(checks_dem, use_container_width=True, hide_index=True)
                st.dataframe(checks_cap_mcf, use_container_width=True, hide_index=True)

            st.caption("Зелёные дуги — ненулевой поток (min cost).")
            _render_flow_highlight(
                flow_graph,
                mcf_res.get("flow_dict"),
                st.session_state.get("flow_viz_backend", "Graphviz"),
                int(st.session_state.get("flow_edge_font_size", 11)),
            )
        else:
            st.info("Сначала постройте модель (①), затем запустите min cost flow.")

        # ——— ④ Сравнение ———
        max_res = st.session_state.get("flow_max_result")
        mcf_res = st.session_state.get("flow_mcf_result")
        if max_res and mcf_res:
            st.divider()
            st.subheader("④ Сравнение постановок")
            st.markdown(compare_flow_results(max_res, mcf_res, flow_graph))
        elif flow_graph is not None:
            st.divider()
            st.caption("④ Сравнение появится после расчётов **②** и **③**.")
