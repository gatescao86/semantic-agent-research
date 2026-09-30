from logging_.schema import RunLog, ToolCallLog
from analysis.aggregate_results import (
    PRIMARY_CONDITIONS,
    estimate_cost_usd,
    summarize_condition,
)


def _log(experiment: str, tokens: int = 100, wall: int = 1000, n_tools: int = 1) -> RunLog:
    return RunLog(
        run_id="test",
        experiment=experiment,
        model_id="claude-sonnet-5",
        effort="medium",
        thinking_mode="adaptive",
        question_id="q1",
        question_category="factual",
        question_text="q",
        trial_index=0,
        tool_calls=[
            ToolCallLog(tool_name="run_sql", tool_input={}, tool_output="", latency_ms=1)
            for _ in range(n_tools)
        ],
        final_answer_text="answer",
        total_input_tokens=tokens,
        total_output_tokens=10,
        wall_clock_ms=wall,
        timestamp="2026-01-01T00:00:00Z",
    )


def test_primary_conditions_are_the_three_architectures():
    assert PRIMARY_CONDITIONS == ("schema_only", "unified", "tool_routed")


def test_summarize_condition_cost_and_latency():
    logs = [_log("schema_only", tokens=1_000_000, wall=100, n_tools=2)]
    summary = summarize_condition(logs)
    assert summary.experiment == "schema_only"
    assert summary.n_runs == 1
    assert summary.mean_latency_ms == 100
    assert summary.p95_latency_ms == 100
    assert summary.mean_tool_calls_per_run == 2
    assert summary.estimated_cost_usd == estimate_cost_usd(1_000_000, 10)
    assert summary.cost_per_question_usd == summary.estimated_cost_usd
