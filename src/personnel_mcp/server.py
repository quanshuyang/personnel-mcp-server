"""MCP tool definitions for personnel analytics."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .analytics import (
    department_statistics,
    filter_employees as filter_employee_records,
    generate_chart_data,
    headcount_summary,
    list_departments as list_department_counts,
    validate_personnel_data as validate_data,
)
from .data import PersonnelDataError, get_data_dir, load_personnel_data
from .report import export_report


mcp = FastMCP("Personnel Analytics")


def _load(source_file: str | None = None, sheet_name: str | None = None) -> Any:
    """加载人员数据集。

    默认从 MySQL 读取（PERSONNEL_TABLE）；传入 source_file 时改为读取本地文件。
    """
    try:
        return load_personnel_data(source_file, sheet_name)
    except PersonnelDataError as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def get_headcount_summary(
    source_file: str | None = None,
    sheet_name: str | None = None,
) -> dict[str, Any]:
    """返回总人数、男女数量及比例，以及有效部门数量。

    数据源：source_file 给定时读取本地 Excel/CSV；否则从 MySQL 人员表读取（默认）。
    """
    return headcount_summary(_load(source_file, sheet_name))


@mcp.tool()
def get_department_statistics(
    departments: list[str] | None = None,
    source_file: str | None = None,
    sheet_name: str | None = None,
) -> dict[str, Any]:
    """按部门统计人数、男女数量及比例。departments 为空时统计全部部门。

    数据源：source_file 给定时读取本地文件；否则从 MySQL 人员表读取（默认）。
    """
    return department_statistics(_load(source_file, sheet_name), departments)


@mcp.tool()
def filter_employees(
    department: str | None = None,
    gender: str | None = None,
    name_contains: str | None = None,
    limit: int = 50,
    offset: int = 0,
    source_file: str | None = None,
    sheet_name: str | None = None,
) -> dict[str, Any]:
    """按部门、性别和姓名关键词筛选人员；返回字段已最小化，最多每页 200 条。

    数据源：source_file 给定时读取本地文件；否则从 MySQL 人员表读取（默认）。
    """
    return filter_employee_records(
        _load(source_file, sheet_name), department, gender, name_contains, limit, offset
    )


@mcp.tool()
def list_departments(
    source_file: str | None = None,
    sheet_name: str | None = None,
) -> dict[str, Any]:
    """列出人员表中的有效部门及各部门人数，按人数降序。

    数据源：source_file 给定时读取本地文件；否则从 MySQL 人员表读取（默认）。
    """
    return list_department_counts(_load(source_file, sheet_name))


@mcp.tool()
def validate_personnel_data(
    known_departments: list[str] | None = None,
    source_file: str | None = None,
    sheet_name: str | None = None,
) -> dict[str, Any]:
    """检查空值、未识别性别、未知部门、重复人员等数据质量问题。

    数据源：source_file 给定时读取本地文件；否则从 MySQL 人员表读取（默认）。
    """
    return validate_data(_load(source_file, sheet_name), known_departments)


@mcp.tool()
def export_statistics_report(
    output_file: str,
    known_departments: list[str] | None = None,
    source_file: str | None = None,
    sheet_name: str | None = None,
) -> dict[str, Any]:
    """导出多工作表 Excel 报告（汇总、部门统计、性别统计、数据问题、规范化数据）。

    output_file 必须是数据目录内的相对路径；数据目录由 PERSONNEL_DATA_DIR 指定，
    未指定时使用服务所在目录的 data/。
    数据源：source_file 给定时读取本地文件；否则从 MySQL 人员表读取（默认）。
    """
    dataset = _load(source_file, sheet_name)
    return export_report(dataset, output_file, known_departments, get_data_dir())


@mcp.tool()
def generate_chart(
    dimension: str = "department",
    chart_type: str = "bar",
    department: str | None = None,
    source_file: str | None = None,
    sheet_name: str | None = None,
) -> dict[str, Any]:
    """生成人员数据的可视化图表数据（供前端渲染）。

    - dimension: "department"（部门维度）或 "gender"（性别维度）。
    - chart_type: "bar"（柱状图）或 "pie"（饼图）。
    - department: 仅当 dimension="department" 且想只画某一个部门时可指定（画该部门内性别分布）。
      用户未明确维度/类型时，由后端根据对话意图自动传入，无需手动猜测。
    返回 {"chart": {"type", "title", "data": [{"label","value"}]}}，前端据此绘制。
    数据源：source_file 给定时读取本地文件；否则从 MySQL 人员表读取（默认）。
    """
    if dimension not in ("department", "gender"):
        raise ValueError("dimension 仅支持 department 或 gender。")
    if chart_type not in ("bar", "pie"):
        raise ValueError("chart_type 仅支持 bar 或 pie。")
    dataset = _load(source_file, sheet_name)
    return generate_chart_data(dataset, dimension, chart_type, department)


def main() -> None:
    """Run the server over stdio for MCP-compatible clients."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

