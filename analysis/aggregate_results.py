#!/usr/bin/env python
"""Rolls up persisted JSONL run logs (runs/*.jsonl) into cost, latency, and
routing/failure-mode comparison tables between Experiment A (unified) and
Experiment B (routed). See plan §6/§8.

This is separate from eval/run_eval.py's live in-run summary: it operates
on logs already written to disk, so it can be re-run against past runs
without re-calling any API, and is where $/question and latency/question —
called out in the plan as first-class metrics, not just accuracy — get
computed.

Run:
    python -m analysis.aggregate_results <run_id_prefix>

where <run_id_prefix> matches the prefix used by eval/run_eval.py, e.g.
`eval-20260810T120000-abc123` (reads
runs/<prefix>-unified.jsonl and runs/<prefix>-routed.jsonl).
"""

from __future__ import annotations

import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from logging_.schema import RunLog  # noqa: E402
from logging_.sink import RunLogSink  # noqa: E402

# Anthropic first-party pricing, $ per million tokens (claude-opus-5, per
# shared/models.md at time of writing). Update if the model/pricing changes
# — this is an estimate for research reporting, not a billing reconciliation.
PRICE_PER_MTOK_INPUT = 5.00
PRICE_PER_MTOK_OUTPUT = 25.00


@dataclass
class ConditionSummary:
    experiment: str
    n_runs: int
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int
    estimated_cost_usd: float
    cost_per_question_usd: float
    mean_latency_ms: float
    p95_latency_ms: float
    hit_iteration_cap_rate: float
    mean_tool_calls_per_run: float


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000) * PRICE_PER_MTOK_INPUT + (
        output_tokens / 1_000_000
    ) * PRICE_PER_MTOK_OUTPUT


def summarize_condition(logs: list[RunLog]) -> ConditionSummary:
    if not logs:
        raise ValueError("No logs to summarize.")

    total_input = sum(log.total_input_tokens for log in logs)
    total_output = sum(log.total_output_tokens for log in logs)
    total_cache_read = sum(log.total_cache_read_tokens for log in logs)
    cost = estimate_cost_usd(total_input, total_output)
    latencies = sorted(log.wall_clock_ms for log in logs)
    hit_cap = sum(1 for log in logs if log.hit_iteration_cap)
    tool_call_counts = [len(log.tool_calls) for log in logs]

    p95_index = max(0, int(len(latencies) * 0.95) - 1)

    return ConditionSummary(
        experiment=logs[0].experiment,
        n_runs=len(logs),
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_cache_read_tokens=total_cache_read,
        estimated_cost_usd=cost,
        cost_per_question_usd=cost / len(logs),
        mean_latency_ms=statistics.mean(latencies),
        p95_latency_ms=latencies[p95_index],
        hit_iteration_cap_rate=hit_cap / len(logs),
        mean_tool_calls_per_run=statistics.mean(tool_call_counts),
    )


def print_comparison(unified: ConditionSummary, routed: ConditionSummary) -> None:
    rows = [
        ("n_runs", unified.n_runs, routed.n_runs),
        ("total_input_tokens", unified.total_input_tokens, routed.total_input_tokens),
        ("total_output_tokens", unified.total_output_tokens, routed.total_output_tokens),
        ("total_cache_read_tokens", unified.total_cache_read_tokens, routed.total_cache_read_tokens),
        ("estimated_cost_usd", f"{unified.estimated_cost_usd:.4f}", f"{routed.estimated_cost_usd:.4f}"),
        (
            "cost_per_question_usd",
            f"{unified.cost_per_question_usd:.4f}",
            f"{routed.cost_per_question_usd:.4f}",
        ),
        ("mean_latency_ms", f"{unified.mean_latency_ms:.0f}", f"{routed.mean_latency_ms:.0f}"),
        ("p95_latency_ms", unified.p95_latency_ms, routed.p95_latency_ms),
        (
            "hit_iteration_cap_rate",
            f"{unified.hit_iteration_cap_rate:.2%}",
            f"{routed.hit_iteration_cap_rate:.2%}",
        ),
        (
            "mean_tool_calls_per_run",
            f"{unified.mean_tool_calls_per_run:.1f}",
            f"{routed.mean_tool_calls_per_run:.1f}",
        ),
    ]

    label_width = max(len(r[0]) for r in rows) + 2
    print(f"{'metric':<{label_width}}{'unified':>15}{'routed':>15}")
    print("-" * (label_width + 30))
    for label, u_val, r_val in rows:
        print(f"{label:<{label_width}}{str(u_val):>15}{str(r_val):>15}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m analysis.aggregate_results <run_id_prefix>", file=sys.stderr)
        raise SystemExit(1)

    prefix = sys.argv[1]
    unified_logs = RunLogSink(f"{prefix}-unified").read_all()
    routed_logs = RunLogSink(f"{prefix}-routed").read_all()

    if not unified_logs or not routed_logs:
        print(
            f"No logs found for prefix {prefix!r} — expected "
            f"runs/{prefix}-unified.jsonl and runs/{prefix}-routed.jsonl",
            file=sys.stderr,
        )
        raise SystemExit(1)

    unified_summary = summarize_condition(unified_logs)
    routed_summary = summarize_condition(routed_logs)
    print_comparison(unified_summary, routed_summary)


if __name__ == "__main__":
    main()
