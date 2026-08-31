"""Domain operations used by MCP tool handlers and tests."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .data import REQUIRED_FIELDS, UNKNOWN_VALUES, PersonnelDataset, normalize_key, normalize_text


def _gender_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    counts = Counter(record.get("gender_normalized", "unknown") for record in records)
    male = counts["male"]
    female = counts["female"]
    unknown = total - male - female
    male_pct = f"{male / total * 100:.1f}%" if total else "0.0%"
    female_pct = f"{female / total * 100:.1f}%" if total else "0.0%"
    unknown_pct = f"{unknown / total * 100:.1f}%" if total else "0.0%"
    return {
        "male": male,
        "female": female,
        "unknown": unknown,
        "male_ratio": round(male / total, 4) if total else 0.0,
        "female_ratio": round(female / total, 4) if total else 0.0,
        "male_pct": male_pct,
        "female_pct": female_pct,
        "unknown_pct": unknown_pct,
    }


def headcount_summary(dataset: PersonnelDataset) -> dict[str, Any]:
    departments = {normalize_text(record.get("department")) for record in dataset.records if normalize_text(record.get("department"))}
    return {
        "source": _source(dataset),
        "total_headcount": len(dataset.records),
        "department_count": len(departments),
        "gender": _gender_metrics(dataset.records),
        "warnings": dataset.warnings,
    }


def department_statistics(dataset: PersonnelDataset, departments: list[str] | None = None) -> dict[str, Any]:
    requested = {normalize_key(value) for value in departments or [] if normalize_text(value)}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unassigned: list[dict[str, Any]] = []
    for record in dataset.records:
        department = normalize_text(record.get("department"))
        if not department:
            unassigned.append(record)
        elif not requested or normalize_key(department) in requested:
            grouped[department].append(record)

    result = [
        {"department": name, "headcount": len(records), "gender": _gender_metrics(records)}
        for name, records in grouped.items()
    ]
    result.sort(key=lambda item: (-item["headcount"], item["department"]))
    return {
        "source": _source(dataset),
        "departments": result,
        "unassigned_headcount": len(unassigned),
        "warnings": dataset.warnings,
    }


def list_departments(dataset: PersonnelDataset) -> dict[str, Any]:
    statistics = department_statistics(dataset)
    return {
        "source": statistics["source"],
        "departments": [
            {"department": item["department"], "headcount": item["headcount"]}
            for item in statistics["departments"]
        ],
        "unassigned_headcount": statistics["unassigned_headcount"],
        "warnings": dataset.warnings,
    }


def filter_employees(
    dataset: PersonnelDataset,
    department: str | None = None,
    gender: str | None = None,
    name_contains: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    if limit < 1 or limit > 200:
        raise ValueError("limit 必须介于 1 和 200 之间。")
    if offset < 0:
        raise ValueError("offset 不能小于 0。")

    department_key = normalize_key(department) if department else None
    gender_key = normalize_key(gender) if gender else None
    gender_aliases = {"男": "male", "male": "male", "m": "male", "女": "female", "female": "female", "f": "female", "未知": "unknown", "unknown": "unknown"}
    if gender_key and gender_key not in gender_aliases:
        raise ValueError("gender 仅支持 男、女、未知 或 male、female、unknown。")
    normalized_gender = gender_aliases.get(gender_key) if gender_key else None
    name_key = normalize_key(name_contains) if name_contains else None

    matched = [
        record
        for record in dataset.records
        if (not department_key or normalize_key(record.get("department")) == department_key)
        and (not normalized_gender or record.get("gender_normalized") == normalized_gender)
        and (not name_key or name_key in normalize_key(record.get("name")))
    ]
    employees = [
        {
            "employee_id": record.get("employee_id", ""),
            "name": record.get("name", ""),
            "department": record.get("department", ""),
            "gender": record.get("gender", ""),
            "gender_normalized": record.get("gender_normalized", "unknown"),
            "source_row": record["source_row"],
        }
        for record in matched[offset : offset + limit]
    ]
    return {
        "source": _source(dataset),
        "total_matched": len(matched),
        "offset": offset,
        "limit": limit,
        "employees": employees,
        "warnings": dataset.warnings,
    }


def validate_personnel_data(dataset: PersonnelDataset, known_departments: list[str] | None = None) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    required_fields = REQUIRED_FIELDS
    for field in required_fields:
        if field not in dataset.mapped_columns:
            issues.append(_issue("error", "missing_column", field, [], f"未识别必需列: {field}。"))

    known = {normalize_key(value) for value in known_departments or [] if normalize_text(value)}
    duplicate_groups: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for record in dataset.records:
        row = record["source_row"]
        for field in required_fields:
            if field in dataset.mapped_columns and not normalize_text(record.get(field)):
                issues.append(_issue("warning", "missing_value", field, [row], f"第 {row} 行的 {field} 为空。"))

        gender_key = normalize_key(record.get("gender"))
        if gender_key and record.get("gender_normalized") == "unknown" and gender_key not in UNKNOWN_VALUES:
            issues.append(_issue("warning", "invalid_gender", "gender", [row], f"第 {row} 行的性别值无法识别: {record.get('gender')}。"))
        if known and normalize_text(record.get("department")) and normalize_key(record.get("department")) not in known:
            issues.append(_issue("warning", "unknown_department", "department", [row], f"第 {row} 行的部门不在已知部门列表中。"))

        employee_id = normalize_key(record.get("employee_id"))
        if employee_id:
            duplicate_key = ("employee_id", employee_id)
        else:
            name = normalize_key(record.get("name"))
            department = normalize_key(record.get("department"))
            if not name or not department:
                continue
            duplicate_key = ("name_department", name, department)
        duplicate_groups[duplicate_key].append(row)

    for key, rows in duplicate_groups.items():
        if len(rows) > 1:
            field = "employee_id" if key[0] == "employee_id" else "name,department"
            issues.append(_issue("warning", "duplicate_employee", field, rows, f"疑似重复人员记录，涉及行: {', '.join(map(str, rows))}。"))

    duplicate_headers = [header for header, count in Counter(dataset.headers).items() if header and count > 1]
    for header in duplicate_headers:
        issues.append(_issue("warning", "duplicate_header", header, [], f"表头重复: {header}。"))

    severity_counts = Counter(issue["severity"] for issue in issues)
    return {
        "source": _source(dataset),
        "is_valid": severity_counts["error"] == 0,
        "summary": {"errors": severity_counts["error"], "warnings": severity_counts["warning"], "total_issues": len(issues)},
        "issues": issues,
        "warnings": dataset.warnings,
    }


def _source(dataset: PersonnelDataset) -> dict[str, Any]:
    conflicts = dataset.column_conflicts
    note = ""
    if conflicts:
        parts = [
            f"{field}（候选列：{', '.join(cols)}）"
            for field, cols in conflicts.items()
        ]
        note = (
            "检测到多候选列映射到同一约定字段，请先与用户确认各字段应使用哪一列，"
            "再给出统计结论，不要自行假设：" + "；".join(parts)
        )
    return {
        "source_file": dataset.source_file,
        "sheet_name": dataset.sheet_name,
        "row_count": len(dataset.records),
        "mapped_columns": dataset.mapped_columns,
        "column_conflicts": conflicts,
        "column_mapping_note": note,
    }


def _issue(severity: str, code: str, field: str, rows: list[int], message: str) -> dict[str, Any]:
    return {"severity": severity, "code": code, "field": field, "rows": rows, "message": message}


# ---------------------------------------------------------------------------
# 图表生成（Skill -> 前端 chart 事件）
# ---------------------------------------------------------------------------

# 关键词 -> 图表类型
_PIE_KEYWORDS = ["饼图", "饼状图", "扇形", "环形", "占比", "比例", "构成"]
_BAR_KEYWORDS = ["柱状图", "条形图", "柱图", "对比", "排名", "排行"]
# 维度识别
_GENDER_KEYWORDS = ["性别", "男女", "男女性别", "男/女", "男女比例"]
_DEPT_KEYWORDS = ["部门", "科室", "组别", "团队", "分部"]


def _analyze_chart_intent(text: str) -> tuple[bool, str | None, str | None]:
    """根据自然语言判断是否需要出图，以及维度/类型。

    返回 (wants_chart, dimension, chart_type)：
    - wants_chart: 是否触发图表
    - dimension: "department" | "gender" | None
    - chart_type: "bar" | "pie" | None
    优先级：显式类型词 > 维度词隐含类型。未显式指定类型时按规则兜底
    （部门->bar，性别->pie）。
    """
    if not text:
        return False, None, None

    wants_chart = any(
        k in text
        for k in ["图", "可视化", "分布", "占比", "比例", "对比", "构成", "图表"]
    )
    if not wants_chart:
        return False, None, None

    # 类型判断
    chart_type: str | None = None
    if any(k in text for k in _PIE_KEYWORDS):
        chart_type = "pie"
    elif any(k in text for k in _BAR_KEYWORDS):
        chart_type = "bar"

    # 维度判断
    dimension: str | None = None
    if any(k in text for k in _GENDER_KEYWORDS):
        dimension = "gender"
    elif any(k in text for k in _DEPT_KEYWORDS):
        dimension = "department"

    # 兜底：未显式指定类型时按维度给默认类型
    if dimension and not chart_type:
        chart_type = "pie" if dimension == "gender" else "bar"
    return True, dimension, chart_type


def generate_chart_data(
    dataset: PersonnelDataset,
    dimension: str,
    chart_type: str,
    department: str | None = None,
) -> dict[str, Any]:
    """根据维度与类型生成前端 chart 契约所需的 JSON。

    返回 {"chart": {"type", "title", "data": [{"label","value"}]}}。
    - dimension="department": 各部门人数（可指定单部门时只绘该部门）
    - dimension="gender": 男/女/未填写 分布
    """
    if dimension == "gender":
        metrics = _gender_metrics(dataset.records)
        data = [
            {"label": "男", "value": metrics["male"]},
            {"label": "女", "value": metrics["female"]},
        ]
        if metrics["unknown"]:
            data.append({"label": "未填写", "value": metrics["unknown"]})
        title = "性别分布"
        return {"chart": {"type": chart_type, "title": title, "data": data}}

    # department 维度
    stats = department_statistics(dataset, [department] if department else None)
    if department:
        # 单部门：绘该部门内性别分布（更易读），标题带上部门名
        grouped = next(
            (d for d in stats["departments"] if d["department"] == department), None
        )
        if grouped:
            g = grouped["gender"]
            data = [
                {"label": "男", "value": g["male"]},
                {"label": "女", "value": g["female"]},
            ]
            if g["unknown"]:
                data.append({"label": "未填写", "value": g["unknown"]})
            title = f"{department} 性别分布"
            return {"chart": {"type": chart_type, "title": title, "data": data}}
        # 指定部门不存在则退化为全部部门
    data = [
        {"label": d["department"], "value": d["headcount"]}
        for d in stats["departments"]
    ]
    if stats.get("unassigned_headcount"):
        data.append({"label": "未填写", "value": stats["unassigned_headcount"]})
    title = "各部门人数"
    return {"chart": {"type": chart_type, "title": title, "data": data}}
