from eval.failure_report import detect_trace_notes, render_failure_report, summarize_trace


ATTR = "SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FDIC_SUMMARY_OF_DEPOSITS_ATTRIBUTES"
TS = "SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.FDIC_SUMMARY_OF_DEPOSITS_TIMESERIES"


def test_detects_ilike_and_attributes_browse():
    browse = f"SELECT variable, variable_name FROM {ATTR} WHERE variable_name ILIKE '%deposit%' LIMIT 20"
    joined = (
        f"SELECT t.value FROM {TS} t JOIN {ATTR} a ON t.variable = a.variable "
        "WHERE a.variable_name ILIKE '%deposits%'"
    )
    notes = detect_trace_notes([browse, joined])
    assert "ilike" in notes
    assert "attributes_only_browse" in notes
    assert "ilike_on_timeseries" not in notes


def test_detects_timeseries_distinct_and_ilike_on_facts():
    sql = f"SELECT DISTINCT variable_name FROM {TS} WHERE variable_name ILIKE '%deposit%'"
    notes = detect_trace_notes([sql])
    assert "timeseries_distinct" in notes
    assert "ilike_on_timeseries" in notes
    assert "attributes_only_browse" not in notes


def test_summarize_trace_includes_tool_sequence_and_sql():
    log = {
        "experiment": "schema_only",
        "run_id": "r1",
        "generated_sql": [f"SELECT 1 FROM {TS} WHERE variable = 'DEPSUMBR'"],
        "tool_calls": [{"tool_name": "run_sql", "is_error": False}],
        "sql_execution_errors": [],
        "hit_iteration_cap": False,
    }
    trace = summarize_trace(log)
    assert trace["tool_sequence"] == ["run_sql"]
    assert any("DEPSUMBR" in sql for sql in trace["sql"])
    assert any("TIMESERIES" in t for t in trace["tables"])


def _record() -> dict:
    sql_ilike = (
        f"SELECT t.value FROM {TS} t JOIN {ATTR} a ON t.variable = a.variable "
        "WHERE a.variable_name ILIKE '%deposits%'"
    )
    sql_ok = f"SELECT t.value FROM {TS} t WHERE t.variable = 'DEPSUMBR'"
    return {
        "question": {
            "id": "ex-001",
            "criteria": [
                {
                    "id": "001",
                    "match_criteria": "PASS if the market is the metro. FAIL if city proper.",
                },
                {
                    "id": "002",
                    "match_criteria": (
                        "PASS if the answer reports the Evansville deposit market as a dollar total. "
                        "FAIL if no market-total is stated."
                    ),
                },
            ],
        },
        "trial": 0,
        "schema_only": {
            "experiment": "schema_only",
            "generated_sql": [sql_ilike],
            "tool_calls": [{"tool_name": "run_sql"}],
        },
        "unified": {
            "experiment": "unified",
            "generated_sql": [sql_ok],
            "tool_calls": [{"tool_name": "run_sql"}],
        },
        "tool_routed": {
            "experiment": "tool_routed",
            "generated_sql": [
                f"SELECT variable FROM {ATTR} WHERE variable_name ILIKE '%deposit%'",
                sql_ok,
            ],
            "tool_calls": [
                {"tool_name": "get_semantic_model"},
                {"tool_name": "query_deposits"},
                {"tool_name": "query_deposits"},
            ],
        },
        "schema_only_score": {
            "n_passed": 1,
            "n_criteria": 2,
            "criterion_pass_rate": 0.5,
            "criteria_results": [
                {"id": "001", "verdict": "PASS", "reasoning": "Names the metro."},
                {
                    "id": "002",
                    "verdict": "FAIL",
                    "failure_reason": "absent",
                    "reasoning": "No CBSA-wide deposit total is stated.",
                },
            ],
        },
        "unified_score": {
            "n_passed": 1,
            "n_criteria": 2,
            "criterion_pass_rate": 0.5,
            "criteria_results": [
                {"id": "001", "verdict": "PASS", "reasoning": "Names the metro."},
                {
                    "id": "002",
                    "verdict": "FAIL",
                    "failure_reason": "numeric_mismatch",
                    "claimed_value": 13900000,
                    "expected_value": 14314109,
                    "unit": "USD_thousands",
                    "reasoning": "Reports top-10 deposits (~$13.9B), not the market total.",
                },
            ],
        },
        "tool_routed_score": {
            "n_passed": 2,
            "n_criteria": 2,
            "criterion_pass_rate": 1.0,
            "criteria_results": [
                {"id": "001", "verdict": "PASS", "reasoning": "Names the metro."},
                {
                    "id": "002",
                    "verdict": "PASS",
                    "claimed_value": 14310000,
                    "expected_value": 14314109,
                    "reasoning": "States ~$14.31B in-market deposits.",
                },
            ],
        },
    }


def test_report_has_grid_fail_reasoning_and_sql():
    report = render_failure_report([_record()])
    assert "## ex-001 (trial 0)" in report
    assert "FAIL absent" in report
    assert "FAIL numeric_mismatch (13900000 vs 14314109)" in report
    assert "No CBSA-wide deposit total is stated." in report
    assert "top-10" in report
    assert "ILIKE" in report
    assert "DEPSUMBR" in report
    assert "attributes_only_browse" in report
    assert "query_deposits" in report
    # PASSes stay in the grid; they are not expanded under Failures.
    assert "#### 001" not in report
    assert "#### 002" in report
