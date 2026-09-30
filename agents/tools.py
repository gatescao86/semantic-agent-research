"""
Shared tool definitions for conditions 1 (schema_only) and 2 (unified).
"""

from __future__ import annotations

TOOL_RUN_SQL = {
    "name": "run_sql",
    "description": (
        "Execute a read-only SQL SELECT query against Snowflake and return up to "
        "500 rows plus row count and column types. Only SELECT (or WITH ... SELECT) "
        "statements are allowed; DDL/DML/multi-statement input is rejected before "
        "execution."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "A single SELECT (or WITH ... SELECT) statement.",
            }
        },
        "required": ["sql"],
    },
}

ALL_TOOLS = [TOOL_RUN_SQL]
