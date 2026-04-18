"""Extended SQL safety tests for edge cases and bypass attempts.

Supplements the base SQL validation tests in test_snowflake_client.py
with adversarial inputs, comment injection, and encoding tricks.
"""

import pytest

from app.snowflake_client import _is_safe_sql, execute_analyst_sql


class TestSqlSafetyEdgeCases:
    """Edge cases for the _is_safe_sql regex guard."""

    def test_comment_with_dangerous_keyword_rejected(self):
        # Regex doesn't parse SQL comments, so DROP in a comment triggers rejection.
        # This is a conservative false positive — safer than missing a real threat.
        assert _is_safe_sql("SELECT 1 -- DROP TABLE users") is False

    def test_block_comment_does_not_bypass(self):
        assert _is_safe_sql("SELECT 1 /* DROP TABLE users */") is False

    def test_union_select_allowed(self):
        assert _is_safe_sql("SELECT 1 UNION SELECT 2") is True

    def test_subquery_allowed(self):
        assert _is_safe_sql("SELECT * FROM (SELECT 1 AS x) sub") is True

    def test_alter_rejected(self):
        assert _is_safe_sql("ALTER TABLE users ADD COLUMN x INT") is False

    def test_merge_rejected(self):
        assert _is_safe_sql("MERGE INTO t USING s ON t.id = s.id") is False

    def test_execute_rejected(self):
        assert _is_safe_sql("EXECUTE IMMEDIATE 'DROP TABLE t'") is False

    def test_copy_rejected(self):
        assert _is_safe_sql("COPY INTO @stage FROM t") is False

    def test_put_rejected(self):
        assert _is_safe_sql("PUT file:///tmp/data.csv @stage") is False

    def test_remove_rejected(self):
        assert _is_safe_sql("REMOVE @stage/data.csv") is False

    def test_revoke_rejected(self):
        assert _is_safe_sql("REVOKE SELECT ON t FROM PUBLIC") is False

    def test_call_rejected(self):
        assert _is_safe_sql("CALL system$cancel_all_queries()") is False

    def test_select_with_excessive_whitespace(self):
        assert _is_safe_sql("   SELECT   1   ") is True

    def test_select_with_tabs_and_newlines(self):
        assert _is_safe_sql("\tSELECT\n1") is True

    def test_cte_with_dangerous_keyword_in_alias(self):
        # "drop_count" contains DROP as substring but not as standalone word
        assert _is_safe_sql("WITH drop_count AS (SELECT 1) SELECT * FROM drop_count") is True

    def test_column_named_with_keyword_substring_rejected(self):
        # Regex uses \b word boundaries, so "insert_date" doesn't contain
        # standalone INSERT — this should be allowed
        assert _is_safe_sql("SELECT insert_date FROM t") is True

    def test_only_semicolon_rejected(self):
        assert _is_safe_sql(";") is False

    def test_null_byte_rejected(self):
        assert _is_safe_sql("SELECT 1\x00; DROP TABLE t") is False

    def test_very_long_select_allowed(self):
        long_cols = ", ".join(f"col_{i}" for i in range(100))
        assert _is_safe_sql(f"SELECT {long_cols} FROM big_table") is True

    # --- Mixed case keyword tests ---

    def test_mixed_case_select_allowed(self):
        assert _is_safe_sql("SeLeCt 1") is True

    def test_mixed_case_with_allowed(self):
        assert _is_safe_sql("WiTh cte AS (SeLeCt 1) SeLeCt * FROM cte") is True

    def test_mixed_case_drop_rejected(self):
        assert _is_safe_sql("SELECT 1 DRoP TABLE t") is False

    def test_mixed_case_insert_rejected(self):
        assert _is_safe_sql("InSeRt INTO t VALUES (1)") is False

    # --- CTE variants ---

    def test_with_recursive_cte_allowed(self):
        """WITH RECURSIVE is a valid read-only CTE pattern."""
        sql = "WITH RECURSIVE cte AS (SELECT 1 UNION ALL SELECT 1) SELECT * FROM cte"
        assert _is_safe_sql(sql) is True

    # --- Additional dangerous keywords ---

    def test_get_rejected(self):
        assert _is_safe_sql("GET @stage/file.csv") is False

    def test_truncate_rejected(self):
        assert _is_safe_sql("TRUNCATE TABLE t") is False

    def test_grant_rejected(self):
        assert _is_safe_sql("GRANT SELECT ON t TO role_name") is False

    # --- Keyword as non-standalone substring ---

    def test_column_named_delete_count_allowed(self):
        """'delete_count' has DELETE as substring but not standalone word."""
        assert _is_safe_sql("SELECT delete_count FROM t") is True

    def test_column_named_updated_at_allowed(self):
        """'updated_at' has UPDATE as substring but not standalone word."""
        assert _is_safe_sql("SELECT updated_at FROM t") is True

    def test_column_named_create_date_allowed(self):
        """'create_date' has CREATE as substring but not standalone word."""
        assert _is_safe_sql("SELECT create_date FROM t") is True

    # --- Whitespace/format edge cases ---

    def test_leading_newlines_accepted(self):
        assert _is_safe_sql("\n\nSELECT 1") is True

    def test_windows_line_endings_accepted(self):
        assert _is_safe_sql("SELECT\r\n1") is True

    def test_only_whitespace_and_newlines_rejected(self):
        assert _is_safe_sql("\n\t\r  ") is False


class TestSqlSafetyIntegration:
    """Verify _is_safe_sql is enforced by execute_analyst_sql."""

    def test_alter_via_execute_raises(self):
        with pytest.raises(ValueError, match="read-only"):
            execute_analyst_sql("ALTER SESSION SET TIMEZONE = 'UTC'")

    def test_call_via_execute_raises(self):
        with pytest.raises(ValueError, match="read-only"):
            execute_analyst_sql("CALL system$cancel_all_queries()")

    def test_copy_via_execute_raises(self):
        with pytest.raises(ValueError, match="read-only"):
            execute_analyst_sql("COPY INTO @stage FROM t")
