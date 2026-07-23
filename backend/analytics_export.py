"""Excel export for supervisor complaint analytics."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill

from backend.schemas import ComplaintAnalyticsDto


HEADERS = (
    "Дата отправки",
    "ID задачи Bitrix",
    "Оператор",
    "Отдел",
    "Тип",
    "Основание",
    "Подтверждение жалобы",
    "Название задачи",
    "Описание",
    "Приоритет",
    "ID звонка",
)


def build_complaints_workbook(
    rows: list[dict[str, Any]],
    analytics: ComplaintAnalyticsDto,
) -> bytes:
    workbook = Workbook()
    complaints = workbook.active
    complaints.title = "Жалобы"
    complaints.freeze_panes = "A2"
    complaints.append(HEADERS)

    for row in rows:
        complaints.append(
            (
                _excel_datetime(row["sent_at"]),
                row["bitrix_item_id"],
                row["operator_name"],
                row["department"],
                row["task_type"],
                row["complaint_basis"],
                row["complaint_evidence"],
                row["title"],
                row["description"],
                row["priority"],
                str(row["call_id"]),
            )
        )

    _style_header(complaints)
    complaints.auto_filter.ref = complaints.dimensions
    for cell in complaints["A"][1:]:
        cell.number_format = "dd.mm.yyyy hh:mm"
    widths = (20, 18, 26, 28, 28, 28, 42, 34, 60, 12, 38)
    for index, width in enumerate(widths, start=1):
        complaints.column_dimensions[complaints.cell(1, index).column_letter].width = (
            width
        )
    for row in complaints.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    summary = workbook.create_sheet("Аналитика")
    summary.append(("Отдел", "Жалобы", "Доля"))
    for item in analytics.departments:
        summary.append(
            (
                item.department,
                item.count,
                item.share_percent / 100,
            )
        )
    _style_header(summary)
    summary.freeze_panes = "A2"
    summary.column_dimensions["A"].width = 34
    summary.column_dimensions["B"].width = 14
    summary.column_dimensions["C"].width = 14
    for cell in summary["C"][1:]:
        cell.number_format = "0.0%"

    if analytics.departments:
        chart = BarChart()
        chart.type = "bar"
        chart.style = 10
        chart.title = "Отправленные жалобы по отделам"
        chart.y_axis.title = "Отдел"
        chart.x_axis.title = "Количество"
        chart.height = max(7, min(16, len(analytics.departments) * 0.65))
        chart.width = 17
        data = Reference(
            summary,
            min_col=2,
            min_row=1,
            max_row=len(analytics.departments) + 1,
        )
        categories = Reference(
            summary,
            min_col=1,
            min_row=2,
            max_row=len(analytics.departments) + 1,
        )
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(categories)
        summary.add_chart(chart, "E2")

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _style_header(sheet: Any) -> None:
    fill = PatternFill("solid", fgColor="7F1F93")
    for cell in sheet[1]:
        cell.fill = fill
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(vertical="center", wrap_text=True)


def _excel_datetime(value: Any) -> Any:
    if getattr(value, "tzinfo", None) is not None:
        return value.replace(tzinfo=None)
    return value


__all__ = ["HEADERS", "build_complaints_workbook"]
