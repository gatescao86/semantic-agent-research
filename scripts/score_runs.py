"""Score existing RunLog files against a question's criteria.

Separate from eval/run_eval.py on purpose: run_eval executes agents *and*
scores them, which costs a full multi-minute agent run per condition. This
scores logs that already exist in runs/, so the eval framework can be
exercised and re-exercised against real answers without re-running agents.

    python -m scripts.score_runs --question ex-001 \\
        --runs runs/unified-analyst-manual-e11792ca.jsonl \\
               runs/decomposed-analyst-manual-0283beb1.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eval.criteria import parse_criteria  # noqa: E402
from eval.domain_coverage import compute_coverage  # noqa: E402
from eval.failure_report import PRIMARY_CONDITIONS, write_failure_report  # noqa: E402
from eval.judge import EXPERIMENT_CONFIG  # noqa: E402
from eval.question_bank import load_question  # noqa: E402
from eval.scoring import score_answer  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", required=True)
    parser.add_argument("--runs", nargs="+", required=True)
    parser.add_argument(
        "--n-calls",
        type=int,
        default=None,
        help="Judge calls per criterion (default: config trials.n_judge_calls_per_answer)",
    )
    parser.add_argument("--max-workers", type=int, default=6)
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env")
    client = anthropic.Anthropic()

    question = load_question(args.question)
    criteria = parse_criteria(
        question, default_tolerance=EXPERIMENT_CONFIG.get("scoring", {}).get("default_tolerance")
    )
    if not criteria:
        raise SystemExit(f"Question {args.question!r} has no criteria to score against.")

    expected = question.get("expected_domains") or {}
    scores = []
    record: dict = {"question": question, "trial": 0}

    for run_path in args.runs:
        run_log = json.loads(Path(run_path).read_text().strip().splitlines()[0])
        coverage = compute_coverage(
            run_log.get("generated_sql", []),
            expected.get("minimum_required", []),
            expected.get("optional_enrichment", []),
        )
        score = score_answer(
            client,
            question,
            criteria,
            run_log,
            domain_coverage=coverage.to_dict(),
            judge_model=EXPERIMENT_CONFIG["judge"]["model_id"],
            n_calls=args.n_calls,
            max_workers=args.max_workers,
        )
        out_path = REPO_ROOT / "runs" / f"{run_log['run_id']}-scores.json"
        out_path.write_text(json.dumps(score.to_dict(), indent=2))
        scores.append((score, out_path))
        record["trial"] = run_log.get("trial_index", 0)
        record[score.condition] = run_log
        record[f"{score.condition}_score"] = score.to_dict()
        print(f"{score.condition:22s} {score.summary()}  -> {out_path.name}")

    print()
    header = f"{'criterion':10s} " + " ".join(f"{s.condition[:20]:>22s}" for s, _ in scores)
    print(header)
    print("-" * len(header))
    for criterion in criteria:
        cells = []
        for score, _ in scores:
            result = next(r for r in score.criteria_results if r.id == criterion.id)
            mark = result.verdict
            detail = f" ({result.failure_reason})" if result.failure_reason else ""
            cells.append(f"{mark + detail:>22s}")
        print(f"{criterion.id:10s} " + " ".join(cells))

    print()
    for score, _ in scores:
        cov = score.domain_coverage or {}
        print(
            f"{score.condition:22s} pass_rate={score.criterion_pass_rate:.2f} "
            f"all_pass={score.all_pass} coverage={cov.get('covered')} "
            f"missing={cov.get('missing_domains')}"
        )

    present = tuple(c for c in PRIMARY_CONDITIONS if c in record)
    report_path = REPO_ROOT / "runs" / f"{question['id']}-failure-report.md"
    report = write_failure_report([record], report_path, conditions=present or PRIMARY_CONDITIONS)
    print(f"\nWrote failure report to {report_path}")
    print()
    print(report)


if __name__ == "__main__":
    main()
