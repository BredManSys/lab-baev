"""KPI deviation analysis and recommendations for SCM KPI Optimizer."""

from __future__ import annotations

from typing import Any, Literal

import pandas as pd

from utils import KPI_KEYS

Status = Literal["accepted", "conditionally_accepted", "rejected"]

KPI_METRIC_MAP: list[tuple[str, str]] = [
    ("cost", "total_cost"),
    ("time", "total_time"),
    ("risk", "total_risk"),
]

ACCEPTANCE_THRESHOLD_PCT = 20.0
CONDITIONAL_THRESHOLD_PCT = 25.0


def calculate_deviation_percentage(current: float, optimal: float) -> float:
    """
    Percent deviation from optimal: (current - optimal) / optimal * 100.

    Returns 0 if optimal is zero and current equals zero; 100 if optimal is 0 and current > 0.
    """
    if optimal == 0:
        return 0.0 if current == 0 else 100.0
    return ((current - optimal) / optimal) * 100.0


def compute_deviations(
    current_metrics: dict[str, float],
    optimal_metrics: dict[str, float],
) -> dict[str, float]:
    """Return deviation % per KPI label (cost, time, risk)."""
    out: dict[str, float] = {}
    for label, key in KPI_METRIC_MAP:
        cur = float(current_metrics.get(key, 0))
        opt = float(optimal_metrics.get(key, 0))
        out[label] = round(calculate_deviation_percentage(cur, opt), 2)
    return out


def total_deviation_sum(deviations: dict[str, float]) -> float:
    """Sum of cost/time/risk deviation percentages (methodology selection criterion)."""
    return round(sum(float(deviations.get(label, 0)) for label, _ in KPI_METRIC_MAP), 2)


def solution_status_from_deviations(deviations: dict[str, float]) -> Status:
    """
    Classify solution using ALL KPI deviations together (course methodology).

    - all <= 20%  -> accepted
    - all <= 25%  -> conditionally_accepted
    - any > 25%   -> rejected
    """
    values = [float(deviations.get(label, 0)) for label, _ in KPI_METRIC_MAP]
    if not values:
        return "rejected"
    if all(v <= ACCEPTANCE_THRESHOLD_PCT for v in values):
        return "accepted"
    if all(v <= CONDITIONAL_THRESHOLD_PCT for v in values):
        return "conditionally_accepted"
    return "rejected"


def _status_for_deviation(deviation_pct: float) -> Status:
    """Per-KPI line status in balance table (same thresholds)."""
    if deviation_pct <= ACCEPTANCE_THRESHOLD_PCT:
        return "accepted"
    if deviation_pct <= CONDITIONAL_THRESHOLD_PCT:
        return "conditionally_accepted"
    return "rejected"


def analyze_kpi_balance(
    current_metrics: dict[str, float],
    optimal_metrics: dict[str, float],
) -> pd.DataFrame:
    """
    Compare current vs per-KPI optimal with deviation % and per-line status.

    Keys expected: total_cost, total_time, total_risk in both dicts.
    """
    rows: list[dict[str, Any]] = []
    for label, key in KPI_METRIC_MAP:
        cur = float(current_metrics.get(key, 0))
        opt = float(optimal_metrics.get(key, 0))
        dev = calculate_deviation_percentage(cur, opt)
        rows.append(
            {
                "kpi": label,
                "current": round(cur, 2),
                "optimal": round(opt, 2),
                "deviation_pct": round(dev, 2),
                "status": _status_for_deviation(dev),
            }
        )
    return pd.DataFrame(rows)


def generate_kpi_summary(
    balance_df: pd.DataFrame,
    *,
    solution_status: Status | None = None,
) -> dict[str, Any]:
    """Aggregate acceptance counts and overall verdict (strict all-KPI rule)."""
    if balance_df.empty:
        return {
            "accepted": 0,
            "conditionally_accepted": 0,
            "rejected": 0,
            "overall": "rejected",
            "explanation": "Данных по KPI пока нет.",
        }

    counts = balance_df["status"].value_counts().to_dict()
    accepted = int(counts.get("accepted", 0))
    conditional = int(counts.get("conditionally_accepted", 0))
    rejected = int(counts.get("rejected", 0))

    deviations = balance_df["deviation_pct"].astype(float).tolist()
    if solution_status is None:
        dev_map = {
            str(row["kpi"]): float(row["deviation_pct"])
            for _, row in balance_df.iterrows()
        }
        overall = solution_status_from_deviations(dev_map)
    else:
        overall = solution_status

    explanation = explain_solution(balance_df, overall)

    return {
        "accepted": accepted,
        "conditionally_accepted": conditional,
        "rejected": rejected,
        "overall": overall,
        "explanation": explanation,
    }


