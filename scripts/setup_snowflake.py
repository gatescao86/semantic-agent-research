#!/usr/bin/env python
"""M0 connectivity + schema-discovery check for SNOWFLAKE_PUBLIC_DATA_FREE.

This does NOT mutate anything — it only runs SELECT against
INFORMATION_SCHEMA to confirm read access, and cross-checks the live table
list against what semantic_models/domains/*.yaml actually reference (parsed
from their `table:` fields, not a separately hardcoded list — a hardcoded
list drifts out of sync with the YAML files, which is exactly what happened
here once before).

Run: python scripts/setup_snowflake.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agents.sql_executor import SqlExecutor  # noqa: E402
from semantic_models.schema import DOMAINS_DIR, load_semantic_model  # noqa: E402


def expected_tables() -> dict[str, str]:
    """Map real table name (upper) -> owning domain, parsed from the domain YAMLs."""
    tables: dict[str, str] = {}
    for path in sorted(DOMAINS_DIR.glob("*.yaml")):
        model = load_semantic_model(path)
        for entity in model.entities:
            table_name = entity.table.split(".")[-1].upper()
            tables[table_name] = model.domain
    return tables


def main() -> None:
    database = os.environ.get("SNOWFLAKE_PUBLIC_DATA_DATABASE", "SNOWFLAKE_PUBLIC_DATA_FREE")
    schema = os.environ.get("SNOWFLAKE_PUBLIC_DATA_SCHEMA", "PUBLIC_DATA_FREE")

    executor = SqlExecutor()

    print(f"Connecting and listing tables in {database}.{schema} ...\n")
    result = executor.execute(f"SELECT TABLE_NAME, ROW_COUNT FROM {database}.INFORMATION_SCHEMA.TABLES "
                               f"WHERE TABLE_SCHEMA = '{schema}' ORDER BY TABLE_NAME")
    if result.error:
        print(f"FAILED to list tables: {result.error}", file=sys.stderr)
        print(
            "\nCheck SNOWFLAKE_ACCOUNT / SNOWFLAKE_USER / SNOWFLAKE_PASSWORD / "
            "SNOWFLAKE_ROLE / SNOWFLAKE_WAREHOUSE in .env, and confirm the "
            "'Snowflake Public Data (Free)' Marketplace listing has been added "
            "to this account (it must be explicitly added even though it's free).",
            file=sys.stderr,
        )
        raise SystemExit(1)

    found_tables = {row[0].upper() for row in result.rows}
    print(f"Found {len(found_tables)} tables in {database}.{schema}.\n")

    expected = expected_tables()
    print(f"--- Cross-check against semantic_models/domains/*.yaml ({len(expected)} tables referenced) ---")
    missing = {t: domain for t, domain in expected.items() if t not in found_tables}
    if missing:
        print(
            "\nThe following tables are referenced in semantic_models/domains/*.yaml "
            "but were NOT found in this schema — the domain model is out of date "
            "or this account doesn't have access to them:"
        )
        for t, domain in sorted(missing.items()):
            print(f"  MISSING: {t}  (domain: {domain})")
        executor.close()
        raise SystemExit(1)

    print("\nAll tables referenced in semantic_models/domains/*.yaml were found. Connectivity OK.")
    executor.close()


if __name__ == "__main__":
    main()
