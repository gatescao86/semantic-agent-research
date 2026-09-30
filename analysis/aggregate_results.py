#!/usr/bin/env python
"""Rolls up persisted JSONL run logs (runs/*.jsonl) into cost, latency, and
efficiency comparison tables for the three conditions: schema_only,
unified, and tool_routed.

This is separate from eval/run_eval.py's live in-run summary: it operates
on logs already written to disk, so it can be re-run against past runs
without re-calling any API. Cost and latency are first-class metrics, not
just accuracy.

Run:
    python -m analysis.aggregate_results <run_id_prefix>

where <run_id_prefix> matches the prefix used by eval/run_eval.py, e.g.
`eval-20260810T120000-abc123` (reads runs/<prefix>-schema_only.jsonl,
runs/<prefix>-unified.jsonl, and runs/<prefix>-tool_routed.jsonl).
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

PRIMARY_CONDITIONS = ("schema_only", "unified", "tool_routed")

# Anthropic first-party pricing, $ per million tokens. All three conditions
# use claude-opus-4-7 (config/experiment.yaml). Update if the model changes —
# this is an estimate for research reporting, not a billing reconciliation.
# Cache read/write are priced relative to the base input rate — see
# https://docs.anthropic.com/en/docs/about-claude/pricing: reads 0.1x,
# 5-minute cache writes 1.25x.
PRICE_PER_MTOK_INPUT = 5.00
PRICE_PER_MTOK_OUTPUT = 25.00
PRICE_PER_MTOK_CACHE_READ = PRICE_PER_MTOK_INPUT * 0.1
PRICE_PER_MTOK_CACHE_WRITE = PRICE_PER_MTOK_INPUT * 1.25


@dataclass
class ConditionSummary:
    experiment: str
    n_runs: int
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int
    total_cache_creation_tokens: int
    estimated_cost_usd: float
    cost_per_question_usd: float
    mean_latency_ms: float
    p95_latency_ms: float
    hit_iteration_cap_rate: float
    mean_tool_calls_per_run: float


def estimate_cost_usd(
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> float:
    return (
        (input_tokens / 1_000_000) * PRICE_PER_MTOK_INPUT
        + (output_tokens / 1_000_000) * PRICE_PER_MTOK_OUTPUT
        + (cache_read_tokens / 1_000_000) * PRICE_PER_MTOK_CACHE_READ
        + (cache_creation_tokens / 1_000_000) * PRICE_PER_MTOK_CACHE_WRITE
    )


def summarize_condition(logs: list[RunLog]) -> ConditionSummary:
    if not logs:
        raise ValueError("No logs to summarize.")

    total_input = sum(log.total_input_tokens for log in logs)
    total_output = sum(log.total_output_tokens for log in logs)
    total_cache_read = sum(log.total_cache_read_tokens for log in logs)
    total_cache_creation = sum(log.total_cache_creation_tokens for log in logs)
    cost = estimate_cost_usd(total_input, total_output, total_cache_read, total_cache_creation)
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
        total_cache_creation_tokens=total_cache_creation,
        estimated_cost_usd=cost,
        cost_per_question_usd=cost / len(logs),
        mean_latency_ms=statistics.mean(latencies),
        p95_latency_ms=latencies[p95_index],
        hit_iteration_cap_rate=hit_cap / len(logs),
        mean_tool_calls_per_run=statistics.mean(tool_call_counts),
    )


def print_comparison(*summaries: ConditionSummary) -> None:
    if not summaries:
        raise ValueError("No summaries to print.")

    def _cell(summary: ConditionSummary, attr: str, fmt: str | None = None) -> str:
        value = getattr(summary, attr)
        if fmt is None:
            return str(value)
        if fmt == "usd":
            return f"{value:.4f}"
        if fmt == "ms":
            return f"{value:.0f}"
        if fmt == "pct":
            return f"{value:.2%}"
        if fmt == "tools":
            return f"{value:.1f}"
        return str(value)

    rows = [
        ("n_runs", None),
        ("total_input_tokens", None),
        ("total_output_tokens", None),
        ("total_cache_read_tokens", None),
        ("total_cache_creation_tokens", None),
        ("estimated_cost_usd", "usd"),
        ("cost_per_question_usd", "usd"),
        ("mean_latency_ms", "ms"),
        ("p95_latency_ms", None),
        ("hit_iteration_cap_rate", "pct"),
        ("mean_tool_calls_per_run", "tools"),
    ]

    label_width = max(len(r[0]) for r in rows) + 2
    col_width = 22
    header = f"{'metric':<{label_width}}" + "".join(
        f"{s.experiment:>{col_width}}" for s in summaries
    )
    print(header)
    print("-" * (label_width + col_width * len(summaries)))
    for label, fmt in rows:
        cells = "".join(f"{_cell(s, label, fmt):>{col_width}}" for s in summaries)
        print(f"{label:<{label_width}}{cells}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m analysis.aggregate_results <run_id_prefix>", file=sys.stderr)
        raise SystemExit(1)

    prefix = sys.argv[1]
    logs_by_condition = {
        name: RunLogSink(f"{prefix}-{name}").read_all() for name in PRIMARY_CONDITIONS
    }
    missing = [name for name, logs in logs_by_condition.items() if not logs]
    if missing:
        expected = " and ".join(f"runs/{prefix}-{n}.jsonl" for n in PRIMARY_CONDITIONS)
        print(
            f"No logs found for prefix {prefix!r} — expected {expected}. "
            f"Missing: {missing}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    print_comparison(*(summarize_condition(logs_by_condition[n]) for n in PRIMARY_CONDITIONS))


if __name__ == "__main__":
    main()
