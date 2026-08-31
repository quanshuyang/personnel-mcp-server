"""数据访问层：支持两种数据源，供 analytics.py / report.py 零改动复用。

1. 文件模式（source_file 给定）：读取本地 Excel/CSV，构造 PersonnelDataset。
2. MySQL 模式（默认，未给 source_file）：从数据库读取（见 db.py）。

两种模式输出的 PersonnelDataset 结构一致，analytics/report 无需感知差异。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import db

# 列名约定（与 SQL 建表脚本保持一致）
EMPLOYEE_ID_COL = "employee_id"
NAME_COL = "name"
DEPARTMENT_COL = "department"
POSITION_COL = "position"
LEVEL_COL = "level"
SALARY_COL = "salary"
HIRE_DATE_COL = "hire_date"
STATUS_COL = "status"
GENDER_COL = "gender"
AGE_COL = "age"

# 真实库可能使用中文列名，这里做兼容映射（中文 -> 约定英文）
COLUMN_ALIASES = {
    "工号": EMPLOYEE_ID_COL,
    "编号": EMPLOYEE_ID_COL,
    "员工编号": EMPLOYEE_ID_COL,
    "工号": EMPLOYEE_ID_COL,
    "姓名": NAME_COL,
    "名字": NAME_COL,
    "员工姓名": NAME_COL,
    "人员姓名": NAME_COL,
    "部门": DEPARTMENT_COL,
    "部门名称": DEPARTMENT_COL,
    "工作部门": DEPARTMENT_COL,
    "所属部门": DEPARTMENT_COL,
    "员工部门": DEPARTMENT_COL,
    "所在部门": DEPARTMENT_COL,
    "岗位": POSITION_COL,
    "职位": POSITION_COL,
    "职级": LEVEL_COL,
    "薪水": SALARY_COL,
    "薪资": SALARY_COL,
    "工资": SALARY_COL,
    "月薪": SALARY_COL,
    "入职日期": HIRE_DATE_COL,
    "入职时间": HIRE_DATE_COL,
    "状态": STATUS_COL,
    "性别": GENDER_COL,
    "年龄": AGE_COL,
}

# 约定字段集合（用于识别「多候选列映射到同一字段」的冲突）
CANONICAL_FIELDS = {
    EMPLOYEE_ID_COL, NAME_COL, DEPARTMENT_COL, POSITION_COL, LEVEL_COL,
    SALARY_COL, HIRE_DATE_COL, STATUS_COL, GENDER_COL, AGE_COL,
}

# 敏感字段黑名单（身份证 / 手机号 / 银行卡等）：任何工具返回中均不得回显。
# 同时匹配中文列名与常见英文列名（原始列名，未做规范化）。
SENSITIVE_FIELDS = {
    "身份证", "身份证号", "证件号", "证件号码", "手机号", "手机号码", "手机",
    "电话", "电话号码", "联系电话", "银行卡", "银行卡号", "银行账号", "银行卡号",
    "id_card", "idcard", "id number", "phone", "mobile", "tel", "telephone",
    "cellphone", "bank_card", "bankcard", "bank_account",
}

# 规范化所需的元信息（保持与旧接口一致）
REQUIRED_FIELDS = [
    EMPLOYEE_ID_COL,
    NAME_COL,
    DEPARTMENT_COL,
    GENDER_COL,
]
UNKNOWN_VALUES = {"未知", "unknown", "不详", "na", "n/a", "null", ""}

# 性别规范映射
_GENDER_ALIASES = {
    "男": "male", "male": "male", "m": "male",
    "女": "female", "female": "female", "f": "female",
    "未知": "unknown", "unknown": "unknown", "": "unknown",
}


def normalize_text(value: Any) -> str:
    """归一化文本：去空白、转小写、None/空串返回空串。"""
    if value is None:
        return ""
    return str(value).strip().lower()


def normalize_key(value: Any) -> str:
    """用于比较的键归一化。"""
    return normalize_text(value)


def _to_float(value: Any, default: float = 0.0) -> float:
    """把任意值安全转为 float。"""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        s = str(value).strip().replace(",", "").replace("%", "").replace("元", "")
        return float(s) if s else default
    except (ValueError, TypeError):
        return default


def _safe_get(row: Dict[str, Any], key: str, default: Any = "") -> Any:
    v = row.get(key)
    return v if v is not None else default


def _gender_normalized(value: Any) -> str:
    key = normalize_text(value)
    return _GENDER_ALIASES.get(key, "unknown")


def _row_to_record(row: Dict[str, Any]) -> Dict[str, Any]:
    """把一行 DB 记录规整为 analytics 需要的字段（含派生字段）。

    支持真实库使用中文列名：通过 COLUMN_ALIASES 把中文键映射回约定英文字段。
    """
    # 先按别名统一为约定英文字段；敏感字段（身份证/手机号/银行卡等）直接剔除
    normalized: Dict[str, Any] = {}
    for raw_key, value in row.items():
        if raw_key in SENSITIVE_FIELDS:
            continue
        key = COLUMN_ALIASES.get(raw_key, raw_key)
        if value is None:
            normalized[key] = ""
        elif isinstance(value, str):
            normalized[key] = value.strip()
        else:
            normalized[key] = value
    record = {k: v for k, v in normalized.items()}
    record["gender_normalized"] = _gender_normalized(normalized.get(GENDER_COL))
    # source_row 用于 validate 报告里的"行号"，DB 场景下用主键或其序号
    record["source_row"] = normalized.get(EMPLOYEE_ID_COL) or 0
    return record


class PersonnelDataset:
    """兼容旧 Excel 版的数据集结构。

    source_file / sheet_name 记录数据来源，analytics.report 的 `_source` 会用到。
    """

    def __init__(
        self,
        records: List[Dict[str, Any]],
        warnings: Optional[List[str]] = None,
        source_file: str = "",
        sheet_name: Optional[str] = None,
        raw_columns: Optional[List[str]] = None,
    ):
        self.records = records
        self.warnings: List[str] = list(warnings or [])
        self.source_file = source_file
        self.sheet_name = sheet_name
        # 原始列名（用于多候选列冲突检测）
        self.raw_columns: List[str] = list(raw_columns or [])
        # 多候选列冲突：约定字段 -> [候选真实列名]（长度 > 1 表示需要用户确认映射）
        self.column_conflicts: Dict[str, List[str]] = _detect_column_conflicts(self.raw_columns)
        # 约定字段集合（analytics 依赖这些键）
        canonical = [
            EMPLOYEE_ID_COL, NAME_COL, DEPARTMENT_COL, POSITION_COL, LEVEL_COL,
            SALARY_COL, HIRE_DATE_COL, STATUS_COL, GENDER_COL, AGE_COL,
        ]
        # mapped_columns：约定英文字段 -> 真实原始列名（来自实际读取到的列）
        self.mapped_columns = {}
        for raw in raw_columns or []:
            canonical_field = COLUMN_ALIASES.get(raw, raw)
            if canonical_field in CANONICAL_FIELDS and canonical_field not in self.mapped_columns:
                self.mapped_columns[canonical_field] = raw
        # headers 反映真实读取到的原始列名（用于重复列名检测等数据质量校验）
        self.headers = list(raw_columns or [])


def _detect_column_conflicts(raw_columns: List[str]) -> Dict[str, List[str]]:
    """检测「多个真实列映射到同一约定字段」的冲突。

    例如数据同时含「部门」和「所属部门」两列，二者都通过 COLUMN_ALIASES
    映射到 department，此时应停止并请用户确认使用哪一列，而非默默取其一。
    返回：约定字段名 -> 候选真实列名列表（仅包含候选数 > 1 的约定字段）。
    """
    mapping: Dict[str, List[str]] = {}
    for raw in raw_columns:
        canonical = COLUMN_ALIASES.get(raw, raw)
        mapping.setdefault(canonical, []).append(raw)
    conflicts: Dict[str, List[str]] = {}
    for canonical, cols in mapping.items():
        if canonical in CANONICAL_FIELDS and len(cols) > 1:
            conflicts[canonical] = cols
    return conflicts


class PersonnelDataError(Exception):
    """数据加载/校验错误。"""


def get_data_dir() -> Any:
    """返回报告导出目录（MySQL 模式下仍支持把统计报告写为本地 Excel）。"""
    env = os.getenv("PERSONNEL_DATA_DIR")
    if env:
        path = Path(env)
    else:
        path = Path(__file__).resolve().parents[2] / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_file_records(
    source_file: str, sheet_name: Optional[str], data_dir: Optional[str] = None
) -> List[Dict[str, Any]]:
    """读取本地 Excel/CSV 文件，返回规整字典列表。

    source_file 会被解析为 data 目录内的相对路径（安全约束，见 server.py）。
    文件列名支持中文别名（姓名/部门/性别等），通过 COLUMN_ALIASES 映射。
    data_dir 可选，指定文件查找基准目录（默认用 get_data_dir()）。
    """
    try:
        import pandas as pd
    except ImportError as error:  # pragma: no cover
        raise PersonnelDataError(
            "文件模式需要 pandas/openpyxl：请执行 `uv pip install pandas openpyxl`。"
        ) from error

    base = Path(data_dir) if data_dir else get_data_dir()
    base_resolved = base.resolve()
    path = (base_resolved / source_file).resolve()
    # 目录穿越防护：解析后的路径必须仍在数据目录内
    if base_resolved != path and base_resolved not in path.parents:
        raise PersonnelDataError(f"路径不合法：{source_file} 位于数据目录之外（禁止目录穿越）。")
    if not path.is_file():
        raise PersonnelDataError(f"未找到文件：{source_file}（应在 data 目录内）。")

    lower = path.suffix.lower()
    if lower in (".xlsx", ".xls"):
        frame = pd.read_excel(path, sheet_name=sheet_name or 0, dtype=str)
    elif lower in (".csv", ".tsv", ".tab"):
        sep = "\t" if lower in (".tsv", ".tab") else ","
        # 中文环境常见编码（utf-8-sig / gb18030 / gbk）依次回退
        frame = None
        last_error: Exception | None = None
        for enc in ("utf-8-sig", "gb18030", "gbk"):
            try:
                frame = pd.read_csv(path, sep=sep, dtype=str, encoding=enc)
                break
            except (UnicodeDecodeError, LookupError) as error:
                last_error = error
        if frame is None:
            raise PersonnelDataError(
                f"文件编码无法识别（已尝试 utf-8/gb18030/gbk）：{source_file}。"
            ) from last_error
    else:
        raise PersonnelDataError(f"不支持的文件类型：{path.suffix}（仅支持 .xlsx/.xls/.csv/.tsv）。")

    records: List[Dict[str, Any]] = []
    for idx, row in enumerate(frame.to_dict(orient="records"), start=2):
        record = _row_to_record(row)
        record["source_row"] = idx  # CSV/Excel 行号（表头为第 1 行）
        records.append(record)
    raw_columns: List[str] = [str(c) for c in frame.columns]
    return records, raw_columns


def load_personnel_data(
    source_file: Optional[str] = None,
    sheet_name: Optional[str] = None,
    data_dir: Optional[str] = None,
) -> PersonnelDataset:
    """加载人员数据，构造 PersonnelDataset。

    双数据源：
    - source_file 给定 → 文件模式（读取本地 Excel/CSV）。
    - 否则 → MySQL 模式（默认，从 PERSONNEL_TABLE 读取）。

    data_dir 仅文件模式有效，指定文件查找基准目录（默认用 get_data_dir()）。
    """
    warnings: List[str] = []
    if source_file:
        records, raw_columns = _read_file_records(source_file, sheet_name, data_dir)
        if not records:
            warnings.append("文件解析后无数据行，请确认文件内容。")
        # 缺失必需列告警
        present_fields = set()
        for raw in raw_columns or []:
            present_fields.add(COLUMN_ALIASES.get(raw, raw))
        missing = [f for f in REQUIRED_FIELDS if f not in present_fields]
        if missing:
            labels = "、".join(missing)
            warnings.append(f"缺失必需列：{labels}（将影响统计/筛选准确性，请核对文件表头）。")
        return PersonnelDataset(
            records, warnings, source_file=source_file, sheet_name=sheet_name,
            raw_columns=raw_columns,
        )

    # MySQL 模式（默认）
    if not db.table_exists():
        raise PersonnelDataError(
            f"人员表 `{db.PERSONNEL_TABLE}` 在数据库 `{db._db_config()['database']}` 中不存在，"
            "请先执行 sql/init_schema.sql 建表并写入数据，或改用 source_file 传入本地文件。"
        )
    raw_columns = db.list_columns()
    raw = db.get_all_records()
    if not raw:
        warnings.append("人员表为空，请确认数据已写入。")
    records = [_row_to_record(r) for r in raw]
    return PersonnelDataset(
        records, warnings, source_file=f"mysql:{db.PERSONNEL_TABLE}", sheet_name=None,
        raw_columns=raw_columns,
    )


def load_records(
    filters: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """从 MySQL 加载记录（带过滤），返回规整字典列表。"""
    raw = db.get_all_records(filters)
    return [_row_to_record(r) for r in raw]


__all__ = [
    "PersonnelDataset",
    "PersonnelDataError",
    "load_personnel_data",
    "load_records",
    "get_data_dir",
    "normalize_text",
    "normalize_key",
    "REQUIRED_FIELDS",
    "UNKNOWN_VALUES",
    "_to_float",
    "_safe_get",
    EMPLOYEE_ID_COL,
    NAME_COL,
    DEPARTMENT_COL,
    POSITION_COL,
    LEVEL_COL,
    SALARY_COL,
    HIRE_DATE_COL,
    STATUS_COL,
    GENDER_COL,
    AGE_COL,
]
