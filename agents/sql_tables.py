"""Warehouse table names referenced by a SQL statement.

Used by condition 3's domain-scope gate and by eval coverage so both
read the same tables out of the same SQL.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError


def referenced_tables(sql: str) -> set[str]:
    """Return the warehouse tables named in this SQL, as uppercase strings.

    CTE aliases are omitted. Names look like YAML entity tables
    (CATALOG.SCHEMA.TABLE, or a bare table if the SQL did not qualify them).
    """
    stripped = sql.strip()
    if not stripped:
        return set()
    try:
        trees = sqlglot.parse(stripped, dialect="snowflake")
    except ParseError:
        return set()

    tables: set[str] = set()
    for tree in trees:
        if tree is None:
            continue
        cte_names = {cte.alias_or_name.upper() for cte in tree.find_all(exp.CTE)}
        for table in tree.find_all(exp.Table):
            name = (table.name or "").upper()
            if not name or name in cte_names:
                continue
            parts = [p.upper() for p in (table.catalog, table.db, table.name) if p]
            tables.add(".".join(parts))
    return tables


def check_domain_scope(sql: str, allowed_tables: set[str]) -> str | None:
    """If this SQL uses a table not in `allowed_tables`, return an error string.

    Returns None when the query is in scope. Unparseable SQL is an error.
    """
    stripped = sql.strip()
    if not stripped:
        return "Empty SQL statement."
    try:
        sqlglot.parse(stripped, dialect="snowflake")
    except ParseError as exc:
        return f"Could not parse SQL to check domain scope: {exc}"

    out_of_scope = referenced_tables(sql) - allowed_tables
    if out_of_scope:
        return (
            "This tool only has access to tables in this domain. Referenced "
            f"table(s) outside this domain's scope: {sorted(out_of_scope)}. Each "
            "domain tool is scoped to its own tables and cannot JOIN across "
            "domains in a single query — query another domain's tool separately "
            "and combine the results yourself."
        )
    return None
