"""Shared per-domain tool building blocks for condition 3 (tool_routed).

Gives the agent one SQL-execution tool per domain plus a domain-scoped
get_semantic_model.
"""

from __future__ import annotations

from pathlib import Path

import yaml as pyyaml

from logging_.schema import RunLog
from semantic_models.schema import domain_table_names, raw_domain_model_text

REPO_ROOT = Path(__file__).resolve().parent.parent

with open(REPO_ROOT / "config" / "domains.yaml") as f:
    DOMAINS_CONFIG = pyyaml.safe_load(f)["domains"]

DOMAIN_NAMES = [d["name"] for d in DOMAINS_CONFIG]


def build_domain_query_tools() -> list[dict]:
    """One query_<domain> tool per domain, reusing config/domains.yaml's
    description text verbatim.
    """
    tools = []
    for d in DOMAINS_CONFIG:
        tools.append(
            {
                "name": f"query_{d['name']}",
                "description": (
                    f"{d['description'].strip()}\n\nExecutes a read-only SQL SELECT "
                    f"against ONLY this domain's tables. Call get_semantic_model('{d['name']}') "
                    "first if you haven't already seen this domain's schema in this "
                    "conversation. Cannot JOIN to tables outside this domain."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "sql": {
                            "type": "string",
                            "description": "A single SELECT (or WITH ... SELECT) statement against this domain's tables only.",
                        }
                    },
                    "required": ["sql"],
                },
            }
        )
    return tools


TOOL_GET_SEMANTIC_MODEL_BY_DOMAIN = {
    "name": "get_semantic_model",
    "description": (
        "Return the semantic model (entities, metrics, dimensions, relationships) "
        "for a domain. Call this before writing SQL against a domain you "
        "haven't queried yet in this conversation."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "enum": DOMAIN_NAMES,
                "description": "Which domain's schema to return.",
            }
        },
        "required": ["domain"],
    },
}


def _build_domain_semantic_models() -> dict[str, str]:
    return {name: raw_domain_model_text(name) for name in DOMAIN_NAMES}


def _build_domain_table_names() -> dict[str, set[str]]:
    return {name: domain_table_names(name) for name in DOMAIN_NAMES}


DOMAIN_SEMANTIC_MODELS = _build_domain_semantic_models()
DOMAIN_TABLE_NAMES = _build_domain_table_names()


def domains_visited(log: RunLog) -> list[str]:
    """Domains a run actually touched, derived from tool_calls.
    """
    seen: list[str] = []
    for tc in log.tool_calls:
        if tc.tool_name.startswith("query_"):
            domain = tc.tool_name[len("query_") :]
        elif tc.tool_name == "get_semantic_model":
            domain = tc.tool_input.get("domain")
        else:
            domain = None
        if domain and domain not in seen:
            seen.append(domain)
    return seen
