#!/usr/bin/env python
"""Orchestrates a full eval run: both agents x N trials x the question bank,
ground-truth SQL diffing for category 1, LLM-judge scoring for categories
2/3, and a comparison table. See plan §7 and §8.

Run:
    python -m eval.run_eval                 # full question bank
    python -m eval.run_eval --pilot 5        # first 5 questions only (M3 exit criteria)

Requires ANTHROPIC_API_KEY and the SNOWFLAKE_* env vars (see .env.example).
Not runnable in this environment — no live credentials were available when
this was written; see PLAN.md Implementation status.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agents import routed_agent, unified_agent  # noqa: E402
from agents.sql_executor import SqlExecutor  # noqa: E402
from eval.judge import judge_answer_median  # noqa: E402
from logging_.schema import RunLog  # noqa: E402
from logging_.sink import RunLogSink  # noqa: E402

QUESTIONS_DIR = Path(__file__).resolve().parent / "questions"
GROUND_TRUTH_DIR = Path(__file__).resolve().parent / "ground_truth"

with open(REPO_ROOT / "config" / "experiment.yaml") as f:
    EXPERIMENT_CONFIG = yaml.safe_load(f)


def load_question_bank() -> list[dict]:
    all_questions: list[dict] = []
    for path in sorted(QUESTIONS_DIR.glob("*.yaml")):
        with open(path) as f:
            data = yaml.safe_load(f)
        all_questions.extend(data.get("questions", []))
    return all_questions


def _normalize_rows(rows: list[tuple]) -> list[tuple]:
    def normalize_value(v):
        if isinstance(v, float):
            return round(v, 6)
        return v

    normalized = [tuple(normalize_value(v) for v in row) for row in rows]
    return sorted(normalized, key=lambda r: tuple(str(x) for x in r))


def compare_result_sets(agent_rows: list[tuple], reference_rows: list[tuple]) -> dict:
    a = _normalize_rows(agent_rows)
    r = _normalize_rows(reference_rows)
    return {
        "exact_match": a == r,
        "row_count_match": len(agent_rows) == len(reference_rows),
    }


def check_ground_truth(
    sql_executor: SqlExecutor, run_log: RunLog, ground_truth_sql_path: str
) -> dict:
    """Compare the agent's last executed SQL against the reference query.

    Uses the last statement the agent ran, on the assumption it's the one
    that produced the final answer. Not perfectly robust to agents that
    compute the answer from an earlier query and merely double-check with a
    later one — flagged here rather than silently assumed correct.
    """
    if not run_log.generated_sql:
        return {"exact_match": False, "row_count_match": False, "error": "agent generated no SQL"}

    agent_result = sql_executor.execute(run_log.generated_sql[-1])
    ref_path = REPO_ROOT / ground_truth_sql_path
    ref_result = sql_executor.execute(ref_path.read_text())

    if agent_result.error or ref_result.error:
        return {
            "exact_match": False,
            "row_count_match": False,
            "error": agent_result.error or ref_result.error,
        }

    return compare_result_sets(agent_result.rows, ref_result.rows)


def run_agents_interleaved(
    client: anthropic.Anthropic,
    sql_executor: SqlExecutor,
    questions: list[dict],
    n_trials: int,
    run_id_prefix: str,
) -> list[dict]:
    """Runs Experiment A then B for each (question, trial), interleaved by
    question rather than blocked by experiment — see plan §8 step 2."""
    sink_unified = RunLogSink(f"{run_id_prefix}-unified")
    sink_routed = RunLogSink(f"{run_id_prefix}-routed")

    records = []
    for q in questions:
        for trial in range(n_trials):
            log_a = unified_agent.answer_question(
                client=client,
                sql_executor=sql_executor,
                question_id=q["id"],
                question_category=q["category"],
                question_text=q["text"],
                trial_index=trial,
                run_id=sink_unified.run_id,
            )
            sink_unified.write(log_a)

            log_b = routed_agent.answer_question(
                client=client,
                sql_executor=sql_executor,
                question_id=q["id"],
                question_category=q["category"],
                question_text=q["text"],
                trial_index=trial,
                run_id=sink_routed.run_id,
            )
            sink_routed.write(log_b)

            records.append({"question": q, "trial": trial, "unified": log_a, "routed": log_b})

    return records


def score_records(client: anthropic.Anthropic, sql_executor: SqlExecutor, records: list[dict]) -> list[dict]:
    for rec in records:
        q = rec["question"]
        category = q["category"]

        for condition in ("unified", "routed"):
            log: RunLog = rec[condition]

            if category == "single_domain" and q.get("ground_truth_sql_path"):
                rec[f"{condition}_ground_truth"] = check_ground_truth(
                    sql_executor, log, q["ground_truth_sql_path"]
                )

            median_scores, _ = judge_answer_median(
                client, q["text"], log.final_answer_text, category
            )
            rec[f"{condition}_judge_scores"] = median_scores

    return records


def aggregate(records: list[dict]) -> dict:
    summary: dict = {"unified": {}, "routed": {}}

    for condition in ("unified", "routed"):
        exact_matches = [
            r[f"{condition}_ground_truth"]["exact_match"]
            for r in records
            if f"{condition}_ground_truth" in r
        ]
        row_matches = [
            r[f"{condition}_ground_truth"]["row_count_match"]
            for r in records
            if f"{condition}_ground_truth" in r
        ]

        judge_dims: dict[str, list[float]] = {}
        for r in records:
            for dim, score in r.get(f"{condition}_judge_scores", {}).items():
                judge_dims.setdefault(dim, []).append(score)

        routing_accuracy = None
        if condition == "routed":
            correct = 0
            total = 0
            for r in records:
                q = r["question"]
                min_required = set(q.get("expected_domains", {}).get("minimum_required", []))
                if not min_required:
                    continue
                total += 1
                routed_domains = set(r["routed"].routing_decision.domains)
                if min_required.issubset(routed_domains):
                    correct += 1
            routing_accuracy = correct / total if total else None

        total_input_tokens = sum(r[condition].total_input_tokens for r in records)
        total_output_tokens = sum(r[condition].total_output_tokens for r in records)
        total_wall_clock_ms = sum(r[condition].wall_clock_ms for r in records)
        hit_cap_count = sum(1 for r in records if r[condition].hit_iteration_cap)

        summary[condition] = {
            "n_questions": len(records),
            "sql_exact_match_rate": statistics.mean(exact_matches) if exact_matches else None,
            "sql_row_count_match_rate": statistics.mean(row_matches) if row_matches else None,
            "routing_accuracy": routing_accuracy,
            "mean_judge_scores": {
                dim: statistics.mean(scores) for dim, scores in judge_dims.items()
            },
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_wall_clock_ms": total_wall_clock_ms,
            "hit_iteration_cap_count": hit_cap_count,
        }

    return summary


def write_summary_csv(summary: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "unified", "routed"])
        for key in summary["unified"]:
            u_val = summary["unified"][key]
            r_val = summary["routed"][key]
            writer.writerow([key, u_val, r_val])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pilot", type=int, default=None, help="Run only the first N questions (M3 pilot)."
    )
    args = parser.parse_args()

    questions = load_question_bank()
    if args.pilot:
        questions = questions[: args.pilot]

    client = anthropic.Anthropic()
    sql_executor = SqlExecutor(
        max_rows_returned=EXPERIMENT_CONFIG["sql_executor"]["max_rows_returned"],
        query_timeout_seconds=EXPERIMENT_CONFIG["sql_executor"]["query_timeout_seconds"],
    )

    run_id_prefix = f"eval-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
    n_trials = EXPERIMENT_CONFIG["trials"]["n_agent_trials_per_question"]

    print(f"Running {len(questions)} questions x {n_trials} trials x 2 experiments...")
    records = run_agents_interleaved(client, sql_executor, questions, n_trials, run_id_prefix)

    print("Scoring (ground truth + judge)...")
    records = score_records(client, sql_executor, records)

    summary = aggregate(records)
    summary_path = REPO_ROOT / "runs" / f"{run_id_prefix}-summary.csv"
    write_summary_csv(summary, summary_path)

    print(f"\nWrote summary to {summary_path}")
    for condition in ("unified", "routed"):
        print(f"\n{condition}:")
        for key, val in summary[condition].items():
            print(f"  {key}: {val}")

    sql_executor.close()


if __name__ == "__main__":
    main()
