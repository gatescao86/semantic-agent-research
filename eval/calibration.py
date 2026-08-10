"""Judge-vs-human calibration check. See plan §7.

Since the judge runs at the same model tier as the answering agents (the
user's explicit choice — cheaper, but higher self-preference-bias risk than
a stronger-tier judge), this calibration check is the primary safeguard
against that bias, not an optional nice-to-have. Do not trust judge-only
scoring on the full run unless agreement clears the pre-registered
threshold in config/experiment.yaml (`judge.calibration_kappa_threshold`,
default 0.6).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml
from scipy.stats import spearmanr
from sklearn.metrics import cohen_kappa_score

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

with open(REPO_ROOT / "config" / "experiment.yaml") as f:
    EXPERIMENT_CONFIG = yaml.safe_load(f)


@dataclass
class AgreementResult:
    n: int
    weighted_kappa: float
    spearman_rho: float
    spearman_p: float
    threshold: float
    meets_threshold: bool


def compute_agreement(judge_scores: list[int], human_scores: list[int]) -> AgreementResult:
    if len(judge_scores) != len(human_scores):
        raise ValueError(
            f"judge_scores ({len(judge_scores)}) and human_scores "
            f"({len(human_scores)}) must be the same length and paired by index."
        )
    if len(judge_scores) < 2:
        raise ValueError("Need at least 2 paired scores to compute agreement.")

    threshold = EXPERIMENT_CONFIG["judge"]["calibration_kappa_threshold"]
    kappa = cohen_kappa_score(judge_scores, human_scores, weights="linear")
    rho, p_value = spearmanr(judge_scores, human_scores)

    return AgreementResult(
        n=len(judge_scores),
        weighted_kappa=kappa,
        spearman_rho=rho,
        spearman_p=p_value,
        threshold=threshold,
        meets_threshold=kappa >= threshold,
    )


def load_paired_scores(path: str | Path) -> tuple[list[int], list[int]]:
    """Load a JSON file shaped {"judge_scores": [...], "human_scores": [...]}.

    Both lists must be paired by index (same question, same dimension, in
    the same order) — see plan §7 for the calibration sampling procedure
    (stratified ~20% subset across categories and both conditions).
    """
    with open(path) as f:
        data = json.load(f)
    return data["judge_scores"], data["human_scores"]


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: python -m eval.calibration <paired_scores.json>\n"
            '  where paired_scores.json is {"judge_scores": [...], "human_scores": [...]}',
            file=sys.stderr,
        )
        raise SystemExit(1)

    judge_scores, human_scores = load_paired_scores(sys.argv[1])
    result = compute_agreement(judge_scores, human_scores)

    print(f"n = {result.n}")
    print(f"weighted kappa = {result.weighted_kappa:.3f} (threshold: {result.threshold})")
    print(f"spearman rho = {result.spearman_rho:.3f} (p = {result.spearman_p:.4f})")
    print(f"meets threshold: {result.meets_threshold}")

    if not result.meets_threshold:
        print(
            "\nDo NOT proceed to judge-only scoring on the full run. "
            "Revise the rubric (eval/judge_rubric.md) and recalibrate first.",
            file=sys.stderr,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
