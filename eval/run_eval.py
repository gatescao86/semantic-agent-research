#!/usr/bin/env python
"""Orchestrates a full eval run of the three conditions: schema_only,
unified, and tool_routed. Interleaves conditions per (question, trial),
scores criteria, and writes a cost/latency/accuracy summary.

Run:
    python -m eval.run_eval                 # full question bank
    python -m eval.run_eval --pilot 5        # first 5 questions only

Requires ANTHROPIC_API_KEY and the SNOWFLAKE_* env vars (see .env.example).
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agents import schema_only_agent, tool_router_agent, unified_agent  # noqa: E402
from agents.sql_executor import SqlExecutor  # noqa: E402
from analysis.aggregate_results import estimate_cost_usd  # noqa: E402
from eval.criteria import parse_criteria  # noqa: E402
from eval.domain_coverage import compute_coverage  # noqa: E402
from eval.failure_report import write_failure_report  # noqa: E402
from eval.judge import EXPERIMENT_CONFIG as EVAL_CONFIG  # noqa: E402
from eval.question_bank import agent_question_text, load_question_bank  # noqa: E402
from eval.scoring import score_answer  # noqa: E402
from logging_.schema import RunLog  # noqa: E402
from logging_.sink import RunLogSink  # noqa: E402

with open(REPO_ROOT / "config" / "experiment.yaml") as f:
    EXPERIMENT_CONFIG = yaml.safe_load(f)

PRIMARY_CONDITIONS = ("schema_only", "unified", "tool_routed")

_AGENTS = {
    "schema_only": schema_only_agent.answer_question,
    "unified": unified_agent.answer_question,
    "tool_routed": tool_router_agent.answer_question,
}


def run_agents_interleaved(
    client: anthropic.Anthropic,
    sql_executor: SqlExecutor,
    questions: list[dict],
    n_trials: int,
    run_id_prefix: str,
) -> list[dict]:
    """Runs the three conditions for each (question, trial), interleaved
    by question rather than blocked by condition."""
    sinks = {c: RunLogSink(f"{run_id_prefix}-{c}") for c in PRIMARY_CONDITIONS}

    records = []
    for q in questions:
        for trial in range(n_trials):
            rec: dict = {"question": q, "trial": trial}
            for condition in PRIMARY_CONDITIONS:
                print(
                    f"[{condition}] {q['id']} trial {trial} …",
                    flush=True,
                )
                log = _AGENTS[condition](
                    client=client,
                    sql_executor=sql_executor,
                    question_id=q["id"],
                    question_category=q["category"],
                    question_text=agent_question_text(q),
                    trial_index=trial,
                    run_id=sinks[condition].run_id,
                )
                sinks[condition].write(log)
                rec[condition] = log
                print(
                    f"[{condition}] {q['id']} trial {trial} done "
                    f"({log.wall_clock_ms} ms, {len(log.tool_calls)} tools, "
                    f"{log.total_input_tokens}+{log.total_output_tokens} tok)",
                    flush=True,
                )
            records.append(rec)

    return records


def score_records(client: anthropic.Anthropic, records: list[dict]) -> list[dict]:
    for rec in records:
        q = rec["question"]

        for condition in PRIMARY_CONDITIONS:
            log: RunLog = rec[condition]

            criteria = parse_criteria(
                q, default_tolerance=EVAL_CONFIG.get("scoring", {}).get("default_tolerance")
            )
            if not criteria:
                continue

            expected = q.get("expected_domains") or {}
            coverage = compute_coverage(
                log.generated_sql,
                expected.get("minimum_required", []),
                expected.get("optional_enrichment", []),
            )
            score = score_answer(
                client,
                q,
                criteria,
                log.model_dump(),
                domain_coverage=coverage.to_dict(),
                judge_model=EVAL_CONFIG["judge"]["model_id"],
            )
            rec[f"{condition}_score"] = score.to_dict()
            scores_path = REPO_ROOT / "runs" / f"{log.run_id}-scores.json"
            scores_path.write_text(json.dumps(score.to_dict(), indent=2))

    return records


def _mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def aggregate(records: list[dict]) -> dict:
    summary: dict = {}

    for condition in PRIMARY_CONDITIONS:
        logs = [r[condition] for r in records]
        scores = [r[f"{condition}_score"] for r in records if f"{condition}_score" in r]

        n_passed = sum(s["n_passed"] for s in scores)
        n_criteria = sum(s["n_criteria"] for s in scores)
        pass_rates = [s["criterion_pass_rate"] for s in scores]
        all_pass = [s["all_pass"] for s in scores]

        total_input = sum(log.total_input_tokens for log in logs)
        total_output = sum(log.total_output_tokens for log in logs)
        total_cache_read = sum(log.total_cache_read_tokens for log in logs)
        total_cache_creation = sum(log.total_cache_creation_tokens for log in logs)
        cost = estimate_cost_usd(total_input, total_output, total_cache_read, total_cache_creation)
        wall = [log.wall_clock_ms for log in logs]

        summary[condition] = {
            "n_questions": len(records),
            "criterion_pass_rate_pooled": (n_passed / n_criteria) if n_criteria else None,
            "criterion_pass_rate_macro": _mean(pass_rates),
            "all_pass_rate": _mean([1.0 if v else 0.0 for v in all_pass]),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cache_read_tokens": total_cache_read,
            "total_cache_creation_tokens": total_cache_creation,
            "estimated_cost_usd": round(cost, 4),
            "cost_per_question_usd": round(cost / len(logs), 4) if logs else None,
            "total_wall_clock_ms": sum(wall),
            "mean_wall_clock_ms": _mean(wall),
            "hit_iteration_cap_count": sum(1 for log in logs if log.hit_iteration_cap),
            "mean_tool_calls_per_run": _mean([len(log.tool_calls) for log in logs]),
        }

    return summary


def write_summary_csv(summary: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", *PRIMARY_CONDITIONS])
        first = PRIMARY_CONDITIONS[0]
        for key in summary[first]:
            writer.writerow([key, *[summary[c][key] for c in PRIMARY_CONDITIONS]])


def select_questions(
    bank: list[dict],
    question_ids: list[str] | None,
    pilot: int | None,
) -> list[dict]:
    if question_ids and pilot is not None:
        raise SystemExit("Use --question or --pilot, not both.")
    if question_ids:
        by_id = {q["id"]: q for q in bank}
        missing = [qid for qid in question_ids if qid not in by_id]
        if missing:
            raise SystemExit(
                f"Unknown question id(s): {missing}. Available: {sorted(by_id)}"
            )
        return [by_id[qid] for qid in question_ids]
    if pilot is not None:
        return bank[:pilot]
    return bank


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pilot", type=int, default=None, help="Run only the first N questions."
    )
    parser.add_argument(
        "--question",
        action="append",
        dest="question_ids",
        help="Run only this question id (repeatable).",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=None,
        help="Override n_agent_trials_per_question from experiment.yaml.",
    )
    args = parser.parse_args()

    questions = select_questions(load_question_bank(), args.question_ids, args.pilot)

    load_dotenv(REPO_ROOT / ".env")
    client = anthropic.Anthropic()
    sql_executor = SqlExecutor(
        max_rows_returned=EXPERIMENT_CONFIG["sql_executor"]["max_rows_returned"],
        query_timeout_seconds=EXPERIMENT_CONFIG["sql_executor"]["query_timeout_seconds"],
    )

    run_id_prefix = f"eval-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
    n_trials = args.trials if args.trials is not None else EXPERIMENT_CONFIG["trials"]["n_agent_trials_per_question"]

    print(
        f"Running {len(questions)} questions x {n_trials} trials x "
        f"{' vs '.join(PRIMARY_CONDITIONS)}..."
    )
    records = run_agents_interleaved(client, sql_executor, questions, n_trials, run_id_prefix)

    print("Scoring (judge + numeric tolerance)...")
    records = score_records(client, records)

    summary = aggregate(records)
    summary_path = REPO_ROOT / "runs" / f"{run_id_prefix}-summary.csv"
    write_summary_csv(summary, summary_path)
    report_path = REPO_ROOT / "runs" / f"{run_id_prefix}-failure-report.md"
    report = write_failure_report(records, report_path)

    print(f"\nWrote summary to {summary_path}")
    print(f"Wrote failure report to {report_path}")
    for condition in PRIMARY_CONDITIONS:
        print(f"\n{condition}:")
        for key, val in summary[condition].items():
            print(f"  {key}: {val}")
    print("\n" + report)

    sql_executor.close()


if __name__ == "__main__":
    main()
