"""Experiment B's domain router — LLM classification, not keyword/embedding.

Rationale (plan §5): the research question is about architectural tradeoffs
of decomposition, not routing-infrastructure quality. An LLM router keeps
"routing failure" attributable to genuine domain ambiguity rather than a
second uncontrolled variable (embedding/keyword routing quality), and its
reasoning is auditable text rather than an opaque similarity score.

Uses the same model as the answering agents (so routing failures can't be
blamed on a deliberately weaker router model) at a lower effort level, since
classification is a simpler task than SQL generation — this is a separate,
router-only knob, not a violation of "pin effort across conditions" (that
rule governs the shared answering-agent loop, which has no router in
Experiment A to compare against).
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import anthropic
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
ROUTER_SYSTEM_TEMPLATE = (PROMPTS_DIR / "router_system.md").read_text()

with open(REPO_ROOT / "config" / "domains.yaml") as f:
    DOMAINS_CONFIG = yaml.safe_load(f)

with open(REPO_ROOT / "config" / "experiment.yaml") as f:
    EXPERIMENT_CONFIG = yaml.safe_load(f)

DOMAIN_NAMES = [d["name"] for d in DOMAINS_CONFIG["domains"]]

ROUTER_EFFORT = "low"


@dataclass
class RouterDecision:
    domains: list[str] = field(default_factory=list)
    reasoning: str = ""
    ambiguous: bool = False
    latency_ms: int = 0
    request_id: str | None = None


def _build_domain_list_text() -> str:
    lines = []
    for d in DOMAINS_CONFIG["domains"]:
        lines.append(f"- **{d['router_label']}**: {d['description'].strip()}")
    return "\n".join(lines)


def _build_output_schema() -> dict:
    return {
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": {
                "domains": {
                    "type": "array",
                    "items": {"type": "string", "enum": DOMAIN_NAMES},
                },
                "reasoning": {"type": "string"},
                "ambiguous": {"type": "boolean"},
            },
            "required": ["domains", "reasoning", "ambiguous"],
            "additionalProperties": False,
        },
    }


def route_question(client: anthropic.Anthropic, question_text: str) -> RouterDecision:
    system_text = ROUTER_SYSTEM_TEMPLATE.replace("{domain_list}", _build_domain_list_text())

    start = time.monotonic()
    with client.messages.stream(
        model=EXPERIMENT_CONFIG["model"]["id"],
        max_tokens=1024,
        system=system_text,
        thinking={"type": "adaptive"},
        output_config={"effort": ROUTER_EFFORT, "format": _build_output_schema()},
        messages=[{"role": "user", "content": question_text}],
    ) as stream:
        response = stream.get_final_message()
    latency_ms = int((time.monotonic() - start) * 1000)

    if response.stop_reason == "refusal":
        return RouterDecision(
            domains=[],
            reasoning="Router call was refused by safety classifiers.",
            ambiguous=True,
            latency_ms=latency_ms,
            request_id=response._request_id,
        )

    text = next((b.text for b in response.content if b.type == "text"), "{}")
    parsed = json.loads(text)

    return RouterDecision(
        domains=parsed.get("domains", []),
        reasoning=parsed.get("reasoning", ""),
        ambiguous=parsed.get("ambiguous", False),
        latency_ms=latency_ms,
        request_id=response._request_id,
    )
