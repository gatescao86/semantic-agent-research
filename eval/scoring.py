"""Answer scoring. See eval/eval_strategies.md § Scoring Details.

Every criterion produces one binary verdict (`PASS` or `FAIL`). The judge
supplies that verdict and, for numeric criteria, the number the answer
states; tolerance comparison happens here.
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eval.criteria import FAIL, PASS, Criterion  # noqa: E402
from eval.judge import DEFAULT_JUDGE_MODEL, judge_criterion_majority  # noqa: E402
from eval.question_bank import agent_question_text  # noqa: E402

SPEC_VERSION = 2


def within_tolerance(
    claimed: float,
    expected: float,
    tolerance: float | None,
    tolerance_abs: float | None,
) -> bool:
    if tolerance_abs is not None:
        return abs(claimed - expected) <= tolerance_abs
    if tolerance is not None:
        return abs(claimed - expected) <= tolerance * abs(expected)
    return claimed == expected


@dataclass
class CriterionResult:
    id: str
    match_criteria: str
    verdict: str  # PASS | FAIL
    failure_reason: str | None = None  # "absent" | "numeric_mismatch" | "no_value_stated"
    claimed_value: float | None = None
    expected_value: float | None = None
    unit: str | None = None
    split_vote: bool = False
    reasoning: str = ""
    judge_input_tokens: int = 0
    judge_output_tokens: int = 0

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "match_criteria": self.match_criteria,
            "verdict": self.verdict,
            "reasoning": self.reasoning,
        }
        if self.failure_reason:
            d["failure_reason"] = self.failure_reason
        if self.expected_value is not None:
            d |= {
                "claimed_value": self.claimed_value,
                "expected_value": self.expected_value,
                "unit": self.unit,
            }
        if self.split_vote:
            d["split_vote"] = True
        return d


@dataclass
class AnswerScore:
    run_id: str
    question_id: str
    category: str
    condition: str
    trial: int
    criteria_results: list[CriterionResult] = field(default_factory=list)
    domain_coverage: dict | None = None
    judge_model: str = ""
    spec_version: int = SPEC_VERSION

    @property
    def n_criteria(self) -> int:
        return len(self.criteria_results)

    @property
    def n_passed(self) -> int:
        return sum(1 for r in self.criteria_results if r.verdict == PASS)

    @property
    def criterion_pass_rate(self) -> float:
        return self.n_passed / self.n_criteria if self.n_criteria else 0.0

    @property
    def all_pass(self) -> bool:
        return self.n_criteria > 0 and self.n_passed == self.n_criteria

    @property
    def judge_tokens(self) -> dict[str, int]:
        return {
            "input": sum(r.judge_input_tokens for r in self.criteria_results),
            "output": sum(r.judge_output_tokens for r in self.criteria_results),
        }

    def summary(self) -> str:
        reasons: dict[str, int] = {}
        for r in self.criteria_results:
            if r.verdict == FAIL and r.failure_reason:
                reasons[r.failure_reason] = reasons.get(r.failure_reason, 0) + 1
        detail = ", ".join(f"{n} {reason}" for reason, n in sorted(reasons.items()))
        base = f"{self.n_passed}/{self.n_criteria} criteria passed"
        return f"{base} — {detail}." if detail else f"{base}."

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "question_id": self.question_id,
            "category": self.category,
            "condition": self.condition,
            "trial": self.trial,
            "spec_version": self.spec_version,
            "criterion_pass_rate": round(self.criterion_pass_rate, 4),
            "n_criteria": self.n_criteria,
            "n_passed": self.n_passed,
            "all_pass": self.all_pass,
            "summary": self.summary(),
            "criteria_results": [r.to_dict() for r in self.criteria_results],
            "domain_coverage": self.domain_coverage,
            "judge_model": self.judge_model,
            "judge_tokens": self.judge_tokens,
        }


def score_criterion(
    client: anthropic.Anthropic,
    question_text: str,
    answer_text: str,
    criterion: Criterion,
    n_calls: int | None = None,
    model: str | None = None,
) -> CriterionResult:
    consensus, _, was_split = judge_criterion_majority(
        client, question_text, answer_text, criterion, n_calls=n_calls, model=model
    )

    result = CriterionResult(
        id=criterion.id,
        match_criteria=criterion.match_criteria,
        verdict=FAIL,
        claimed_value=consensus.claimed_value,
        expected_value=criterion.value,
        unit=criterion.unit,
        split_vote=was_split,
        reasoning=consensus.reasoning,
        judge_input_tokens=consensus.input_tokens,
        judge_output_tokens=consensus.output_tokens,
    )

    if not consensus.passed:
        result.failure_reason = "absent"
        return result

    if not criterion.is_numeric:
        result.verdict = PASS
        return result

    if consensus.claimed_value is None:
        result.failure_reason = "no_value_stated"
        return result

    if within_tolerance(
        consensus.claimed_value, criterion.value, criterion.tolerance, criterion.tolerance_abs
    ):
        result.verdict = PASS
    else:
        result.failure_reason = "numeric_mismatch"
    return result


def score_answer(
    client: anthropic.Anthropic,
    question: dict,
    criteria: list[Criterion],
    run_log: dict,
    domain_coverage: dict | None = None,
    judge_model: str | None = None,
    n_calls: int | None = None,
    max_workers: int = 6,
) -> AnswerScore:
    judge_model = judge_model or DEFAULT_JUDGE_MODEL
    answer_text = run_log.get("final_answer_text", "")

    # Score criteria in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                score_criterion,
                client,
                agent_question_text(question),
                answer_text,
                c,
                n_calls,
                judge_model,
            ): c.id
            for c in criteria
        }
        by_id = {futures[f]: f.result() for f in as_completed(futures)}
    results = [by_id[c.id] for c in criteria]

    return AnswerScore(
        run_id=run_log.get("run_id", ""),
        question_id=question.get("id", ""),
        category=question.get("category", ""),
        condition=run_log.get("experiment", ""),
        trial=run_log.get("trial_index", 0),
        criteria_results=results,
        domain_coverage=domain_coverage,
        judge_model=judge_model,
    )
