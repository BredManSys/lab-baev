"""PDF and tabular export for SCM KPI Optimizer."""

from __future__ import annotations

import json
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from graph_visualizer import figure_to_bytes, visualize_graph_matplotlib
from utils import KPI_RU, OVERALL_RU, graph_summary_ru


def _styles():
    base = getSampleStyleSheet()
    title = ParagraphStyle(
        "CustomTitle",
        parent=base["Title"],
        fontSize=22,
        spaceAfter=20,
        textColor=colors.HexColor("#2c3e50"),
    )
    heading = ParagraphStyle(
        "CustomHeading",
        parent=base["Heading2"],
        fontSize=14,
        spaceBefore=16,
        spaceAfter=8,
        textColor=colors.HexColor("#34495e"),
    )
    body = ParagraphStyle("CustomBody", parent=base["Normal"], fontSize=10, leading=14)
    return title, heading, body


def _df_table(df: pd.DataFrame, col_widths: list[float] | None = None) -> Table:
    if df.empty:
        data = [["Нет данных"]]
        t = Table(data)
    else:
        data = [df.columns.tolist()] + df.astype(str).values.tolist()
        t = Table(data, colWidths=col_widths)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3498db")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#ecf0f1")]),
            ]
        )
    )
    return t


def generate_pdf_report(
    output_path: str | Path,
    *,
    graph_summary: dict[str, Any],
    edge_df: pd.DataFrame,
    optimal_paths_df: pd.DataFrame,
    kpi_balance_df: pd.DataFrame,
    kpi_summary: dict[str, Any],
    recommendations: list[str],
    graph: Any,
    highlight_path: list[int] | None = None,
    anchor_kpi: str = "cost",
    relaxation_percent: float = 12.0,
    balanced_result: dict[str, Any] | None = None,
) -> Path:
    """Generate multi-section PDF report."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm)
    title_style, heading_style, body_style = _styles()
    story: list[Any] = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Title page
    anchor_ru = KPI_RU.get(anchor_kpi, anchor_kpi)
    story.append(Paragraph("SCM KPI Optimizer", title_style))
    story.append(Paragraph("Отчёт по транспортной SCM-сети", body_style))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"Собран: {now}", body_style))
    story.append(Paragraph(f"Якорный KPI: {anchor_ru} | Допуск: {relaxation_percent}%", body_style))
    story.append(Spacer(1, 24))

    # Graph summary
    story.append(Paragraph("1. Сводка по графу", heading_style))
    ru_summary = graph_summary_ru(graph_summary)
    summary_lines = [f"<b>{k}:</b> {v}" for k, v in ru_summary.items()]
    story.append(Paragraph("<br/>".join(summary_lines), body_style))
    story.append(Spacer(1, 12))

    # Visualization
    story.append(Paragraph("2. Визуализация сети", heading_style))
    if graph is not None:
        fig = visualize_graph_matplotlib(graph, highlight_path=highlight_path)
        img_bytes = figure_to_bytes(fig)
        img = Image(BytesIO(img_bytes), width=16 * cm, height=10 * cm)
        story.append(img)
    story.append(Spacer(1, 12))

    # Edge table
    story.append(Paragraph("3. Таблица рёбер", heading_style))
    story.append(_df_table(edge_df))
    story.append(Spacer(1, 12))

    # Optimal paths
    story.append(Paragraph("4. Оптимальные маршруты по KPI", heading_style))
    story.append(_df_table(optimal_paths_df))
    story.append(Spacer(1, 12))

    # KPI analysis
    story.append(Paragraph("5. Анализ KPI", heading_style))
    story.append(_df_table(kpi_balance_df))
    story.append(Spacer(1, 8))
    overall = kpi_summary.get("overall", "N/A")
    overall_ru = OVERALL_RU.get(str(overall), str(overall))
    story.append(
        Paragraph(
            f"Итог: <b>{overall_ru}</b> — {kpi_summary.get('explanation', '')}",
            body_style,
        )
    )
    story.append(Spacer(1, 12))

    # Deviations & balanced path
    story.append(Paragraph("6. Отклонения и сбалансированный путь", heading_style))
    if balanced_result:
        bm = balanced_result.get("balanced_metrics", {})
        story.append(
            Paragraph(
                f"Маршрут: {' → '.join(map(str, balanced_result.get('balanced_path', [])))}<br/>"
                f"Затраты: {bm.get('total_cost', '—')} | Время: {bm.get('total_time', '—')} | "
                f"Риск: {bm.get('total_risk', '—')} | Сумм. откл.: {bm.get('total_deviation', '—')}%",
                body_style,
            )
        )
    story.append(Spacer(1, 12))

    # Recommendations
    story.append(Paragraph("7. Рекомендации", heading_style))
    for rec in recommendations:
        story.append(Paragraph(f"• {rec}", body_style))
        story.append(Spacer(1, 4))

    doc.build(story)
    return path


def export_csv(df: pd.DataFrame, filepath: str | Path) -> Path:
    """Export DataFrame to CSV."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path


def export_json_results(data: dict[str, Any], filepath: str | Path) -> Path:
    """Export results dict to JSON file."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    return path


def build_results_payload(
    *,
    graph_summary: dict[str, Any],
    optimal_paths_df: pd.DataFrame,
    ranked_paths_df: pd.DataFrame,
    kpi_balance_df: pd.DataFrame,
    kpi_summary: dict[str, Any],
    balanced_result: dict[str, Any],
    anchor_kpi: str,
    relaxation_percent: float,
) -> dict[str, Any]:
    """Bundle all results for JSON export."""
    return {
        "generated_at": datetime.now().isoformat(),
        "anchor_kpi": anchor_kpi,
        "relaxation_percent": relaxation_percent,
        "graph_summary": graph_summary,
        "optimal_paths": optimal_paths_df.to_dict(orient="records"),
        "ranked_paths": ranked_paths_df.to_dict(orient="records"),
        "kpi_balance": kpi_balance_df.to_dict(orient="records"),
        "kpi_summary": kpi_summary,
        "balanced_result": balanced_result,
    }
