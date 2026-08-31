"""MySQL 连接与查询层（替代原 Excel 数据加载）。

连接参数优先读取环境变量（由 Backend 转发注入），并提供默认值便于本地调试。
所有查询均使用参数化占位符，避免 SQL 注入。
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pymysql
from pymysql.cursors import DictCursor

# 人员主表名，可通过环境变量覆盖（便于接不同库/表）
PERSONNEL_TABLE = os.getenv("PERSONNEL_TABLE", "employees")


def _db_config() -> Dict[str, Any]:
    """从环境变量构造 PyMySQL 连接参数。"""
    return {
        "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "personnel"),
        "charset": os.getenv("MYSQL_CHARSET", "utf8mb4"),
        "autocommit": True,
        # 长连接场景下自动重连，避免 gone away
        "client_flag": pymysql.constants.CLIENT.REMEMBER_OPTIONS
        if hasattr(pymysql.constants.CLIENT, "REMEMBER_OPTIONS")
        else 0,
    }


@contextmanager
def _connection():
    """上下文管理器：返回连接，异常时回滚/关闭。"""
    cfg = _db_config()
    conn = pymysql.connect(cursorclass=DictCursor, **cfg)
    try:
        yield conn
    finally:
        conn.close()


def _build_where(
    filters: Optional[Dict[str, Any]]
) -> Tuple[str, List[Any]]:
    """把 {"col": value} 转成参数化 WHERE 片段，支持多值(元组)的 IN。

    返回 (where_clause, params)。
    """
    if not filters:
        return "", []
    clauses: List[str] = []
    params: List[Any] = []
    for col, val in filters.items():
        if isinstance(val, (list, tuple, set)):
            placeholders = ", ".join(["%s"] * len(val))
            clauses.append(f"`{col}` IN ({placeholders})")
            params.extend(list(val))
        else:
            clauses.append(f"`{col}` = %s")
            params.append(val)
    return " WHERE " + " AND ".join(clauses), params


def fetch_all(
    sql: str, params: Optional[Sequence[Any]] = None
) -> List[Dict[str, Any]]:
    """执行 SELECT，返回字典列表。"""
    with _connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return list(cur.fetchall())


def fetch_one(
    sql: str, params: Optional[Sequence[Any]] = None
) -> Optional[Dict[str, Any]]:
    rows = fetch_all(sql, params)
    return rows[0] if rows else None


def table_exists(table: str = PERSONNEL_TABLE) -> bool:
    """判断人员表是否存在。"""
    cfg = _db_config()
    with _connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name = %s LIMIT 1",
                (cfg["database"], table),
            )
            return cur.fetchone() is not None


def list_columns(table: str = PERSONNEL_TABLE) -> List[str]:
    """返回表的所有列名。"""
    rows = fetch_all(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
        (_db_config()["database"], table),
    )
    return [r["column_name"] if "column_name" in r else r["COLUMN_NAME"] for r in rows]


def run_query(
    sql: str, params: Optional[Sequence[Any]] = None
) -> List[Dict[str, Any]]:
    """通用只读查询（供 analytics 复用，集中在此保证参数化）。"""
    return fetch_all(sql, params)


def _parse_kwargs(filters: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return filters or {}


# ---- 语义化读取接口（供 data.py 使用）----


def get_all_records(filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """读取人员表全部记录（可带过滤）。"""
    where, params = _build_where(filters)
    return fetch_all(f"SELECT * FROM `{PERSONNEL_TABLE}`{where}", params)


def get_headcount(filters: Optional[Dict[str, Any]] = None) -> int:
    where, params = _build_where(filters)
    row = fetch_one(
        f"SELECT COUNT(*) AS cnt FROM `{PERSONNEL_TABLE}`{where}", params
    )
    return int(row["cnt"]) if row else 0


def distinct_values(column: str) -> List[Any]:
    """返回某列的去重值（用于部门/职级等枚举）。"""
    rows = fetch_all(
        f"SELECT DISTINCT `{column}` FROM `{PERSONNEL_TABLE}` "
        f"WHERE `{column}` IS NOT NULL ORDER BY `{column}`"
    )
    return [r[column] for r in rows]


def aggregate_count(
    group_column: str, filters: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """按某列分组统计人数。"""
    where, params = _build_where(filters)
    return fetch_all(
        f"SELECT `{group_column}` AS label, COUNT(*) AS value "
        f"FROM `{PERSONNEL_TABLE}`{where} "
        f"GROUP BY `{group_column}` ORDER BY value DESC",
        params,
    )


def avg_numeric(
    column: str, filters: Optional[Dict[str, Any]] = None
) -> Optional[float]:
    where, params = _build_where(filters)
    row = fetch_one(
        f"SELECT AVG(`{column}`) AS v FROM `{PERSONNEL_TABLE}`{where}", params
    )
    return float(row["v"]) if row and row["v"] is not None else None


__all__ = [
    "PERSONNEL_TABLE",
    "table_exists",
    "list_columns",
    "run_query",
    "get_all_records",
    "get_headcount",
    "distinct_values",
    "aggregate_count",
    "avg_numeric",
]
