from agents.sql_tables import check_domain_scope
from agents.tool_router_agent import (
    DOMAIN_NAMES,
    DOMAIN_SEMANTIC_MODELS,
    DOMAIN_TABLE_NAMES,
    TOOL_ROUTED_TOOLS,
    domains_visited,
)
from logging_.schema import RunLog, ToolCallLog
from datetime import datetime, timezone


def test_domain_query_tools_cover_every_configured_domain():
    tool_names = {t["name"] for t in TOOL_ROUTED_TOOLS}
    for name in DOMAIN_NAMES:
        assert f"query_{name}" in tool_names
    assert "get_semantic_model" in tool_names


def test_get_semantic_model_tool_enum_matches_domains():
    get_model_tool = next(t for t in TOOL_ROUTED_TOOLS if t["name"] == "get_semantic_model")
    assert get_model_tool["input_schema"]["properties"]["domain"]["enum"] == DOMAIN_NAMES


def test_domain_semantic_models_and_table_names_populated_for_every_domain():
    for name in DOMAIN_NAMES:
        assert DOMAIN_SEMANTIC_MODELS[name].strip()
        assert DOMAIN_TABLE_NAMES[name], f"{name} has no known tables"


def test_check_domain_scope_allows_query_within_domain():
    allowed = DOMAIN_TABLE_NAMES["geography"]
    table = next(iter(allowed))
    sql = f"SELECT * FROM {table} LIMIT 10"
    assert check_domain_scope(sql, allowed) is None


def test_check_domain_scope_rejects_table_outside_domain():
    allowed = DOMAIN_TABLE_NAMES["deposits"]
    foreign_table = next(iter(DOMAIN_TABLE_NAMES["markets"] - allowed))
    sql = f"SELECT * FROM {foreign_table}"
    error = check_domain_scope(sql, allowed)
    assert error is not None
    assert foreign_table in error


def test_check_domain_scope_ignores_cte_names():
    allowed = DOMAIN_TABLE_NAMES["geography"]
    table = next(iter(allowed))
    sql = f"WITH recent AS (SELECT * FROM {table}) SELECT * FROM recent"
    assert check_domain_scope(sql, allowed) is None


def test_check_domain_scope_ignores_every_cte_in_a_multi_cte_with_clause():
    # Regression test: \b doesn't match at a bare comma (non-word char on both
    # sides), so a naive `\b(?:WITH|,)` pattern only ever caught the first CTE
    # in a "WITH a AS (...), b AS (...)" clause. Found live on Experiment C's
    # Evansville pilot run, where a second CTE named `ts` was misflagged as an
    # out-of-domain table.
    allowed = DOMAIN_TABLE_NAMES["deposits"]
    t1, t2 = list(allowed)[:2]
    sql = (
        f"WITH br AS (SELECT * FROM {t1}), ts AS (SELECT * FROM {t2}) "
        "SELECT * FROM br JOIN ts ON 1=1"
    )
    assert check_domain_scope(sql, allowed) is None


def _make_log(tool_calls: list[ToolCallLog]) -> RunLog:
    return RunLog(
        run_id="test",
        experiment="tool_routed",
        model_id="claude-opus-5",
        effort="high",
        thinking_mode="adaptive",
        question_id="q1",
        question_category="single_domain",
        question_text="test",
        trial_index=0,
        tool_calls=tool_calls,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def test_domains_visited_derives_from_query_tool_calls():
    log = _make_log(
        [
            ToolCallLog(tool_name="get_semantic_model", tool_input={"domain": "geography"}, tool_output="", latency_ms=1),
            ToolCallLog(tool_name="query_geography", tool_input={"sql": "SELECT 1"}, tool_output="", latency_ms=1),
            ToolCallLog(tool_name="query_deposits", tool_input={"sql": "SELECT 1"}, tool_output="", latency_ms=1),
            ToolCallLog(tool_name="query_geography", tool_input={"sql": "SELECT 2"}, tool_output="", latency_ms=1),
        ]
    )
    assert domains_visited(log) == ["geography", "deposits"]


def test_domains_visited_empty_when_no_tool_calls():
    assert domains_visited(_make_log([])) == []


class _FakeToolUseBlock:
    type = "tool_use"

    def __init__(self, name, input_, id_):
        self.name = name
        self.input = input_
        self.id = id_


class _FakeTextBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _FakeUsage:
    input_tokens = 10
    output_tokens = 5
    cache_read_input_tokens = 0
    cache_creation_input_tokens = 0


class _FakeResponse:
    def __init__(self, content, stop_reason, request_id="req_test"):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = _FakeUsage()
        self._request_id = request_id


class _FakeStreamCM:
    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def get_final_message(self):
        return self._response

    @property
    def request_id(self):
        return self._response._request_id


class _FakeMessages:
    def __init__(self, responses):
        self._responses = list(responses)
        self.call_count = 0

    def stream(self, **kwargs):
        response = self._responses[self.call_count]
        self.call_count += 1
        return _FakeStreamCM(response)


class _FakeClient:
    def __init__(self, responses):
        self.messages = _FakeMessages(responses)


class _FakeSqlExecutor:
    def execute(self, sql: str):
        from agents.sql_executor import QueryResult

        return QueryResult(sql=sql, columns=["X"], rows=[(1,)], row_count_returned=1)


def test_tool_routed_loop_executes_domain_query_without_a_plan_gate():
    from agents.loop import run_tool_routed_agent_loop

    responses = [
        _FakeResponse(
            [_FakeToolUseBlock("query_geography", {"sql": "SELECT 1"}, "t1")],
            stop_reason="tool_use",
        ),
        _FakeResponse(
            [_FakeTextBlock("Answer.")],
            stop_reason="end_turn",
        ),
    ]

    turn = run_tool_routed_agent_loop(
        client=_FakeClient(responses),
        model_id="claude-sonnet-5",
        effort="medium",
        max_tokens=1000,
        system_text="system prompt",
        question_text="What metro area is Evansville in?",
        sql_executor=_FakeSqlExecutor(),
        tools=TOOL_ROUTED_TOOLS,
        domain_semantic_models=DOMAIN_SEMANTIC_MODELS,
        domain_table_names=DOMAIN_TABLE_NAMES,
        max_iterations=8,
    )

    assert len(turn.tool_calls) == 1
    assert turn.tool_calls[0].tool_name == "query_geography"
    assert turn.tool_calls[0].is_error is False
    assert turn.final_answer_text == "Answer."

