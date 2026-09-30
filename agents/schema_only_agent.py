"""Condition 1: raw schema, no semantic model.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agents.loop import run_agent_loop  # noqa: E402
from agents.sql_executor import SqlExecutor  # noqa: E402
from logging_.schema import RunLog, ToolCallLog  # noqa: E402
from logging_.sink import RunLogSink  # noqa: E402

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
SCHEMA_ONLY_SYSTEM_TEXT = (PROMPTS_DIR / "schema_only_system.md").read_text()
SCHEMA_CATALOG_PATH = REPO_ROOT / "semantic_models" / "raw" / "schema_catalog.md"

with open(REPO_ROOT / "config" / "experiment.yaml") as f:
    EXPERIMENT_CONFIG = yaml.safe_load(f)


def _load_schema_catalog_text() -> str:
    if not SCHEMA_CATALOG_PATH.exists():
        raise FileNotFoundError(
            f"{SCHEMA_CATALOG_PATH} is missing. Run "
            "`python scripts/generate_schema_catalog.py` first."
        )
    return SCHEMA_CATALOG_PATH.read_text()


def answer_question(
    client: anthropic.Anthropic,
    sql_executor: SqlExecutor,
    question_id: str,
    question_category: str,
    question_text: str,
    trial_index: int,
    run_id: str,
) -> RunLog:
    model_cfg = EXPERIMENT_CONFIG["model"]
    loop_cfg = EXPERIMENT_CONFIG["agent_loop"]

    turn = run_agent_loop(
        client=client,
        model_id=model_cfg["id"],
        effort=model_cfg["effort"],
        max_tokens=model_cfg["max_tokens"],
        condition_prompt_text=SCHEMA_ONLY_SYSTEM_TEXT,
        semantic_model_text=_load_schema_catalog_text(),
        question_text=question_text,
        sql_executor=sql_executor,
        max_iterations=loop_cfg["max_tool_call_iterations"],
        schema_heading="Table catalog",
    )

    return RunLog(
        run_id=run_id,
        experiment="schema_only",
        model_id=model_cfg["id"],
        effort=model_cfg["effort"],
        thinking_mode=model_cfg["thinking"],
        question_id=question_id,
        question_category=question_category,
        question_text=question_text,
        trial_index=trial_index,
        routing_decision=None,
        tool_calls=[
            ToolCallLog(
                tool_name=tc.tool_name,
                tool_input=tc.tool_input,
                tool_output=tc.tool_output,
                latency_ms=tc.latency_ms,
                is_error=tc.is_error,
            )
            for tc in turn.tool_calls
        ],
        generated_sql=turn.generated_sql,
        sql_execution_errors=turn.sql_execution_errors,
        final_answer_text=turn.final_answer_text,
        final_answer_structured=turn.final_answer_structured,
        total_input_tokens=turn.total_input_tokens,
        total_output_tokens=turn.total_output_tokens,
        total_cache_read_tokens=turn.total_cache_read_tokens,
        total_cache_creation_tokens=turn.total_cache_creation_tokens,
        wall_clock_ms=turn.wall_clock_ms,
        hit_iteration_cap=turn.hit_iteration_cap,
        timestamp=datetime.now(timezone.utc).isoformat(),
        request_ids=turn.request_ids,
    )


def main() -> None:
    """Manual smoke-test entry point: python -m agents.schema_only_agent "question"."""
    if len(sys.argv) < 2:
        print('Usage: python -m agents.schema_only_agent "your question"', file=sys.stderr)
        raise SystemExit(1)

    question_text = sys.argv[1]
    run_id = f"schema-only-manual-{uuid.uuid4().hex[:8]}"

    client = anthropic.Anthropic()
    sql_executor = SqlExecutor(
        max_rows_returned=EXPERIMENT_CONFIG["sql_executor"]["max_rows_returned"],
        query_timeout_seconds=EXPERIMENT_CONFIG["sql_executor"]["query_timeout_seconds"],
    )
    sink = RunLogSink(run_id)

    log = answer_question(
        client=client,
        sql_executor=sql_executor,
        question_id="manual",
        question_category="single_domain",
        question_text=question_text,
        trial_index=0,
        run_id=run_id,
    )
    sink.write(log)

    print(log.final_answer_text)
    print(f"\n[logged to runs/{run_id}.jsonl]")
    sql_executor.close()


if __name__ == "__main__":
    main()
