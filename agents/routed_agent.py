"""Experiment B: the routed specialist agent.

Router (agents/router.py) selects domain(s), then this runs the SAME shared
loop (agents/loop.py) as unified_agent.py, scoped to the union of the
selected domains' semantic models instead of the full unified model. See
plan §5: when the router returns 2+ domains, the specialist loop runs with
the union of those domains' models injected.
"""

from __future__ import annotations

import sys
import uuid
import yaml as pyyaml
from datetime import datetime, timezone
from pathlib import Path

import anthropic

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agents.loop import run_agent_loop  # noqa: E402
from agents.router import route_question, RouterDecision  # noqa: E402
from agents.sql_executor import SqlExecutor  # noqa: E402
from logging_.schema import RunLog, RoutingDecision, ToolCallLog  # noqa: E402
from logging_.sink import RunLogSink  # noqa: E402
from semantic_models.schema import merge_domain_models  # noqa: E402

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
ROUTED_SYSTEM_TEXT = (PROMPTS_DIR / "routed_system.md").read_text()

with open(REPO_ROOT / "config" / "experiment.yaml") as f:
    EXPERIMENT_CONFIG = pyyaml.safe_load(f)


NO_DOMAIN_MODEL_TEXT = (
    "domain: none\n"
    "description: >\n"
    "  The router did not match this question to any available domain. You\n"
    "  have no tables available to answer it.\n"
    "entities: []\n"
    "relationships: []\n"
    "dimensions: []\n"
    "metrics: []\n"
)


def _build_routed_semantic_model_text(domains: list[str]) -> str:
    if not domains:
        return NO_DOMAIN_MODEL_TEXT

    merged, unavailable_refs = merge_domain_models(domains)
    text = pyyaml.dump(merged, sort_keys=False, default_flow_style=False)
    if unavailable_refs:
        note_lines = "\n".join(f"#   - {r}" for r in unavailable_refs)
        text = (
            "# NOTE: the following cross-domain references point outside this "
            "routed view and are NOT usable joins here:\n" + note_lines + "\n\n" + text
        )
    return text


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

    router_decision: RouterDecision = route_question(client, question_text)
    semantic_model_text = _build_routed_semantic_model_text(router_decision.domains)

    turn = run_agent_loop(
        client=client,
        model_id=model_cfg["id"],
        effort=model_cfg["effort"],
        max_tokens=model_cfg["max_tokens"],
        condition_prompt_text=ROUTED_SYSTEM_TEXT,
        semantic_model_text=semantic_model_text,
        question_text=question_text,
        sql_executor=sql_executor,
        max_iterations=loop_cfg["max_tool_call_iterations"],
    )

    return RunLog(
        run_id=run_id,
        experiment="routed",
        model_id=model_cfg["id"],
        effort=model_cfg["effort"],
        thinking_mode=model_cfg["thinking"],
        question_id=question_id,
        question_category=question_category,
        question_text=question_text,
        trial_index=trial_index,
        routing_decision=RoutingDecision(
            domains=router_decision.domains,
            reasoning=router_decision.reasoning,
            ambiguous=router_decision.ambiguous,
            latency_ms=router_decision.latency_ms,
            request_id=router_decision.request_id,
        ),
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
        wall_clock_ms=turn.wall_clock_ms,
        hit_iteration_cap=turn.hit_iteration_cap,
        timestamp=datetime.now(timezone.utc).isoformat(),
        request_ids=[rid for rid in [router_decision.request_id] + turn.request_ids if rid],
    )


def main() -> None:
    """Manual smoke-test entry point: python -m agents.routed_agent "question"."""
    if len(sys.argv) < 2:
        print('Usage: python -m agents.routed_agent "your question"', file=sys.stderr)
        raise SystemExit(1)

    question_text = sys.argv[1]
    run_id = f"routed-manual-{uuid.uuid4().hex[:8]}"

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

    print(f"Routed to: {log.routing_decision.domains} ({log.routing_decision.reasoning})")
    print()
    print(log.final_answer_text)
    print(f"\n[logged to runs/{run_id}.jsonl]")
    sql_executor.close()


if __name__ == "__main__":
    main()
