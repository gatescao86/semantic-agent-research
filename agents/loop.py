"""The single shared Claude tool-use agent loop.

Used identically by unified_agent.py (Experiment A) and routed_agent.py
(Experiment B) — they differ only in which semantic model text and which
condition-specific prompt snippet (unified_system.md vs routed_system.md)
get passed in. See plan §5 for why this must be one implementation: if the
two experiments had independently written loops, any measured performance
delta would be confounded by incidental implementation differences, not
just semantic architecture.

Uses a manual loop (not the SDK's beta Tool Runner) so every tool call's
latency, input, and output can be captured for logging_/schema.py's
ToolCallLog — the Tool Runner's per-turn hooks could do this too, but a
manual loop keeps the instrumentation point obvious and avoids a beta
dependency.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

from agents.sql_executor import SqlExecutor
from agents.tools import ALL_TOOLS

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
SHARED_SYSTEM_CORE = (PROMPTS_DIR / "shared_system_core.md").read_text()

_JSON_FOOTER_RE = re.compile(r"\{[^{}]*\"sql_used\"[^{}]*\}", re.DOTALL)


@dataclass
class ToolCallRecord:
    tool_name: str
    tool_input: dict
    tool_output: str
    latency_ms: int
    is_error: bool = False


@dataclass
class AgentTurnResult:
    final_answer_text: str = ""
    final_answer_structured: dict | None = None
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    generated_sql: list[str] = field(default_factory=list)
    sql_execution_errors: list[str] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_creation_tokens: int = 0
    wall_clock_ms: int = 0
    hit_iteration_cap: bool = False
    request_ids: list[str] = field(default_factory=list)
    stop_reason: str | None = None


def _extract_structured_footer(text: str) -> dict | None:
    match = _JSON_FOOTER_RE.search(text)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _build_system_blocks(condition_prompt_text: str, semantic_model_text: str) -> list[dict]:
    """Shared core (never changes) as block 1; condition + semantic model as block 2.

    cache_control on the last block caches both, and stays valid across all
    trials of the same question and across questions that share the same
    semantic-model scope (whole unified model, or the same routed domain set).
    """
    return [
        {"type": "text", "text": SHARED_SYSTEM_CORE},
        {
            "type": "text",
            "text": (
                f"{condition_prompt_text}\n\n## Semantic Model\n\n"
                f"```yaml\n{semantic_model_text}\n```"
            ),
            "cache_control": {"type": "ephemeral"},
        },
    ]


def _execute_tool(
    tool_name: str,
    tool_input: dict,
    sql_executor: SqlExecutor,
    semantic_model_text: str,
) -> tuple[str, bool, int]:
    start = time.monotonic()
    if tool_name == "get_semantic_model":
        output_text = semantic_model_text
        is_error = False
    elif tool_name == "run_sql":
        result = sql_executor.execute(tool_input.get("sql", ""))
        output_text = result.to_tool_result_text()
        is_error = bool(result.error)
    else:
        output_text = f"Unknown tool: {tool_name}"
        is_error = True
    latency_ms = int((time.monotonic() - start) * 1000)
    return output_text, is_error, latency_ms


def run_agent_loop(
    client: anthropic.Anthropic,
    model_id: str,
    effort: str,
    max_tokens: int,
    condition_prompt_text: str,
    semantic_model_text: str,
    question_text: str,
    sql_executor: SqlExecutor,
    max_iterations: int = 8,
) -> AgentTurnResult:
    result = AgentTurnResult()
    start_time = time.monotonic()

    system_blocks = _build_system_blocks(condition_prompt_text, semantic_model_text)
    messages: list[dict] = [{"role": "user", "content": question_text}]

    iteration = 0
    while True:
        iteration += 1
        if iteration > max_iterations:
            result.hit_iteration_cap = True
            break

        with client.messages.stream(
            model=model_id,
            max_tokens=max_tokens,
            system=system_blocks,
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            tools=ALL_TOOLS,
            messages=messages,
        ) as stream:
            response = stream.get_final_message()

        result.request_ids.append(response._request_id)
        result.total_input_tokens += response.usage.input_tokens
        result.total_output_tokens += response.usage.output_tokens
        result.total_cache_read_tokens += response.usage.cache_read_input_tokens or 0
        result.total_cache_creation_tokens += response.usage.cache_creation_input_tokens or 0
        result.stop_reason = response.stop_reason

        if response.stop_reason == "refusal":
            result.final_answer_text = "[REFUSED]"
            break

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            text_blocks = [b.text for b in response.content if b.type == "text"]
            result.final_answer_text = "\n".join(text_blocks)
            result.final_answer_structured = _extract_structured_footer(result.final_answer_text)
            break

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        tool_results = []
        for block in tool_use_blocks:
            output_text, is_error, latency_ms = _execute_tool(
                block.name, block.input, sql_executor, semantic_model_text
            )
            result.tool_calls.append(
                ToolCallRecord(
                    tool_name=block.name,
                    tool_input=block.input,
                    tool_output=output_text,
                    latency_ms=latency_ms,
                    is_error=is_error,
                )
            )
            if block.name == "run_sql":
                sql = block.input.get("sql", "")
                result.generated_sql.append(sql)
                if is_error:
                    result.sql_execution_errors.append(output_text)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output_text,
                    "is_error": is_error,
                }
            )

        messages.append({"role": "user", "content": tool_results})

    result.wall_clock_ms = int((time.monotonic() - start_time) * 1000)
    return result
