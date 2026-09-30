#!/usr/bin/env python
"""Generate semantic_models/raw/schema_catalog.md from the study's tables.

Condition 1 (schema_only) must see the same table universe as conditions
2 and 3 — the tables named in semantic_models/domains/*.yaml — but as
physical columns, not a semantic model. Live column names and types come
from `SELECT * … LIMIT 0` (same path as scripts/audit_semantic_models.py).
`--from-yaml` lists only YAML-declared columns, for offline tests; do not
freeze eval-v1 on that output.

Run:
    python scripts/generate_schema_catalog.py
    python scripts/generate_schema_catalog.py --check
    python scripts/generate_schema_catalog.py --from-yaml
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from snowflake.connector.constants import FIELD_ID_TO_NAME  # noqa: E402

from semantic_models.schema import (  # noqa: E402
    DOMAINS_DIR,
    load_semantic_model,
    study_tables,
)

CATALOG_PATH = REPO_ROOT / "semantic_models" / "raw" / "schema_catalog.md"

LIVE_HEADER = (
    "# GENERATED FILE — do not hand-edit.\n"
    "# Produced by scripts/generate_schema_catalog.py from live Snowflake\n"
    "# columns (SELECT * LIMIT 0) for every table in semantic_models/domains/*.yaml.\n"
    "# Re-run that script after adding or removing a domain table, and commit the result.\n"
    "# Physical catalog only: no metrics, entities, synonyms, or certified joins.\n\n"
)

YAML_HEADER = (
    "# GENERATED FILE — do not hand-edit.\n"
    "# Produced by scripts/generate_schema_catalog.py --from-yaml.\n"
    "# YAML-declared columns only — regenerate against Snowflake before freezing eval-v1.\n"
    "# Physical catalog only: no metrics, entities, synonyms, or certified joins.\n\n"
)


@dataclass(frozen=True)
class CatalogColumn:
    name: str
    type: str


@dataclass(frozen=True)
class CatalogTable:
    fqdn: str
    domains: tuple[str, ...]
    columns: tuple[CatalogColumn, ...]


def render_schema_catalog(tables: list[CatalogTable], header: str) -> str:
    lines = [header.rstrip(), ""]
    for table in tables:
        domain_label = ", ".join(table.domains)
        lines.append(f"## {table.fqdn}")
        lines.append(f"domains: {domain_label}")
        for col in table.columns:
            if col.type:
                lines.append(f"- {col.name} {col.type}")
            else:
                lines.append(f"- {col.name}")
        lines.append("")
    return "\n".join(lines)


def _yaml_declared_columns() -> dict[str, set[str]]:
    """Unqualified table name -> columns named in domain YAML (offline fallback)."""
    ident = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    out: dict[str, set[str]] = {}
    for path in sorted(DOMAINS_DIR.glob("*.yaml")):
        model = load_semantic_model(path)
        table_of = {e.name: e.table for e in model.entities}
        for entity in model.entities:
            short = entity.table.split(".")[-1].upper()
            out.setdefault(short, set())
            keys = entity.primary_key if isinstance(entity.primary_key, list) else [entity.primary_key]
            out[short].update(k.upper() for k in keys)
        for dim in model.dimensions:
            short = table_of[dim.entity].split(".")[-1].upper()
            out.setdefault(short, set()).add(dim.column.upper())
        for met in model.metrics:
            if ident.match(met.expression.strip()):
                short = table_of[met.entity].split(".")[-1].upper()
                out.setdefault(short, set()).add(met.expression.strip().upper())
        for rel in model.relationships:
            for ref in (rel.from_, rel.to):
                entity, _, col = ref.partition(".")
                if entity in table_of and col:
                    short = table_of[entity].split(".")[-1].upper()
                    out.setdefault(short, set()).add(col.upper())
        for cdk in model.cross_domain_keys:
            short = table_of[cdk.entity].split(".")[-1].upper()
            out.setdefault(short, set()).add(cdk.join_key.upper())
    return out


def catalog_from_yaml() -> list[CatalogTable]:
    declared = _yaml_declared_columns()
    tables: list[CatalogTable] = []
    for fqdn, domains in study_tables():
        short = fqdn.split(".")[-1].upper()
        columns = tuple(
            CatalogColumn(name=col, type="") for col in sorted(declared.get(short, set()))
        )
        tables.append(CatalogTable(fqdn=fqdn, domains=domains, columns=columns))
    return tables


def _snowflake_type_name(typ: str) -> str:
    """Map snowflake-connector type codes ('2') to names ('TEXT')."""
    if typ.isdigit():
        return FIELD_ID_TO_NAME.get(int(typ), typ)
    return typ


def catalog_from_live(executor) -> list[CatalogTable]:
    tables: list[CatalogTable] = []
    errors: list[str] = []
    for fqdn, domains in study_tables():
        result = executor.execute(f"SELECT * FROM {fqdn} LIMIT 0")
        if result.error:
            errors.append(f"{fqdn}: {result.error}")
            continue
        columns = tuple(
            CatalogColumn(name=name, type=_snowflake_type_name(typ))
            for name, typ in zip(result.columns, result.column_types or [""] * len(result.columns))
        )
        tables.append(CatalogTable(fqdn=fqdn, domains=domains, columns=columns))
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        raise SystemExit(1)
    return tables


def main() -> None:
    check_only = "--check" in sys.argv
    from_yaml = "--from-yaml" in sys.argv

    if from_yaml:
        tables = catalog_from_yaml()
        header = YAML_HEADER
    else:
        from agents.sql_executor import SqlExecutor

        executor = SqlExecutor()
        try:
            tables = catalog_from_live(executor)
        finally:
            executor.close()
        header = LIVE_HEADER

    new_content = render_schema_catalog(tables, header)

    if check_only:
        current_content = CATALOG_PATH.read_text() if CATALOG_PATH.exists() else ""
        if current_content != new_content:
            print(
                f"{CATALOG_PATH} is out of date. "
                "Run `python scripts/generate_schema_catalog.py` and commit the result.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        print("schema_catalog.md is up to date.")
        return

    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text(new_content)
    n_cols = sum(len(t.columns) for t in tables)
    source = "YAML-declared columns" if from_yaml else "live Snowflake columns"
    print(f"Wrote {CATALOG_PATH} ({len(tables)} tables, {n_cols} columns, {source}).")


if __name__ == "__main__":
    main()
