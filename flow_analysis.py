"""Проверки ограничений, узкие места и текстовые выводы для ЧАСТИ 2."""

from __future__ import annotations

from typing import Any

import networkx as nx
import pandas as pd

FLOW_TOL = 1e-5


def inflow_at_node(
    flow_dict: dict[int, dict[int, float]],
    graph: nx.DiGraph,
    node: int,
) -> float:
    """Суммарный поток в узел (по входящим дугам)."""
    return sum(
        float(flow_dict.get(u, {}).get(node, 0.0))
        for u in graph.predecessors(node)
    )


def outflow_at_node(flow_dict: dict[int, dict[int, float]], node: int) -> float:
    """Суммарный поток из узла (по исходящим дугам)."""
    return sum(float(flow_dict.get(node, {}).get(v, 0.0)) for v in flow_dict.get(node, {}))


def net_flow_at_node(
    flow_dict: dict[int, dict[int, float]],
    graph: nx.DiGraph,
    node: int,
) -> float:
    """Чистый поток в узел: вход − выход (конвенция NetworkX)."""
    return inflow_at_node(flow_dict, graph, node) - outflow_at_node(flow_dict, node)


def supply_from_demands(graph: nx.DiGraph, source: int, sink: int) -> float:
    """Объём F по постановке min cost: |demand_s| = demand_t при s<0, t>0."""
    d_s = float(graph.nodes[source].get("demand", 0))
    d_t = float(graph.nodes[sink].get("demand", 0))
    if d_s < 0:
        return abs(d_s)
    if d_t > 0:
        return d_t
    return max(abs(d_s), abs(d_t))


