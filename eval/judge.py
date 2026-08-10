"""LLM-as-judge harness. See plan §7 and eval/judge_rubric.md.

Blinded: the judge sees only the question and answer text, never which
system (unified/routed) or experiment produced it — reduces self-preference
and expectation bias, on top of the human-calibration check in
eval/calibration.py.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import anthropic
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

RUBRIC_TEXT = (Path(__file__).resolve().parent / "judge_rubric.md").read_text()

with open(REPO_ROOT / "config" / "experiment.yaml") as f:
    EXPERIMENT_CONFIG = yaml.safe_load(f)

QuestionCategory = Literal["single_domain", "cross_domain", "executive"]

DIMENSIONS_BY_CATEGORY: dict[QuestionCategory, list[str]] = {
    "single_domain": ["correctness"],
    "cross_domain": ["domain_coverage", "reasoning_quality", "synthesis_genuineness"],
    "executive": ["completeness", "usefulness", "synthesis", "actionability"],
}

JUDGE_SYSTEM_PROMPT = f"""You are a blinded evaluator scoring an AI assistant's answer to a business
data question. You do not know and must not guess which system produced the
answer. Score strictly against the rubric below.

{RUBRIC_TEXT}
"""


@dataclass
class JudgeScore:
    category: QuestionCategory
    dimension_scores: dict[str, int] = field(default_factory=dict)
    justification: str = ""
    latency_ms: int = 0
    request_id: str | None = None


def _build_output_schema(dimensions: list[str]) -> dict:
    properties = {
        dim: {"type": "integer", "minimum": 1, "maximum": 5} for dim in dimensions
    }
    properties["justification"] = {"type": "string"}
    return {
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": properties,
            "required": [*dimensions, "justification"],
            "additionalProperties": False,
        },
    }


def judge_answer(
    client: anthropic.Anthropic,
    question_text: str,
    answer_text: str,
    category: QuestionCategory,
) -> JudgeScore:
    dimensions = DIMENSIONS_BY_CATEGORY[category]
    user_content = (
        f"Question category: {category}\n\n"
        f"Question:\n{question_text}\n\n"
        f"Answer to evaluate:\n{answer_text}\n\n"
        f"Score this answer on: {', '.join(dimensions)}."
    )

    start = time.monotonic()
    with client.messages.stream(
        model=EXPERIMENT_CONFIG["judge"]["model_id"],
        max_tokens=1024,
        system=JUDGE_SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium", "format": _build_output_schema(dimensions)},
        messages=[{"role": "user", "content": user_content}],
    ) as stream:
        response = stream.get_final_message()
    latency_ms = int((time.monotonic() - start) * 1000)

    if response.stop_reason == "refusal":
        return JudgeScore(
            category=category,
            dimension_scores={d: 0 for d in dimensions},
            justification="Judge call was refused by safety classifiers.",
            latency_ms=latency_ms,
            request_id=response._request_id,
        )

    text = next((b.text for b in response.content if b.type == "text"), "{}")
    parsed = json.loads(text)

    return JudgeScore(
        category=category,
        dimension_scores={d: parsed[d] for d in dimensions},
        justification=parsed.get("justification", ""),
        latency_ms=latency_ms,
        request_id=response._request_id,
    )


def judge_answer_median(
    client: anthropic.Anthropic,
    question_text: str,
    answer_text: str,
    category: QuestionCategory,
    n_calls: int | None = None,
) -> tuple[dict[str, float], list[JudgeScore]]:
    """Run the judge n_calls times and take the per-dimension median.

    Averages out judge non-determinism (separate from the agent's own
    n_agent_trials) — see plan §7.
    """
    n_calls = n_calls or EXPERIMENT_CONFIG["trials"]["n_judge_calls_per_answer"]
    scores = [judge_answer(client, question_text, answer_text, category) for _ in range(n_calls)]

    dimensions = DIMENSIONS_BY_CATEGORY[category]
    median_scores = {
        dim: statistics.median(s.dimension_scores[dim] for s in scores) for dim in dimensions
    }
    return median_scores, scores
