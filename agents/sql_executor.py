"""Single shared, read-only Snowflake execution wrapper.

Used identically by unified_agent.py and routed_agent.py (via agents/loop.py),
and by eval/run_eval.py for ground-truth comparison queries. This is
deliberate: Experiment A and B must run the exact same execution code path,
against the same warehouse/database/role, so nothing about SQL execution
itself can differ between conditions.

Safety model: the primary control is a read-only Snowflake role (configure
this at the account level — this code cannot create or enforce grants). The
checks below are defense in depth, not a substitute for that: they reject
anything that isn't a single SELECT/WITH statement before it reaches
Snowflake.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import snowflake.connector
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_DISALLOWED_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|MERGE|GRANT|REVOKE|"
    r"COPY|PUT|GET|CALL|EXECUTE|USE|UNLOAD)\b",
    re.IGNORECASE,
)
_LEADING_KEYWORD = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)


class UnsafeSqlError(ValueError):
    """Raised when a query fails the read-only pre-execution check."""


@dataclass
class QueryResult:
    sql: str
    columns: list[str] = field(default_factory=list)
    column_types: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    row_count_returned: int = 0
    truncated: bool = False
    execution_ms: int = 0
    error: str | None = None

    def to_tool_result_text(self, max_preview_rows: int = 50) -> str:
        """Compact text representation to feed back to the agent as a tool result."""
        if self.error:
            return f"SQL ERROR: {self.error}"
        header = ", ".join(self.columns)
        preview = self.rows[:max_preview_rows]
        lines = [f"columns: {header}", f"row_count: {self.row_count_returned}"]
        if self.truncated:
            lines.append(f"(truncated to {self.row_count_returned} rows)")
        lines.append("rows:")
        lines.extend(str(row) for row in preview)
        return "\n".join(lines)


def check_sql_is_read_only(sql: str) -> None:
    """Raise UnsafeSqlError if `sql` is not a single read-only SELECT/WITH statement."""
    stripped = sql.strip()
    if not stripped:
        raise UnsafeSqlError("Empty SQL statement.")

    # Reject multiple statements: a semicolon followed by any non-whitespace
    # content (a single trailing semicolon is fine).
    body = stripped[:-1] if stripped.endswith(";") else stripped
    if ";" in body:
        raise UnsafeSqlError("Multiple statements are not allowed — submit one SELECT at a time.")

    if not _LEADING_KEYWORD.match(stripped):
        raise UnsafeSqlError("Only SELECT (or WITH ... SELECT) statements are allowed.")

    if _DISALLOWED_KEYWORDS.search(stripped):
        match = _DISALLOWED_KEYWORDS.search(stripped)
        raise UnsafeSqlError(f"Disallowed keyword in query: {match.group(0)!r}.")


class SqlExecutor:
    def __init__(
        self,
        max_rows_returned: int = 500,
        query_timeout_seconds: int = 60,
    ) -> None:
        self.max_rows_returned = max_rows_returned
        self.query_timeout_seconds = query_timeout_seconds
        self._conn: snowflake.connector.SnowflakeConnection | None = None

    def _connect(self) -> snowflake.connector.SnowflakeConnection:
        if self._conn is None or self._conn.is_closed():
            self._conn = snowflake.connector.connect(
                account=_require_env("SNOWFLAKE_ACCOUNT"),
                user=_require_env("SNOWFLAKE_USER"),
                password=_require_env("SNOWFLAKE_PASSWORD"),
                role=_require_env("SNOWFLAKE_ROLE"),
                warehouse=_require_env("SNOWFLAKE_WAREHOUSE"),
                database=os.environ.get("SNOWFLAKE_PUBLIC_DATA_DATABASE", "SNOWFLAKE_PUBLIC_DATA_FREE"),
                schema=os.environ.get("SNOWFLAKE_PUBLIC_DATA_SCHEMA", "CYBERSYN"),
                login_timeout=30,
                network_timeout=self.query_timeout_seconds,
            )
        return self._conn

    def execute(self, sql: str) -> QueryResult:
        try:
            check_sql_is_read_only(sql)
        except UnsafeSqlError as exc:
            return QueryResult(sql=sql, error=str(exc))

        conn = self._connect()
        cursor = conn.cursor()
        start = time.monotonic()
        try:
            cursor.execute(f"ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = {self.query_timeout_seconds}")
            cursor.execute(sql)
            all_rows = cursor.fetchmany(self.max_rows_returned + 1)
            truncated = len(all_rows) > self.max_rows_returned
            rows = all_rows[: self.max_rows_returned]
            columns = [c[0] for c in cursor.description]
            column_types = [str(c[1]) for c in cursor.description]
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return QueryResult(
                sql=sql,
                columns=columns,
                column_types=column_types,
                rows=rows,
                row_count_returned=len(rows),
                truncated=truncated,
                execution_ms=elapsed_ms,
            )
        except Exception as exc:  # noqa: BLE001 — surface any Snowflake error to the caller/agent
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return QueryResult(sql=sql, execution_ms=elapsed_ms, error=str(exc))
        finally:
            cursor.close()

    def close(self) -> None:
        if self._conn is not None and not self._conn.is_closed():
            self._conn.close()


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}. See .env.example.")
    return value
