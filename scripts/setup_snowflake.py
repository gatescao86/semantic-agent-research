#!/usr/bin/env python
"""M0 connectivity + schema-discovery check for SNOWFLAKE_PUBLIC_DATA_FREE.

This does NOT mutate anything — it only runs SHOW/DESCRIBE/SELECT COUNT(*)
against the free public data database to confirm read access, and prints the
actual table names/columns found so the semantic model YAML files
(semantic_models/domains/*.yaml) can be corrected against reality. Those
files were authored from Snowflake's public documentation, not a live
account, and are marked as needing verification — this script is that
verification step.

Run: python scripts/setup_snowflake.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agents.sql_executor import SqlExecutor  # noqa: E402

EXPECTED_TABLES = [
    "GEOGRAPHY_INDEX",
    "GEOGRAPHY_RELATIONSHIPS",
    "FINANCIAL_ECONOMIC_INDICATOR_ATTRIBUTES",
    "FINANCIAL_ECONOMIC_INDICATOR_TIMESERIES",
    "CENSUS_ACS_ATTRIBUTES",
    "CENSUS_ACS_TIMESERIES",
    "COMPANY_INDEX",
    "SEC_REPORT_INDEX",
    "SEC_METRICS_TIMESERIES",
]


def main() -> None:
    database = os.environ.get("SNOWFLAKE_PUBLIC_DATA_DATABASE", "SNOWFLAKE_PUBLIC_DATA_FREE")
    schema = os.environ.get("SNOWFLAKE_PUBLIC_DATA_SCHEMA", "CYBERSYN")

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

    found_tables = {row[0] for row in result.rows}
    print(f"Found {len(found_tables)} tables in {database}.{schema}:\n")
    for row in result.rows:
        print(f"  {row[0]:<50} ~{row[1]} rows")

    print("\n--- Cross-check against semantic model assumptions ---")
    missing = [t for t in EXPECTED_TABLES if t not in found_tables]
    if missing:
        print(
            "\nThe following tables were assumed in semantic_models/domains/*.yaml "
            "but were NOT found under this schema — update those YAML files with "
            "the real table names before trusting them:"
        )
        for t in missing:
            print(f"  MISSING: {t}")
    else:
        print("\nAll tables referenced in semantic_models/domains/*.yaml were found. "
              "Column names still need spot-checking (see below).")

    print(
        "\nNext: run DESCRIBE TABLE on each table above (or query "
        f"{database}.INFORMATION_SCHEMA.COLUMNS) and diff actual column names "
        "against semantic_models/domains/*.yaml — primary/foreign key column "
        "names in particular were guessed from documentation, not verified."
    )

    executor.close()


if __name__ == "__main__":
    main()