def check_capacity_constraints(
    graph: nx.DiGraph,
    flow_dict: dict[int, dict[int, float]],
) -> pd.DataFrame:
    """Поток на каждом ребре не превышает ёмкость."""
    rows: list[dict[str, Any]] = []
    ok_all = True
    for u, v, data in graph.edges(data=True):
        flow = float(flow_dict.get(u, {}).get(v, 0.0))
        cap = float(data.get("capacity", 0))
        violated = flow > cap + FLOW_TOL
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
    source: int,
    sink: int,
    *,
    flow_value: float | None = None,
) -> pd.DataFrame:
    """
    Баланс потока (maximum flow).

    Промежуточные: вход = выход.
    При заданном flow_value: из s выходит F, в t входит F (net_s = −F, net_t = +F).
    """
    rows: list[dict[str, Any]] = []
    ok_all = True
    f_expected = float(flow_value) if flow_value is not None else None

    for n in sorted(graph.nodes()):
        net = net_flow_at_node(flow_dict, graph, n)
        out_f = outflow_at_node(flow_dict, n)
        in_f = inflow_at_node(flow_dict, graph, n)

        if n == source and f_expected is not None:
            expected = f"отдаёт F={f_expected:.4f} (выход−вход)"
            ok = abs((out_f - in_f) - f_expected) < FLOW_TOL
        elif n == sink and f_expected is not None:
            expected = f"принимает F={f_expected:.4f} (вход−выход)"
            ok = abs((in_f - out_f) - f_expected) < FLOW_TOL
        elif n == source:
            expected = "источник (отдаёт)"
            ok = (out_f - in_f) > -FLOW_TOL
        elif n == sink:
            expected = "сток (принимает)"
            ok = (in_f - out_f) > -FLOW_TOL
        else:
            expected = "транзит: вход = выход"
            ok = abs(net) < FLOW_TOL

        if not ok:
            ok_all = False
        rows.append(
            {
                "узел": n,
                "вход": round(in_f, 4),
                "выход": round(out_f, 4),
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
    source: int,
    sink: int,
) -> pd.DataFrame:
    """
    Min cost flow: для каждого узла inflow − outflow = demand;
    дополнительно Σ demand = 0.
    """
    demand_sum = sum(float(graph.nodes[n].get("demand", 0)) for n in graph.nodes())
    rows: list[dict[str, Any]] = []
    ok_all = abs(demand_sum) < FLOW_TOL

    for n in sorted(graph.nodes()):
        demand = float(graph.nodes[n].get("demand", 0))
        net = net_flow_at_node(flow_dict, graph, n)
        residual = net - demand
        ok = abs(residual) < FLOW_TOL
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
    df.attrs["demand_sum"] = round(demand_sum, 6)
    df.attrs["supply"] = supply_from_demands(graph, source, sink)
    return df


def max_flow_summary_text(result: dict[str, Any], checks_cap: pd.DataFrame, checks_bal: pd.DataFrame) -> str:
    """Краткое пояснение по maximum flow."""
    value = float(result.get("flow_value", 0))
    src = result.get("source", "?")
    snk = result.get("sink", "?")
    bdf = result.get("bottlenecks_df")
    n_bottleneck = len(bdf) if bdf is not None and hasattr(bdf, "__len__") and not getattr(bdf, "empty", True) else 0

    cap_ok = checks_cap.attrs.get("all_ok", True)
    bal_ok = checks_bal.attrs.get("all_ok", True)
    parts = [
        f"Максимальный поток **s={src} → t={snk}** равен **{value:.4f}**.",
    ]
    if n_bottleneck:
        parts.append(f"Узких мест (f = C): **{n_bottleneck}**.")
    else:
        parts.append("Полностью загруженных bottleneck-рёбер нет.")
    if cap_ok and bal_ok:
        parts.append("Ёмкости и баланс потока **соблюдены**.")
    else:
        parts.append("**Есть нарушения** — см. таблицы проверок.")
    return " ".join(parts)


def min_cost_flow_summary_text(
    total_cost: float,
    checks_demand: pd.DataFrame,
    checks_cap: pd.DataFrame,
    *,
    source: int,
    sink: int,
) -> str:
    """Краткое пояснение по min cost flow."""
    dem_ok = checks_demand.attrs.get("all_ok", True)
    cap_ok = checks_cap.attrs.get("all_ok", True)
    supply = float(checks_demand.attrs.get("supply", 0))
    d_sum = checks_demand.attrs.get("demand_sum", 0)
    parts = [
        f"Минимальная стоимость **s={source} → t={sink}**: **{total_cost:.4f}** "
        f"(объём постановки **F={supply:.4f}**).",
    ]
    if abs(float(d_sum)) < FLOW_TOL:
        parts.append("Σ demand = **0**.")
    else:
        parts.append(f"**Σ demand = {d_sum}** (должно быть 0).")
    if dem_ok:
        parts.append("Балансы demand **выполнены**.")
    else:
        parts.append("**Не все** demand выполнены.")
    if cap_ok:
        parts.append("Ёмкости **не превышены**.")
    else:
        parts.append("Есть превышение ёмкостей.")
    return " ".join(parts)


def compare_flow_results(
    max_result: dict[str, Any] | None,
    min_cost_result: dict[str, Any] | None,
    graph: nx.DiGraph,
    source: int,
    sink: int,
) -> str:
    """Сравнение max flow и min cost flow для фактических s и t."""
    if not max_result or not min_cost_result:
        return "Для сравнения выполните оба расчёта на одной и той же сети."

    max_val = float(max_result.get("flow_value", 0))
    mcf_dict = min_cost_result.get("flow_dict", {})

    flow_from_source = float(
        min_cost_result.get(
            "flow_from_source",
            outflow_at_node(mcf_dict, source),
        )
    )
    flow_to_sink = float(
        min_cost_result.get(
            "flow_to_sink",
            inflow_at_node(mcf_dict, graph, sink),
        )
    )
    total_cost = float(min_cost_result.get("total_cost", 0))
    supply = supply_from_demands(graph, source, sink)

    lines = [
        f"- **Maximum flow** (s={source} → t={sink}): **{max_val:.4f}** — "
        "верхняя граница объёма при данных ёмкостях (demand не используется).",
        f"- **Min cost flow**: из s выходит **{flow_from_source:.4f}**, в t входит **{flow_to_sink:.4f}**; "
        f"постановка **F={supply:.4f}**; стоимость **{total_cost:.4f}**.",
    ]

    if abs(flow_from_source - flow_to_sink) < FLOW_TOL:
        lines.append("- Поток min cost **согласован** по s и t (выход из s = вход в t).")
    else:
        lines.append(
            f"- **Несогласованность** min cost: выход s ({flow_from_source:.4f}) "
            f"≠ вход t ({flow_to_sink:.4f})."
        )

    if supply > 0 and abs(flow_to_sink - supply) < FLOW_TOL and abs(flow_from_source - supply) < FLOW_TOL:
        lines.append(f"- Объём **F={supply:.4f}** по demand выполнен.")
    elif supply > 0:
        lines.append(
            f"- Объём по demand (**F={supply:.4f}**) не совпадает с потоком в t ({flow_to_sink:.4f})."
        )

    if max_val > supply + FLOW_TOL:
        lines.append(
            f"- Max flow (**{max_val:.4f}**) > объём min cost (**{supply:.4f}**) — "
            "разные постановки: max flow не ограничен demand."
        )
    elif supply > 0:
        lines.append(
            f"- Max flow (**{max_val:.4f}**) ≤ объём min cost (**{supply:.4f}**) — "
            "ёмкости допускают оба значения."
        )

    lines.append(
        "- **Max flow** максимизирует объём; **min cost** минимизирует Σ c·f при фиксированном балансе узлов."
    )
    return "\n".join(lines)
