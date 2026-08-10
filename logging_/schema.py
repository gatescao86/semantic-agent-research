"""Structured run-log schema. See plan §6.

One RunLog per (experiment, question, trial) attempt. Written immediately
after each question completes (not buffered) via logging_/sink.py, so
partial runs are always recoverable.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ToolCallLog(BaseModel):
    tool_name: str
    tool_input: dict
    tool_output: str
    latency_ms: int
    is_error: bool = False


class RoutingDecision(BaseModel):
    domains: list[str]
    reasoning: str
    ambiguous: bool
    latency_ms: int
    request_id: str | None = None


class RunLog(BaseModel):
    run_id: str
    experiment: Literal["unified", "routed"]
    model_id: str
    effort: str
    thinking_mode: str

    question_id: str
    question_category: Literal["single_domain", "cross_domain", "executive"]
    question_text: str
    trial_index: int

    routing_decision: RoutingDecision | None = None

    tool_calls: list[ToolCallLog] = Field(default_factory=list)
    generated_sql: list[str] = Field(default_factory=list)
    sql_execution_errors: list[str] = Field(default_factory=list)

    final_answer_text: str = ""
    final_answer_structured: dict | None = None

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    wall_clock_ms: int = 0
    hit_iteration_cap: bool = False

    # Populated post-hoc by the eval harness (eval/run_eval.py), not by the agent run itself.
    failure_modes: list[str] = Field(default_factory=list)

    timestamp: str
    request_ids: list[str] = Field(default_factory=list)
