"""sql_helpers 单元测试 —— 跨库检测、保留字检测、错误增强。"""

import pytest

from src.ops_agent.tools.service_connectors.sql_helpers import (
    detect_cross_db_references,
    detect_reserved_keyword_aliases,
    enhance_mysql_error,
    enhance_pg_error,
)


# ── detect_cross_db_references ──


class TestDetectCrossDbReferences:
    def test_detects_cross_db_in_from(self):
        sql = "SELECT * FROM target_db.daily_sales_summary"
        assert detect_cross_db_references(sql, "staging_db") == ["target_db"]

    def test_detects_cross_db_in_join(self):
        sql = (
            "SELECT c.id FROM clean_orders c "
            "LEFT JOIN target_db.daily_sales_summary t ON c.date = t.date"
        )
        assert detect_cross_db_references(sql, "staging_db") == ["target_db"]

    def test_ignores_same_db(self):
        sql = "SELECT * FROM staging_db.clean_orders"
        assert detect_cross_db_references(sql, "staging_db") == []

    def test_ignores_column_aliases(self):
        """c.order_date 之类的表别名.列名不应被检测为跨库引用。"""
        sql = "SELECT c.order_date, c.region FROM clean_orders c"
        assert detect_cross_db_references(sql, "staging_db") == []

    def test_multiple_cross_dbs_deduped(self):
        sql = (
            "SELECT * FROM db_a.t1 "
            "JOIN db_b.t2 ON t1.id = t2.id "
            "JOIN db_a.t3 ON t1.id = t3.id"
        )
        result = detect_cross_db_references(sql, "my_db")
        assert result == ["db_a", "db_b"]

    def test_case_insensitive(self):
        sql = "SELECT * FROM Target_DB.sales"
        assert detect_cross_db_references(sql, "target_db") == []

    def test_no_cross_db(self):
        sql = "SELECT COUNT(*) FROM clean_orders WHERE status = 'completed'"
        assert detect_cross_db_references(sql, "staging_db") == []


# ── detect_reserved_keyword_aliases ──


class TestDetectReservedKeywordAliases:
    def test_detects_rows_alias(self):
        sql = "SELECT COUNT(*) as rows, SUM(amount) as total FROM orders"
        assert detect_reserved_keyword_aliases(sql) == ["rows"]

    def test_detects_rank_alias(self):
        sql = "SELECT name, score as rank FROM students"
        assert detect_reserved_keyword_aliases(sql) == ["rank"]

    def test_ignores_safe_aliases(self):
        sql = "SELECT COUNT(*) as cnt, SUM(amount) as total FROM orders"
        assert detect_reserved_keyword_aliases(sql) == []

    def test_ignores_backtick_escaped(self):
        """反引号转义的别名不应被匹配（正则只匹配裸标识符）。"""
        sql = "SELECT COUNT(*) as `rows` FROM orders"
        assert detect_reserved_keyword_aliases(sql) == []

    def test_multiple_reserved_keywords(self):
        sql = "SELECT COUNT(*) as rows, AVG(score) as rank FROM t"
        result = detect_reserved_keyword_aliases(sql)
        assert "rows" in result
        assert "rank" in result

    def test_deduplicates(self):
        sql = "SELECT a as rows, b as rows FROM t"
        assert detect_reserved_keyword_aliases(sql) == ["rows"]


# ── enhance_mysql_error ──


class TestEnhanceMysqlError:
    def test_permission_error_with_cross_db(self):
        e = _make_mysql_error(1142, "SELECT command denied for table 'daily_sales_summary'")
        sql = "SELECT * FROM target_db.daily_sales_summary"
        result = enhance_mysql_error(e, sql, "staging_db")
        assert "target_db" in result
        assert "staging_db" in result
        assert "service_id" in result

    def test_permission_error_without_cross_db(self):
        """权限错误但无跨库引用时，保持原始错误信息。"""
        e = _make_mysql_error(1142, "SELECT command denied for table 'secret_table'")
        sql = "SELECT * FROM secret_table"
        result = enhance_mysql_error(e, sql, "staging_db")
        assert "secret_table" in result
        assert "service_id" not in result

    def test_syntax_error_with_reserved_keyword(self):
        e = _make_mysql_error(1064, "You have an error in your SQL syntax")
        sql = "SELECT COUNT(*) as rows FROM orders"
        result = enhance_mysql_error(e, sql, "my_db")
        assert "保留字" in result
        assert "`rows`" in result

    def test_syntax_error_without_reserved_keyword(self):
        e = _make_mysql_error(1064, "You have an error in your SQL syntax")
        sql = "SELCT * FROM orders"  # typo, not reserved keyword
        result = enhance_mysql_error(e, sql, "my_db")
        assert "保留字" not in result

    def test_other_error_passthrough(self):
        e = Exception("connection reset")
        result = enhance_mysql_error(e, "SELECT 1", "my_db")
        assert result == "Exception: connection reset"

    def test_access_denied_for_database(self):
        e = _make_mysql_error(1044, "Access denied for user to database 'target_db'")
        sql = "SELECT * FROM target_db.orders"
        result = enhance_mysql_error(e, sql, "staging_db")
        assert "target_db" in result
        assert "service_id" in result


# ── enhance_pg_error ──


class TestEnhancePgError:
    def test_privilege_error_with_cross_db(self):
        e = _make_named_error("InsufficientPrivilegeError", "permission denied")
        sql = "SELECT * FROM other_db.users"
        result = enhance_pg_error(e, sql, "my_db")
        assert "other_db" in result
        assert "跨数据库" in result

    def test_syntax_error_with_reserved_keyword(self):
        e = _make_named_error("PostgresSyntaxError", "syntax error")
        sql = "SELECT COUNT(*) as rows FROM t"
        result = enhance_pg_error(e, sql, "my_db")
        assert "保留字" in result
        assert '"rows"' in result

    def test_other_error_passthrough(self):
        e = Exception("timeout")
        result = enhance_pg_error(e, "SELECT 1", "my_db")
        assert result == "Exception: timeout"


# ── helpers ──


class _OperationalError(Exception):
    """模拟 aiomysql/pymysql OperationalError。"""


def _make_mysql_error(code: int, msg: str) -> Exception:
    """构造一个模拟 aiomysql/pymysql 异常（args[0] 是 int 错误码）。"""
    return _OperationalError(code, msg)


def _make_named_error(class_name: str, msg: str) -> Exception:
    """构造一个自定义类名的异常。"""
    cls = type(class_name, (Exception,), {})
    return cls(msg)
