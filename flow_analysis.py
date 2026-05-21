"""Проверки ограничений, узкие места и текстовые выводы для ЧАСТИ 2."""

from __future__ import annotations

from typing import Any

import networkx as nx
import pandas as pd

from flow_generator import DEFAULT_SINK, DEFAULT_SOURCE


def _net_flow_at_node(
    flow_dict: dict[int, dict[int, float]],
    node: int,
) -> float:
    """Чистый поток в узел: вход − выход."""
    inflow = sum(float(flow_dict.get(u, {}).get(node, 0)) for u in flow_dict)
    outflow = sum(float(flow_dict.get(node, {}).get(v, 0)) for v in flow_dict.get(node, {}))
    return inflow - outflow


def check_capacity_constraints(
    graph: nx.DiGraph,
    flow_dict: dict[int, dict[int, float]],
) -> pd.DataFrame:
    """Проверка: поток на ребре не превышает ёмкость."""
    rows: list[dict[str, Any]] = []
    ok_all = True
    for u, v, data in graph.edges(data=True):
        flow = float(flow_dict.get(u, {}).get(v, 0.0))
        cap = float(data.get("capacity", 0))
        violated = flow > cap + 1e-6
        if violated:
            ok_all = False
        rows.append(
            {
                "от": u,
                "до": v,
                "поток": round(flow, 4),
                "ёмкость": cap,
                "нарушение": "да" if violated else "нет",
            }
        )
    df = pd.DataFrame(rows)
    df.attrs["all_ok"] = ok_all
    return df


def check_flow_conservation(
    graph: nx.DiGraph,
    flow_dict: dict[int, dict[int, float]],
    source: int = DEFAULT_SOURCE,
    sink: int = DEFAULT_SINK,
) -> pd.DataFrame:
    """Баланс потока в промежуточных узлах (вход = выход)."""
    rows: list[dict[str, Any]] = []
    ok_all = True
    for n in sorted(graph.nodes()):
        net = _net_flow_at_node(flow_dict, n)
        if n == source:
            expected = "отдаёт поток (net ≤ 0)"
            ok = net <= 1e-6
        elif n == sink:
            expected = "принимает поток (net ≥ 0)"
            ok = net >= -1e-6
        else:
            expected = "0"
            ok = abs(net) < 1e-6
        if not ok:
            ok_all = False
        rows.append(
            {
                "узел": n,
                "чистый поток": round(net, 4),
                "ожидание": expected,
                "соблюдено": "да" if ok else "нет",
            }
        )
    df = pd.DataFrame(rows)
    df.attrs["all_ok"] = ok_all
    return df


def check_demand_satisfaction(
    graph: nx.DiGraph,
    flow_dict: dict[int, dict[int, float]],
) -> pd.DataFrame:
    """Проверка выполнения demand по узлам (min cost flow)."""
    rows: list[dict[str, Any]] = []
    ok_all = True
    for n in sorted(graph.nodes()):
        demand = float(graph.nodes[n].get("demand", 0))
        net = _net_flow_at_node(flow_dict, n)
        # NetworkX: inflow − outflow = demand
        residual = net - demand
        ok = abs(residual) < 1e-5
        if not ok:
            ok_all = False
        rows.append(
            {
                "узел": n,
                "demand": round(demand, 4),
                "чистый поток": round(net, 4),
                "остаток": round(residual, 4),
                "выполнено": "да" if ok else "нет",
            }
        )
    df = pd.DataFrame(rows)
    df.attrs["all_ok"] = ok_all
    return df


def max_flow_summary_text(result: dict[str, Any], checks_cap: pd.DataFrame, checks_bal: pd.DataFrame) -> str:
    """Краткое пояснение по maximum flow."""
    value = result.get("flow_value", 0)
    n_bottleneck = len(result.get("bottlenecks_df", [])) if result.get("bottlenecks_df") is not None else 0
    if hasattr(result.get("bottlenecks_df"), "__len__"):
        try:
            n_bottleneck = len(result["bottlenecks_df"])
        except TypeError:
            n_bottleneck = 0
    cap_ok = checks_cap.attrs.get("all_ok", True)
    bal_ok = checks_bal.attrs.get("all_ok", True)
    parts = [
        f"Максимальный поток от узла **{result.get('source')}** к узлу **{result.get('sink')}** "
        f"равен **{value:.4f}**.",
    ]
    if n_bottleneck:
        parts.append(
            f"Узких мест (рёбра с потоком = ёмкости): **{n_bottleneck}** — они ограничивают увеличение потока."
        )
    else:
        parts.append("Рёбер, полностью загруженных до ёмкости, не обнаружено (или поток распределён без насыщения всех дуг).")
    if cap_ok and bal_ok:
        parts.append("Ограничения по ёмкости и сохранению потока **выполнены**.")
    else:
        parts.append("**Внимание:** обнаружены нарушения ограничений — см. таблицы проверок.")
    return " ".join(parts)


def min_cost_flow_summary_text(
    total_cost: float,
    checks_demand: pd.DataFrame,
    checks_cap: pd.DataFrame,
) -> str:
    """Краткое пояснение по min cost flow."""
    dem_ok = checks_demand.attrs.get("all_ok", True)
    cap_ok = checks_cap.attrs.get("all_ok", True)
    parts = [f"Минимальная суммарная стоимость потока: **{total_cost:.4f}**."]
    if dem_ok:
        parts.append("Спрос/предложение по узлам **удовлетворены**.")
    else:
        parts.append("**Не все** demands выполнены — см. таблицу.")
    if cap_ok:
        parts.append("Ёмкости рёбер **не превышены**.")
    else:
        parts.append("Обнаружено превышение ёмкости на рёбрах.")
    return " ".join(parts)


def compare_flow_results(
    max_result: dict[str, Any] | None,
    min_cost_result: dict[str, Any] | None,
    graph: nx.DiGraph,
) -> str:
    """Сравнительный вывод max flow vs min cost flow."""
    if not max_result or not min_cost_result:
        return "Для сравнения выполните оба расчёта на одной и той же сети."
    max_val = float(max_result.get("flow_value", 0))
    mcf_dict = min_cost_result.get("flow_dict", {})
    flow_to_sink = sum(
        float(mcf_dict.get(u, {}).get(DEFAULT_SINK, 0))
        for u in graph.predecessors(DEFAULT_SINK)
    )
    total_cost = float(min_cost_result.get("total_cost", 0))
    supply = abs(float(graph.nodes[DEFAULT_SOURCE].get("demand", 0)))
    lines = [
        f"- **Maximum flow:** объём **{max_val:.4f}** (теоретический максимум source→sink).",
        f"- **Min cost flow:** в сток поступает **{flow_to_sink:.4f}** при заданном предложении "
        f"**{supply:.4f}** в источнике; суммарная стоимость **{total_cost:.4f}**.",
    ]
    if supply > 0 and abs(flow_to_sink - supply) < 1e-3:
        lines.append(
            "- Поток min cost согласован с постановкой спроса/предложения на той же сети."
        )
    if max_val > supply + 1e-6:
        lines.append(
            f"- Max flow ({max_val:.2f}) может превышать объём предложения в min cost ({supply:.2f}) — "
            "это разные постановки: max flow не учитывает demands."
        )
    lines.append(
        "- Max flow ищет **максимальный** объём; min cost flow — **минимальную стоимость** "
        "при фиксированном балансе узлов."
    )
    return "\n".join(lines)
