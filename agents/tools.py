"""Shared tool definitions for the agent loop.

Identical in both Experiment A (unified) and Experiment B (routed) — see
plan §5. Keeping the tool surface byte-identical between conditions matters:
if the unified and routed agents had different tools, differences in
tool-call counts or behavior could be an artifact of the tool surface, not
of semantic architecture.
"""

from __future__ import annotations

TOOL_GET_SEMANTIC_MODEL = {
    "name": "get_semantic_model",
    "description": (
        "Return the semantic model (entities, metrics, dimensions, relationships) "
        "available to you for SQL generation. The model is already provided in your "
        "system prompt — call this only if you need to re-confirm its contents, e.g. "
        "after a long tool-use exchange."
    ),
    "input_schema": {"type": "object", "properties": {}, "required": []},
}

TOOL_RUN_SQL = {
    "name": "run_sql",
    "description": (
        "Execute a read-only SQL SELECT query against Snowflake and return up to "
        "500 rows plus row count and column types. Only SELECT (or WITH ... SELECT) "
        "statements are allowed; DDL/DML/multi-statement input is rejected before "
        "execution. Use this after consulting the semantic model to translate the "
        "business question into a query over the underlying tables."
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

ALL_TOOLS = [TOOL_GET_SEMANTIC_MODEL, TOOL_RUN_SQL]
