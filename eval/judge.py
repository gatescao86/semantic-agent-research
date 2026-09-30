"""LLM-as-judge harness.

The judge is an *extractor*, not an evaluator. It answers one question about
one criterion — is this fact present, and if the criterion is numeric, what
number does the answer state? Every comparison against an expected value
happens in eval/scoring.py, in code. 

Blinded: the judge sees the question, the answer text, and one criterion. It is
never shown generated SQL, tool calls, or which condition produced the answer.
"""

from __future__ import annotations

import json
import re
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import anthropic
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eval.criteria import FAIL, PASS, Criterion  # noqa: E402

SPEC_PATH = Path(__file__).resolve().parent / "eval_strategies.md"

with open(REPO_ROOT / "config" / "experiment.yaml") as f:
    EXPERIMENT_CONFIG = yaml.safe_load(f)

# thinking: adaptive consumes budget regardless of how short the output is.
# Sizing max_tokens from expected output length has truncated structured output
# mid-JSON three times in this project (PLAN bugs #4, #7, #9).
JUDGE_MAX_TOKENS = EXPERIMENT_CONFIG["judge"].get("max_tokens", 8000)


def _load_judge_instructions() -> str:
    """Extract only the `### Judge Instructions` section from the spec.

    The spec file also covers aggregation, validity gates, and known
    limitations — none of which the judge should see. Injecting the whole file
    would tell it, among other things, that this project considers its own
    judge to carry self-preference risk.
    """
    text = SPEC_PATH.read_text()
    match = re.search(
        r"^### Judge Instructions\s*\n(.*?)(?=^#{2,3} |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise RuntimeError(f"No '### Judge Instructions' section found in {SPEC_PATH}")
    body = match.group(1)
    # Drop the italic editorial note addressed to readers of the spec, not the judge.
    body = re.sub(r"^\*.*?\*\s*$", "", body, flags=re.MULTILINE | re.DOTALL)
    return body.strip()


JUDGE_INSTRUCTIONS = _load_judge_instructions()

JUDGE_SYSTEM_PROMPT = f"""You are a blinded evaluator checking whether one specific criterion is
satisfied by an AI agent's answer to a question. You do not
know and must not guess which system produced the answer.

{JUDGE_INSTRUCTIONS}
"""


DEFAULT_JUDGE_MODEL = EXPERIMENT_CONFIG["judge"]["model_id"]


@dataclass
class CriterionVerdict:
    criterion_id: str
    verdict: str  # PASS | FAIL
    claimed_value: float | None = None
    reasoning: str = ""
    latency_ms: int = 0
    request_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def passed(self) -> bool:
        return self.verdict == PASS


def _output_schema(numeric: bool) -> dict:
    properties: dict = {
        "reasoning": {"type": "string"},
        "verdict": {"type": "string", "enum": [PASS, FAIL]},
    }
    required = ["reasoning", "verdict"]
    if numeric:
        properties["claimed_value"] = {"type": ["number", "null"]}
        required.append("claimed_value")
    return {
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


def build_user_content(question_text: str, answer_text: str, criterion: Criterion) -> str:
    """Pure/testable — no API call."""
    lines = [
        f"Question:\n{question_text}",
        f"Answer to evaluate:\n{answer_text}",
        f"Criterion to check:\n{criterion.match_criteria}",
    ]
    if criterion.is_numeric:
        lines.append(
            f"This criterion is numeric. Return verdict PASS if the answer states the "
            f"quantity the criterion asks for, FAIL if it does not. Report "
            f"`claimed_value` as that number converted to {criterion.unit}, or null if "
            f"the answer states no number for it. Do not judge whether the number is "
            f"correct — that comparison is made outside this call."
        )
    return "\n\n".join(lines)


def judge_criterion(
    client: anthropic.Anthropic,
    question_text: str,
    answer_text: str,
    criterion: Criterion,
    model: str | None = None,
) -> CriterionVerdict:
    user_content = build_user_content(question_text, answer_text, criterion)

    start = time.monotonic()
    with client.messages.stream(
        model=model or DEFAULT_JUDGE_MODEL,
        max_tokens=JUDGE_MAX_TOKENS,
        system=JUDGE_SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium", "format": _output_schema(criterion.is_numeric)},
        messages=[{"role": "user", "content": user_content}],
    ) as stream:
        response = stream.get_final_message()
        request_id = stream.request_id
    latency_ms = int((time.monotonic() - start) * 1000)

    usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}

    if response.stop_reason == "refusal":
        return CriterionVerdict(
            criterion_id=criterion.id,
            verdict=FAIL,
            reasoning="Judge call was refused by safety classifiers.",
            latency_ms=latency_ms,
            request_id=request_id,
            **usage,
        )

    text = next((b.text for b in response.content if b.type == "text"), "{}")
    parsed = json.loads(text)
    raw_verdict = str(parsed.get("verdict", FAIL)).upper()
    verdict = PASS if raw_verdict == PASS else FAIL

    return CriterionVerdict(
        criterion_id=criterion.id,
        verdict=verdict,
        claimed_value=parsed.get("claimed_value"),
        reasoning=parsed.get("reasoning", ""),
        latency_ms=latency_ms,
        request_id=request_id,
        **usage,
    )


def judge_criterion_majority(
    client: anthropic.Anthropic,
    question_text: str,
    answer_text: str,
    criterion: Criterion,
    n_calls: int | None = None,
    model: str | None = None,
) -> tuple[CriterionVerdict, list[CriterionVerdict], bool]:
    """Run the judge n_calls times; majority vote on PASS/FAIL, median of
    non-null `claimed_value`s.
    """
    n_calls = n_calls or EXPERIMENT_CONFIG["trials"]["n_judge_calls_per_answer"]
    verdicts = [
        judge_criterion(client, question_text, answer_text, criterion, model=model)
        for _ in range(n_calls)
    ]

    votes = [v.passed for v in verdicts]
    passed = sum(votes) * 2 > len(votes)
    was_split = 0 < sum(votes) < len(votes)

    values = [v.claimed_value for v in verdicts if v.claimed_value is not None]
    claimed_value = statistics.median(values) if values else None

    consensus = CriterionVerdict(
        criterion_id=criterion.id,
        verdict=PASS if passed else FAIL,
        claimed_value=claimed_value,
        reasoning=next((v.reasoning for v in verdicts if v.passed == passed), verdicts[0].reasoning),
        latency_ms=sum(v.latency_ms for v in verdicts),
        request_id=verdicts[0].request_id,
        input_tokens=sum(v.input_tokens for v in verdicts),
        output_tokens=sum(v.output_tokens for v in verdicts),
    )
    return consensus, verdicts, was_split
