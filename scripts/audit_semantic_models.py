#!/usr/bin/env python
"""Column-level audit of domain semantic models against live table metadata.

setup_snowflake.py only checks that referenced *tables* exist.
validate_semantic_models.py only checks YAML/pydantic and in-file entity names.
This checks that every column the YAML names exists on the live table, lists
live columns the YAML never mentions, and flags join-target columns that
other domains reference but the target domain never declares.

Live columns come from `SELECT * … LIMIT 0` (cursor description), not
INFORMATION_SCHEMA.COLUMNS piped through SqlExecutor: that executor caps
results at 500 rows, which truncates wide tables and reports real columns
as missing.

Docs for table/column meaning: https://data-docs.snowflake.com/sources
(per-source pages under /api/sources/<slug>.json).

Run: python scripts/audit_semantic_models.py

Exit 1 if any declared column is missing from the warehouse, or a YAML
table cannot be described.
"""

from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agents.sql_executor import SqlExecutor  # noqa: E402
from semantic_models.schema import DOMAINS_DIR, load_semantic_model  # noqa: E402

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Columns that matter for this study's customer questions if left unmodeled.
# Informed by eval questions + Snowflake Public Data source docs (H.8 SA,
# ACS 1-year vs 5-year, FDIC cert/RSSD, HMDA tract income).
PRIORITY = re.compile(
    r"income|tract|minority|lei|cert|rssd|frequency|seasonal|"
    r"release|census|occupancy|purpose|action|denial|ethnicity|"
    r"race|hoepa|conforming|assessment|cra|deposit|loan|"
    r"active|measurement|industry|unit",
    re.IGNORECASE,
)


def _short(table: str) -> str:
    return table.split(".")[-1].upper()


def _add(declared: dict[str, dict], table: str, column: str) -> None:
    declared[_short(table)]["columns"].add(column.upper())
    declared[_short(table)]["fqdn"] = table


def declared_columns() -> dict[str, dict]:
    """Unqualified table name -> {domains, columns, fqdn}."""
    out: dict[str, dict] = defaultdict(lambda: {"domains": set(), "columns": set(), "fqdn": ""})
    for path in sorted(DOMAINS_DIR.glob("*.yaml")):
        model = load_semantic_model(path)
        table_of = {e.name: e.table for e in model.entities}

        for e in model.entities:
            keys = e.primary_key if isinstance(e.primary_key, list) else [e.primary_key]
            out[_short(e.table)]["domains"].add(model.domain)
            out[_short(e.table)]["fqdn"] = e.table
            for k in keys:
                _add(out, e.table, k)

        for dim in model.dimensions:
            _add(out, table_of[dim.entity], dim.column)

        for met in model.metrics:
            expr = met.expression.strip()
            if _IDENT.match(expr):
                _add(out, table_of[met.entity], expr)

        for rel in model.relationships:
            for ref in (rel.from_, rel.to):
                entity, _, col = ref.partition(".")
                if entity in table_of and col:
                    _add(out, table_of[entity], col)

        for cdk in model.cross_domain_keys:
            _add(out, table_of[cdk.entity], cdk.join_key)
    return out


def undeclared_join_targets() -> list[str]:
    """Cross-domain join targets that the *target* YAML never names as a column.

    deposits.branch.fdic_institution_certificate_number references
    financial_institutions.institution.fdic_cert — if fdic_cert is only
    mentioned in a description, agents following 'do not guess column
    names that aren't in the model' will not filter on it in that domain.
    """
    models = [load_semantic_model(p) for p in sorted(DOMAINS_DIR.glob("*.yaml"))]
    by_domain = {m.domain: m for m in models}
    entity_table: dict[tuple[str, str], str] = {}
    for m in models:
        for e in m.entities:
            entity_table[(m.domain, e.name)] = e.table

    declared = declared_columns()
    missing: list[str] = []
    for m in models:
        for cdk in m.cross_domain_keys:
            parts = cdk.references.split(".")
            if len(parts) != 3:
                missing.append(f"{m.domain}.{cdk.entity}.{cdk.join_key} has malformed references {cdk.references!r}")
                continue
            ref_domain, ref_entity, ref_col = parts
            table = entity_table.get((ref_domain, ref_entity))
            if table is None:
                missing.append(
                    f"{m.domain}.{cdk.entity}.{cdk.join_key} -> {cdk.references} "
                    f"(target entity not found)"
                )
                continue
            if ref_col.upper() not in declared[_short(table)]["columns"]:
                owner = by_domain[ref_domain].domain
                missing.append(
                    f"{m.domain}.{cdk.entity}.{cdk.join_key} -> {cdk.references} "
                    f"(column not declared on {owner}.{ref_entity})"
                )
    return missing


