"""Domain coverage, derived from executed SQL. See eval/eval_strategies.md.

No LLM judge is involved. Coverage is computed from the tables the agent
actually queried, which is the only measurement that works identically across
all three conditions:

- `tool_routed` exposes domains through `query_<domain>` tool names, but
  `schema_only` and `unified` have no per-domain tool at all, so a
  tool-name metric would have to fall back to the agent's self-reported
  `domains_touched` footer for those conditions. Scoring conditions with
  two different instruments would confound measurement with architecture.
- The self-report is independently known to be unfaithful: live testing
  found an agent claiming `mortgage_lending` in its footer with no
  supporting content in the answer, and claiming `disaster_risk` on a
  question that never asked for it.

Coverage is a *diagnostic*: it explains why required facts were missed. It is
not a measure of answer quality, and must not be summed into the criterion
pass rate — calling every required domain while producing nothing useful still
counts as covered.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agents.sql_tables import referenced_tables  # noqa: E402
from semantic_models.schema import DOMAINS_DIR, domain_table_names  # noqa: E402


@lru_cache(maxsize=1)
def table_to_domain() -> dict[str, str]:
    """Map every fully-qualified table name to the domain that owns it.

    A table appearing in two domains (the bridge tables in
    `financial_institutions`, for instance) maps to whichever domain declares
    it first in sorted order — deterministic, and only affects attribution of
    a table both domains legitimately own.
    """
    mapping: dict[str, str] = {}
    for path in sorted(DOMAINS_DIR.glob("*.yaml")):
        domain = path.stem
        for table in domain_table_names(domain):
            mapping.setdefault(table, domain)
    return mapping


def domains_queried(generated_sql: list[str]) -> list[str]:
    """Domains touched by a run's executed SQL, in first-use order.

    Order is preserved (rather than returning a set) so a run's domain
    *sequence* stays inspectable — e.g. "deposits at query 1, geography at
    query 2, deposits again at query 4" — which is the signal that surfaced
    the wrong-domain-persistence failure mode in manual testing.
    """
    mapping = table_to_domain()
    seen: list[str] = []
    for sql in generated_sql:
        for table in sorted(referenced_tables(sql)):
            domain = mapping.get(table)
            if domain is not None and domain not in seen:
                seen.append(domain)
    return seen


def unmapped_tables(generated_sql: list[str]) -> set[str]:
    """Referenced tables that belong to no domain.

    Non-empty means either the semantic models are missing a table the agent
    found anyway, or table extraction picked up something that isn't a table. Either
    way it is worth surfacing rather than silently dropping, since both would
    understate coverage.
    """
    mapping = table_to_domain()
    return {t for sql in generated_sql for t in referenced_tables(sql) if t not in mapping}


@dataclass
class DomainCoverage:
    covered: bool
    minimum_required: list[str] = field(default_factory=list)
    domains_queried: list[str] = field(default_factory=list)
    missing_domains: list[str] = field(default_factory=list)
    extra_domains: list[str] = field(default_factory=list)
    unmapped_tables: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "covered": self.covered,
            "minimum_required": self.minimum_required,
            "domains_queried": self.domains_queried,
            "missing_domains": self.missing_domains,
            "extra_domains": self.extra_domains,
            "unmapped_tables": self.unmapped_tables,
        }


def compute_coverage(
    generated_sql: list[str],
    minimum_required: list[str],
    optional_enrichment: list[str] | None = None,
) -> DomainCoverage:
    optional_enrichment = optional_enrichment or []
    queried = domains_queried(generated_sql)
    missing = [d for d in minimum_required if d not in queried]
    extra = [d for d in queried if d not in minimum_required and d not in optional_enrichment]
    return DomainCoverage(
        covered=not missing,
        minimum_required=list(minimum_required),
        domains_queried=queried,
        missing_domains=missing,
        extra_domains=extra,
        unmapped_tables=sorted(unmapped_tables(generated_sql)),
    )
