"""Shared Claude tool-use agent loops for the three study conditions.

`run_agent_loop` is used by schema_only (condition 1) and unified
(condition 2) — they differ only in which schema text and which
condition prompt get passed in. `run_tool_routed_agent_loop` is
condition 3: no schema is front-loaded, and each domain is its own
SQL tool with a scope check.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

from agents.sql_executor import SqlExecutor
from agents.sql_tables import check_domain_scope
from agents.tools import ALL_TOOLS

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
SHARED_SYSTEM_CORE = (PROMPTS_DIR / "shared_system_core.md").read_text()


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


def _build_system_blocks(
    condition_prompt_text: str,
    schema_text: str,
    schema_heading: str = "Semantic Model",
) -> list[dict]:
    """Shared core (never changes) as block 1; condition + schema as block 2.

    cache_control on the last block caches both, and stays valid across all
    trials of the same question and across questions that share the same
    schema (the physical catalog, or the whole unified model).
    """
    return [
        {"type": "text", "text": SHARED_SYSTEM_CORE},
        {
            "type": "text",
            "text": (
                f"{condition_prompt_text}\n\n## {schema_heading}\n\n"
                f"```\n{schema_text}\n```"
            ),
            "cache_control": {"type": "ephemeral"},
        },
    ]


def _print_turn(label: str, iteration: int, max_iterations: int, response) -> None:
    n_tools = sum(1 for b in response.content if getattr(b, "type", None) == "tool_use")
    print(
        f"  [{label}] turn {iteration}/{max_iterations} "
        f"stop={response.stop_reason} tool_calls={n_tools}",
        flush=True,
    )


def _execute_tool(
    tool_name: str,
    tool_input: dict,
    sql_executor: SqlExecutor,
) -> tuple[str, bool, int]:
    start = time.monotonic()
    if tool_name == "run_sql":
        result = sql_executor.execute(tool_input.get("sql", ""))
        output_text = result.to_tool_result_text()
        is_error = bool(result.error)
    else:
        output_text = f"Unknown tool: {tool_name}"
        is_error = True
    latency_ms = int((time.monotonic() - start) * 1000)
    return output_text, is_error, latency_ms


def _force_final_synthesis(
    client: anthropic.Anthropic,
    model_id: str,
    effort: str,
    max_tokens: int,
    system_blocks: list[dict],
    messages: list[dict],
    tools: list[dict],
) -> tuple[str, dict]:
    """One more call with tools disabled, forcing a best-effort final answer
    from whatever has already been gathered.
    """
    synthesis_messages = messages + [
        {
            "role": "user",
            "content": (
                "You have reached the maximum number of tool calls for this task. "
                "Do not call any more tools — answer now, using only what you've "
                "already found. If some part of the question isn't fully answered "
                "by what you have, say so explicitly rather than guessing. Follow "
                "the final answer format from your instructions, including source "
                "citations."
            ),
        }
    ]

    with client.messages.stream(
        model=model_id,
        max_tokens=max_tokens,
        system=system_blocks,
        thinking={"type": "adaptive"},
        output_config={"effort": effort},
        tools=tools,
        tool_choice={"type": "none"},
        messages=synthesis_messages,
    ) as stream:
        response = stream.get_final_message()
        request_id = stream.request_id

    text_blocks = [b.text for b in response.content if b.type == "text"]
    final_text = "\n".join(text_blocks)

    usage = {
        "request_id": request_id,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "cache_read_tokens": response.usage.cache_read_input_tokens or 0,
        "cache_creation_tokens": response.usage.cache_creation_input_tokens or 0,
    }
    return final_text, usage


def run_agent_loop(
    client: anthropic.Anthropic,
    model_id: str,
    effort: str,
    max_tokens: int,
    condition_prompt_text: str,
    semantic_model_text: str,
    question_text: str,
    sql_executor: SqlExecutor,
    max_iterations: int = 16,
    schema_heading: str = "Semantic Model",
) -> AgentTurnResult:
    result = AgentTurnResult()
    start_time = time.monotonic()

    system_blocks = _build_system_blocks(
        condition_prompt_text, semantic_model_text, schema_heading=schema_heading
    )
    messages: list[dict] = [{"role": "user", "content": question_text}]

    iteration = 0
    while True:
        iteration += 1
        if iteration > max_iterations:
            result.hit_iteration_cap = True
            final_text, usage = _force_final_synthesis(
                client, model_id, effort, max_tokens, system_blocks, messages, ALL_TOOLS
            )
            result.final_answer_text = final_text
            result.total_input_tokens += usage["input_tokens"]
            result.total_output_tokens += usage["output_tokens"]
            result.total_cache_read_tokens += usage["cache_read_tokens"]
            result.total_cache_creation_tokens += usage["cache_creation_tokens"]
            if usage["request_id"]:
                result.request_ids.append(usage["request_id"])
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
            request_id = stream.request_id

        if request_id:
            result.request_ids.append(request_id)

        result.total_input_tokens += response.usage.input_tokens
        result.total_output_tokens += response.usage.output_tokens
        result.total_cache_read_tokens += response.usage.cache_read_input_tokens or 0
        result.total_cache_creation_tokens += response.usage.cache_creation_input_tokens or 0
        result.stop_reason = response.stop_reason
        _print_turn("agent-loop", iteration, max_iterations, response)

        if response.stop_reason == "refusal":
            result.final_answer_text = "[REFUSED]"
            break

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            text_blocks = [b.text for b in response.content if b.type == "text"]
            result.final_answer_text = "\n".join(text_blocks)
            break

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        tool_results = []
        for block in tool_use_blocks:
            output_text, is_error, latency_ms = _execute_tool(
                block.name, block.input, sql_executor
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


def _execute_tool_routed_tool(
    tool_name: str,
    tool_input: dict,
    sql_executor: SqlExecutor,
    domain_semantic_models: dict[str, str],
    domain_table_names: dict[str, set[str]],
) -> tuple[str, bool, int]:
    start = time.monotonic()
    if tool_name == "get_semantic_model":
        domain = tool_input.get("domain", "")
        if domain not in domain_semantic_models:
            output_text = f"Unknown domain {domain!r}. Valid domains: {sorted(domain_semantic_models)}"
            is_error = True
        else:
            output_text = domain_semantic_models[domain]
            is_error = False
    elif tool_name.startswith("query_"):
        domain = tool_name[len("query_") :]
        sql = tool_input.get("sql", "")
        allowed = domain_table_names.get(domain)
        scope_error = check_domain_scope(sql, allowed) if allowed else None
        if scope_error:
            output_text = scope_error
            is_error = True
        else:
            result = sql_executor.execute(sql)
            output_text = result.to_tool_result_text()
            is_error = bool(result.error)
    else:
        output_text = f"Unknown tool: {tool_name}"
        is_error = True
    latency_ms = int((time.monotonic() - start) * 1000)
    return output_text, is_error, latency_ms


def run_tool_routed_agent_loop(
    client: anthropic.Anthropic,
    model_id: str,
    effort: str,
    max_tokens: int,
    system_text: str,
    question_text: str,
    sql_executor: SqlExecutor,
    tools: list[dict],
    domain_semantic_models: dict[str, str],
    domain_table_names: dict[str, set[str]],
    max_iterations: int = 16,
) -> AgentTurnResult:
    result = AgentTurnResult()
    start_time = time.monotonic()

    # Unlike _build_system_blocks (conditions 1/2), there's no per-question
    # schema text to embed — the system prompt is identical across every
    # question in this condition, so it's cacheable across the whole study,
    # not just across trials of the same question.
    system_blocks = [{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}]
    messages: list[dict] = [{"role": "user", "content": question_text}]

    iteration = 0
    while True:
        iteration += 1
        if iteration > max_iterations:
            result.hit_iteration_cap = True
            final_text, usage = _force_final_synthesis(
                client, model_id, effort, max_tokens, system_blocks, messages, tools
            )
            result.final_answer_text = final_text
            result.total_input_tokens += usage["input_tokens"]
            result.total_output_tokens += usage["output_tokens"]
            result.total_cache_read_tokens += usage["cache_read_tokens"]
            result.total_cache_creation_tokens += usage["cache_creation_tokens"]
            if usage["request_id"]:
                result.request_ids.append(usage["request_id"])
            break

        with client.messages.stream(
            model=model_id,
            max_tokens=max_tokens,
            system=system_blocks,
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            tools=tools,
            messages=messages,
        ) as stream:
            response = stream.get_final_message()
            request_id = stream.request_id

        if request_id:
            result.request_ids.append(request_id)
        result.total_input_tokens += response.usage.input_tokens
        result.total_output_tokens += response.usage.output_tokens
        result.total_cache_read_tokens += response.usage.cache_read_input_tokens or 0
        result.total_cache_creation_tokens += response.usage.cache_creation_input_tokens or 0
        result.stop_reason = response.stop_reason
        _print_turn("tool-routed", iteration, max_iterations, response)

        if response.stop_reason == "refusal":
            result.final_answer_text = "[REFUSED]"
            break

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            text_blocks = [b.text for b in response.content if b.type == "text"]
            result.final_answer_text = "\n".join(text_blocks)
            break

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        tool_results = []
        for block in tool_use_blocks:
            output_text, is_error, latency_ms = _execute_tool_routed_tool(
                block.name, block.input, sql_executor, domain_semantic_models, domain_table_names
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
            if block.name.startswith("query_"):
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