def explain_solution(balance_df: pd.DataFrame, overall: Status) -> str:
    """Human-readable explanation of acceptance decision."""
    if balance_df.empty:
        return "Нет данных для оценки KPI."

    lines: list[str] = []
    for _, row in balance_df.iterrows():
        kpi_ru = {"cost": "затраты", "time": "время", "risk": "риск"}.get(str(row["kpi"]), row["kpi"])
        dev = float(row["deviation_pct"])
        lines.append(
            f"«{kpi_ru}»: текущее {row['current']}, оптимум {row['optimal']}, отклонение {dev:.1f}%."
        )

    detail = " ".join(lines)

    if overall == "accepted":
        return (
            "Решение принято: все KPI не превышают 20% относительно индивидуальных оптимумов. "
            + detail
        )
    if overall == "conditionally_accepted":
        over_20 = balance_df[balance_df["deviation_pct"].astype(float) > ACCEPTANCE_THRESHOLD_PCT]
        names = [
            {"cost": "затраты", "time": "время", "risk": "риск"}.get(str(r["kpi"]), r["kpi"])
            for _, r in over_20.iterrows()
        ]
        warn = f" KPI в зоне 20–25%: {', '.join(names)}." if names else ""
        return (
            "Решение условно принято: все KPI в пределах 25%, но не все укладываются в 20%."
            + warn
            + " "
            + detail
        )

    bad = balance_df[balance_df["deviation_pct"].astype(float) > CONDITIONAL_THRESHOLD_PCT]
    names = [
        {"cost": "затраты", "time": "время", "risk": "риск"}.get(str(r["kpi"]), r["kpi"])
        for _, r in bad.iterrows()
    ]
    bad_txt = ", ".join(names) if names else "не указаны"
    return (
        f"Решение отклонено: как минимум один KPI превышает 25% ({bad_txt}). "
        "Увеличьте допуск по якорю или смените якорный KPI и повторите расчёт. "
        + detail
    )


def _kpi_score(deviation_pct: float) -> float:
    """Higher is better (0–100 scale)."""
    return max(0.0, 100.0 - abs(deviation_pct))


def recommend_anchor_kpi(
    paths_metrics: list[dict[str, float]],
) -> dict[str, Any]:
    """
    Recommend anchor KPI by minimizing average deviation across candidate paths.

    paths_metrics: list of dicts with total_cost, total_time, total_risk.
    """
    if not paths_metrics:
        return {
            "anchor_kpi": "cost",
            "reason": "Маршруты отсутствуют, поэтому по умолчанию выбран KPI «затраты».",
            "scores": {},
        }

    keys = ["total_cost", "total_time", "total_risk"]
    labels = ["cost", "time", "risk"]
    optima = {k: min(m[k] for m in paths_metrics) for k in keys}

    avg_deviations: dict[str, float] = {}
    for label, key in zip(labels, keys):
        devs = [calculate_deviation_percentage(m[key], optima[key]) for m in paths_metrics]
        avg_deviations[label] = sum(devs) / len(devs)

    anchor = min(avg_deviations, key=avg_deviations.get)
    scores = {lbl: round(_kpi_score(avg_deviations[lbl]), 2) for lbl in labels}
    anchor_ru = {"cost": "затраты", "time": "время", "risk": "риск"}.get(anchor, anchor)
    n = len(paths_metrics)
    reason = (
        f"Среди {n} маршрутов из рейтинга наименьшее среднее отклонение по KPI «{anchor_ru}» "
        f"составляет {avg_deviations[anchor]:.1f}% (это не отклонение итогового маршрута шага 3/4). "
        f"Для выбора якоря на шаге 3 ориентируйтесь на предметную постановку задачи."
    )
    return {"anchor_kpi": anchor, "reason": reason, "scores": scores, "avg_deviations": avg_deviations}


def build_recommendations(
    summary: dict[str, Any],
    anchor_info: dict[str, Any],
    balance_df: pd.DataFrame,
    *,
    balanced_result: dict[str, Any] | None = None,
) -> list[str]:
    """Text recommendations for the user."""
    recs = [summary.get("explanation", "")]
    if balanced_result:
        iters = balanced_result.get("iterations")
        if iters and iters > 1:
            recs.append(
                f"Итеративный подбор: выполнено {iters} попыток "
                f"(якорь «{balanced_result.get('anchor_kpi')}», "
                f"итоговый допуск {balanced_result.get('relaxation_percent'):.1f}%)."
            )
        status = balanced_result.get("solution_status")
        if status:
            status_ru = {
                "accepted": "принято",
                "conditionally_accepted": "условно принято",
                "rejected": "отклонено",
            }.get(str(status), str(status))
            recs.append(f"Статус сбалансированного решения: {status_ru}.")
    recs.append(anchor_info.get("reason", ""))
    for _, row in balance_df.iterrows():
        kpi_ru = {"cost": "затраты", "time": "время", "risk": "риск"}.get(row["kpi"], row["kpi"])
        dev = float(row["deviation_pct"])
        if row["status"] == "rejected":
            recs.append(
                f"KPI «{kpi_ru}»: отклонение {dev:.1f}% — превышает порог 25%."
            )
        elif row["status"] == "conditionally_accepted":
            recs.append(
                f"KPI «{kpi_ru}»: отклонение {dev:.1f}% — допустимо условно (20–25%)."
            )
        else:
            recs.append(f"KPI «{kpi_ru}»: отклонение {dev:.1f}% — в пределах 20%.")
    return [r for r in recs if r]