def live_columns(executor: SqlExecutor, declared: dict[str, dict]) -> tuple[dict[str, set[str]], list[str]]:
    """Describe each modeled table via SELECT * LIMIT 0."""
    by_table: dict[str, set[str]] = {}
    errors: list[str] = []
    for table, info in sorted(declared.items()):
        fqdn = info["fqdn"]
        result = executor.execute(f"SELECT * FROM {fqdn} LIMIT 0")
        if result.error:
            errors.append(f"{table}: {result.error}")
            continue
        by_table[table] = {c.upper() for c in (result.columns or [])}
    return by_table, errors


def main() -> None:
    database = os.environ.get("SNOWFLAKE_PUBLIC_DATA_DATABASE", "SNOWFLAKE_PUBLIC_DATA_FREE")
    schema = os.environ.get("SNOWFLAKE_PUBLIC_DATA_SCHEMA", "PUBLIC_DATA_FREE")

    declared = declared_columns()
    tables = sorted(declared)
    join_gaps = undeclared_join_targets()

    executor = SqlExecutor()
    live, describe_errors = live_columns(executor, declared)
    executor.close()

    missing_declared: list[str] = []
    missing_tables: list[str] = []
    gaps: list[tuple[str, str, list[str], list[str]]] = []

    print(f"Auditing {len(tables)} modeled tables in {database}.{schema}")
    print("Live columns from SELECT * LIMIT 0 (not INFORMATION_SCHEMA).\n")

    for table in tables:
        domains = ", ".join(sorted(declared[table]["domains"]))
        want = declared[table]["columns"]
        have = live.get(table)
        if have is None:
            missing_tables.append(f"{table} ({domains})")
            continue
        gone = sorted(want - have)
        extra = sorted(have - want)
        priority = [c for c in extra if PRIORITY.search(c)]
        if gone:
            for col in gone:
                missing_declared.append(f"{table}.{col}  [{domains}]")
        modeled = len(want & have)
        print(
            f"{table:55s}  [{domains:24s}]  "
            f"modeled {modeled}/{len(have)} live cols, "
            f"{len(extra)} unmodeled"
        )
        if gone:
            print(f"  MISSING FROM WAREHOUSE (YAML is wrong): {', '.join(gone)}")
        if priority:
            print(f"  unmodeled (eval-relevant): {', '.join(priority)}")
        gaps.append((table, domains, extra, priority))

    print()
    if describe_errors:
        print("Could not describe these tables:")
        for line in describe_errors:
            print(f"  {line}")
    if missing_tables:
        print("Tables in YAML but not describable:")
        for line in missing_tables:
            print(f"  {line}")
    if missing_declared:
        print("Columns named in YAML but not in the warehouse:")
        for line in missing_declared:
            print(f"  {line}")

    print("\n--- Join targets referenced but not declared on the target model ---")
    if join_gaps:
        for line in join_gaps:
            print(f"  {line}")
    else:
        print("None.")

    print("\n--- Eval-relevant unmodeled columns (keyword filter) ---")
    any_priority = False
    for table, domains, extra, priority in gaps:
        if not priority:
            continue
        any_priority = True
        print(f"\n{table} [{domains}]")
        for col in priority:
            print(f"  {col}")
    if not any_priority:
        print("None.")

    n_bad = len(missing_tables) + len(missing_declared) + len(describe_errors)
    if n_bad:
        raise SystemExit(1)
    print("\nAll YAML-declared columns exist in the warehouse.")
    if join_gaps:
        print(
            f"{len(join_gaps)} join-target column(s) are used as FK targets "
            "but never declared on the target domain — agents will not see them "
            "as filterable columns in that domain's model."
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
