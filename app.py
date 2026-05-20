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


def _parse_path_string(path_str: str) -> list[int]:
    if not path_str or path_str == "N/A":
        return []
    s = str(path_str).strip()
    sep = " → " if " → " in s else ("→" if "→" in s else "-")
    return [int(x.strip()) for x in s.split(sep)]


def _step_banner(step: int) -> None:
    st.info(STEP_GOALS[step])


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


def _viz_controls() -> tuple[str, int]:
    """Общие настройки визуализации (шаг 1 задаёт значения для остальных шагов)."""
    if "viz_backend" not in st.session_state:
        st.session_state["viz_backend"] = "Graphviz"
    col1, col2 = st.columns(2)
    with col1:
        backend_ix = VIZ_BACKENDS.index(st.session_state["viz_backend"])
        st.session_state["viz_backend"] = st.selectbox(
            "Способ отображения",
            VIZ_BACKENDS,
            index=backend_ix,
            help="Graphviz — схема слева направо; Pyvis — интерактивный граф.",
        )
    with col2:
        st.session_state["edge_font_size"] = st.slider(
            "Размер подписей на рёбрах",
            min_value=7,
            max_value=22,
            value=int(st.session_state.get("edge_font_size", 11)),
            step=1,
        )
    return st.session_state["viz_backend"], int(st.session_state["edge_font_size"])


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
    st.title("SCM KPI Optimizer")
    st.caption("Курсовая работа: транспортная SCM-сеть и KPI маршрутов")
    st.markdown(
        "Приложение ведёт по **четырём этапам** слева направо по вкладкам. "
        "На каждом этапе указана цель; переходите по порядку **1 → 2 → 3 → 4**."
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
    max_target = (
        int(max(graph.nodes()))
        if graph is not None and graph.number_of_nodes()
        else int(st.session_state["target"])
    )
    st.session_state["target"] = max_target
    st.number_input("Сток (узел)", min_value=1, value=max_target, disabled=True)

source = int(st.session_state["source"])
target = int(st.session_state["target"])

st.title("Оптимизация транспортной SCM-сети")
st.markdown(
    "Модель — **ориентированный ациклический граф (DAG)**. На каждой дуге три показателя: "
    "**затраты**, **время**, **риск**. Далее — поиск оптимальных и сбалансированных маршрутов "
    "по методике курсовой работы."
)

tab_graph, tab_optima, tab_anchor, tab_kpi = st.tabs(
    [
        "① Модель сети",
        "② Оптимумы по KPI",
        "③ Итоговый маршрут",
        "④ Оценка KPI",
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
        num_nodes = st.slider("Число узлов", 9, 24, 12)
        edge_prob = st.slider("Вероятность доп. ребра", 0.1, 0.8, 0.35, 0.05)

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
        viz_backend, edge_font_size = _viz_controls()

        path_options = ["Без подсветки"] + [
            " → ".join(map(str, p))
            for p in enumerate_all_paths(graph, source, target)[:20]
        ]
        selected = st.selectbox("Подсветить маршрут (опционально)", path_options)
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
        viz_backend, edge_font_size = _viz_controls()
        col_a, col_b = st.columns([1, 3])
        with col_a:
            highlight_choice = st.radio(
                "Подсветить маршрут",
                ["Без подсветки", "по затратам", "по времени", "по риску"],
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
        p1, p2 = st.columns(2)
        with p1:
            anchor_ix = KPI_OPTIONS.index(st.session_state.get("selected_anchor_kpi", "cost"))
            st.session_state["selected_anchor_kpi"] = st.selectbox(
                "Якорный KPI",
                KPI_OPTIONS,
                index=anchor_ix,
                format_func=lambda k: KPI_LABELS[k],
                help="Главный критерий, для которого задаётся допуск от абсолютного оптимума.",
            )
        with p2:
            st.session_state["relaxation_percent"] = st.slider(
                "Допуск по якорю, %",
                10.0,
                15.0,
                float(st.session_state.get("relaxation_percent", 12.0)),
                0.5,
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
            viz_backend, edge_font_size = _viz_controls()
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
