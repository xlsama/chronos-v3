"""SQL 预检与错误增强工具 —— 跨库引用检测、保留字检测、错误信息增强。"""

import re

# MySQL 8.0 常见保留字（容易被误用作别名的子集）
MYSQL_RESERVED_KEYWORDS: frozenset[str] = frozenset({
    "ROWS", "GROUPS", "WINDOW", "RECURSIVE", "RANK", "ROW",
    "CUBE", "LATERAL", "SYSTEM", "STORED", "VIRTUAL", "DENSE_RANK",
    "CUME_DIST", "EMPTY", "GROUPING", "JSON_TABLE", "LAG", "LEAD",
    "NTH_VALUE", "NTILE", "OF", "OVER", "PERCENT_RANK", "ROW_NUMBER",
    "FUNCTION", "MASTER", "SCHEMA",
})

# 匹配 FROM/JOIN 后面的 db.table 模式
_CROSS_DB_RE = re.compile(r"(?:FROM|JOIN)\s+(\w+)\.(\w+)", re.IGNORECASE)

# 匹配 AS alias 模式（不带引号/反引号的别名）
_ALIAS_RE = re.compile(r"\bAS\s+([A-Za-z_]\w*)\b", re.IGNORECASE)


def detect_cross_db_references(sql: str, current_db: str) -> list[str]:
    """检测 SQL 中 FROM/JOIN 后的跨库引用，返回外部数据库名列表。"""
    foreign = []
    for m in _CROSS_DB_RE.finditer(sql):
        db_name = m.group(1)
        if db_name.lower() != current_db.lower():
            foreign.append(db_name)
    return list(dict.fromkeys(foreign))  # 去重保序


def detect_reserved_keyword_aliases(sql: str) -> list[str]:
    """检测 SQL 中使用了 MySQL 保留字作为未转义别名的情况。"""
    found = []
    for m in _ALIAS_RE.finditer(sql):
        alias = m.group(1)
        if alias.upper() in MYSQL_RESERVED_KEYWORDS:
            found.append(alias)
    return list(dict.fromkeys(found))


def enhance_mysql_error(e: Exception, sql: str, current_db: str) -> str:
    """增强 MySQL 错误信息，添加可操作的修复建议。"""
    original = f"{type(e).__name__}: {e}"
    code = e.args[0] if e.args and isinstance(e.args[0], int) else None

    # 权限错误 → 检查跨库引用
    if code in (1142, 1044):
        cross_dbs = detect_cross_db_references(sql, current_db)
        if cross_dbs:
            db_names = ", ".join(cross_dbs)
            return (
                f"{original}\n\n"
                f"此连接绑定到数据库 '{current_db}'，检测到跨库引用: {db_names}。"
                f"不同数据库可能在不同服务器上，无法通过 db.table 语法直接访问。"
                f"请为每个数据库分别使用对应的 service_id 执行查询，然后合并分析结果。"
            )

    # 语法错误 → 检查保留字
    if code == 1064:
        keywords = detect_reserved_keyword_aliases(sql)
        if keywords:
            suggestions = ", ".join(f"`{k}`" for k in keywords)
            return (
                f"{original}\n\n"
                f"可能原因: {', '.join(keywords)} 是 MySQL 8.0 保留字。"
                f"请使用反引号转义别名: {suggestions}"
            )

    return original


def enhance_pg_error(e: Exception, sql: str, current_db: str) -> str:
    """增强 PostgreSQL 错误信息。"""
    original = f"{type(e).__name__}: {e}"
    err_cls = type(e).__name__

    # asyncpg 的权限错误
    if "InsufficientPrivilege" in err_cls:
        cross_dbs = detect_cross_db_references(sql, current_db)
        if cross_dbs:
            db_names = ", ".join(cross_dbs)
            return (
                f"{original}\n\n"
                f"此连接绑定到数据库 '{current_db}'，检测到跨库引用: {db_names}。"
                f"PostgreSQL 不支持跨数据库查询。"
                f"请为每个数据库分别使用对应的 service_id 执行查询。"
            )

    # 语法错误
    if "Syntax" in err_cls:
        keywords = detect_reserved_keyword_aliases(sql)
        if keywords:
            suggestions = ", ".join(f'"{k}"' for k in keywords)
            return (
                f"{original}\n\n"
                f"可能原因: {', '.join(keywords)} 是保留字。"
                f"请使用双引号转义: {suggestions}"
            )

    return original
