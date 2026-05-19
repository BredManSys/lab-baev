"""KPI deviation analysis and recommendations for SCM KPI Optimizer."""

from __future__ import annotations

from typing import Any, Literal

import pandas as pd

from utils import KPI_KEYS

Status = Literal["accepted", "conditionally_accepted", "rejected"]


def calculate_deviation_percentage(current: float, optimal: float) -> float:
    """
    Percent deviation from optimal: (current - optimal) / optimal * 100.

    Returns 0 if optimal is zero and current equals zero; inf-like large value if optimal is 0 and current > 0.
    """
    if optimal == 0:
        return 0.0 if current == 0 else 100.0
    return ((current - optimal) / optimal) * 100.0


def _status_for_deviation(deviation_pct: float) -> Status:
    if deviation_pct <= 20:
        return "accepted"
    if deviation_pct <= 25:
        return "conditionally_accepted"
    return "rejected"


def analyze_kpi_balance(
    current_metrics: dict[str, float],
    optimal_metrics: dict[str, float],
) -> pd.DataFrame:
    """
    Compare current vs optimal per KPI with deviation % and acceptance status.

    Keys expected: total_cost, total_time, total_risk in both dicts.
    """
    mapping = [("cost", "total_cost"), ("time", "total_time"), ("risk", "total_risk")]
    rows: list[dict[str, Any]] = []
    for label, key in mapping:
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


def generate_kpi_summary(balance_df: pd.DataFrame) -> dict[str, Any]:
    """Aggregate acceptance counts and overall verdict."""
    if balance_df.empty:
        return {
            "accepted": 0,
            "conditionally_accepted": 0,
            "rejected": 0,
            "overall": "rejected",
            "explanation": "No KPI data available.",
        }

    counts = balance_df["status"].value_counts().to_dict()
    accepted = int(counts.get("accepted", 0))
    conditional = int(counts.get("conditionally_accepted", 0))
    rejected = int(counts.get("rejected", 0))

    if rejected > 0:
        overall: Status = "rejected"
        explanation = "One or more KPIs exceed 25% deviation from optimal."
    elif conditional > 0:
        overall = "conditionally_accepted"
        explanation = "All KPIs within 25%, but some between 20% and 25%."
    else:
        overall = "accepted"
        explanation = "All KPI deviations are within 20% of optimal."

    return {
        "accepted": accepted,
        "conditionally_accepted": conditional,
        "rejected": rejected,
        "overall": overall,
        "explanation": explanation,
    }


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
        return {"anchor_kpi": "cost", "reason": "Default: no path data.", "scores": {}}

    keys = ["total_cost", "total_time", "total_risk"]
    labels = ["cost", "time", "risk"]
    optima = {k: min(m[k] for m in paths_metrics) for k in keys}

    avg_deviations: dict[str, float] = {}
    for label, key in zip(labels, keys):
        devs = [calculate_deviation_percentage(m[key], optima[key]) for m in paths_metrics]
        avg_deviations[label] = sum(devs) / len(devs)

    anchor = min(avg_deviations, key=avg_deviations.get)
    scores = {lbl: round(_kpi_score(avg_deviations[lbl]), 2) for lbl in labels}
    reason = (
        f"Anchor '{anchor}' has the lowest average deviation ({avg_deviations[anchor]:.1f}%) "
        f"across evaluated paths."
    )
    return {"anchor_kpi": anchor, "reason": reason, "scores": scores, "avg_deviations": avg_deviations}


def build_recommendations(
    summary: dict[str, Any],
    anchor_info: dict[str, Any],
    balance_df: pd.DataFrame,
) -> list[str]:
    """Text recommendations for the user."""
    recs = [summary.get("explanation", "")]
    recs.append(anchor_info.get("reason", ""))
    for _, row in balance_df.iterrows():
        if row["status"] == "rejected":
            recs.append(f"Reduce {row['kpi']}: deviation {row['deviation_pct']}% exceeds 25%.")
        elif row["status"] == "conditionally_accepted":
            recs.append(f"Monitor {row['kpi']}: deviation {row['deviation_pct']}% is in warning zone.")
    return [r for r in recs if r]
