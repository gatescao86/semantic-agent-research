from eval.run_eval import aggregate, compare_result_sets, load_question_bank
from logging_.schema import RoutingDecision, RunLog


def test_load_question_bank_includes_all_categories():
    questions = load_question_bank()
    categories = {q["category"] for q in questions}
    assert categories == {"single_domain", "cross_domain", "executive"}
    ids = [q["id"] for q in questions]
    assert len(ids) == len(set(ids)), "question IDs must be unique across files"


def test_compare_result_sets_ignores_row_order():
    agent_rows = [(2, "b"), (1, "a")]
    ref_rows = [(1, "a"), (2, "b")]
    result = compare_result_sets(agent_rows, ref_rows)
    assert result["exact_match"] is True
    assert result["row_count_match"] is True


def test_compare_result_sets_float_tolerance():
    agent_rows = [(1.0000001,)]
    ref_rows = [(1.0000002,)]
    result = compare_result_sets(agent_rows, ref_rows)
    assert result["exact_match"] is True  # rounds to 6 decimal places


def test_compare_result_sets_detects_mismatch():
    result = compare_result_sets([(1, "a")], [(1, "b")])
    assert result["exact_match"] is False
    assert result["row_count_match"] is True


def _fake_run_log(experiment: str, domains: list[str] | None = None) -> RunLog:
    return RunLog(
        run_id="test",
        experiment=experiment,
        model_id="claude-opus-5",
        effort="high",
        thinking_mode="adaptive",
        question_id="q1",
        question_category="single_domain",
        question_text="q",
        trial_index=0,
        routing_decision=(
            RoutingDecision(domains=domains, reasoning="r", ambiguous=False, latency_ms=1)
            if domains is not None
            else None
        ),
        final_answer_text="answer",
        total_input_tokens=100,
        total_output_tokens=50,
        wall_clock_ms=1000,
        timestamp="2026-01-01T00:00:00Z",
    )


def test_aggregate_computes_routing_accuracy():
    record = {
        "question": {
            "id": "q1",
            "category": "single_domain",
            "expected_domains": {"minimum_required": ["geography"], "optional_enrichment": []},
        },
        "trial": 0,
        "unified": _fake_run_log("unified"),
        "routed": _fake_run_log("routed", domains=["geography", "demographics"]),
        "unified_judge_scores": {"correctness": 5},
        "routed_judge_scores": {"correctness": 4},
    }
    summary = aggregate([record])
    assert summary["routed"]["routing_accuracy"] == 1.0
    assert summary["unified"]["mean_judge_scores"]["correctness"] == 5
    assert summary["routed"]["mean_judge_scores"]["correctness"] == 4
    assert summary["unified"]["total_input_tokens"] == 100


def test_aggregate_routing_accuracy_penalizes_missing_required_domain():
    record = {
        "question": {
            "id": "q1",
            "category": "single_domain",
            "expected_domains": {"minimum_required": ["geography"], "optional_enrichment": []},
        },
        "trial": 0,
        "unified": _fake_run_log("unified"),
        "routed": _fake_run_log("routed", domains=["demographics"]),
    }
    summary = aggregate([record])
    assert summary["routed"]["routing_accuracy"] == 0.0
