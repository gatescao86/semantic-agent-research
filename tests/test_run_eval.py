from pathlib import Path

import pytest
import yaml

from eval.criteria import parse_criteria
from eval.question_bank import (
    QUESTIONS_DIR,
    QuestionBankError,
    agent_question_text,
    load_question,
    load_question_bank,
)
from eval.run_eval import PRIMARY_CONDITIONS, aggregate, select_questions
from logging_.schema import RoutingDecision, RunLog


def test_load_question_bank_ids():
    questions = load_question_bank()
    ids = [q["id"] for q in questions]
    dirs = sorted(d.name for d in QUESTIONS_DIR.iterdir() if d.is_dir())
    assert ids == dirs
    by_id = {q["id"]: q["category"] for q in questions}
    assert (
        by_id["ex-001"]
        == by_id["ex-002"]
        == by_id["ex-003"]
        == by_id["ex-004"]
        == "executive"
    )
    assert all(by_id[i] == "factual" for i in by_id if i.startswith("fa-"))
    assert "fa-001" in by_id and "fa-012" in by_id


def test_every_question_parses_criteria():
    for question in load_question_bank():
        criteria = parse_criteria(question)
        assert len(criteria) >= 1, question["id"]
        assert all(c.id != "guard" for c in criteria), question["id"]


def test_factual_questions_have_numeric_gold():
    for question in load_question_bank():
        if question["category"] != "factual":
            continue
        assert question.get("ground_truth_sql_path"), question["id"]
        numeric = [c for c in parse_criteria(question) if c.is_numeric]
        assert len(numeric) == 1, question["id"]
        assert numeric[0].unit
        assert Path(numeric[0].ground_truth_sql).is_file()


def test_every_question_directory_loads():
    dirs = sorted(d.name for d in QUESTIONS_DIR.iterdir() if d.is_dir())
    assert dirs, "no question directories found"
    for name in dirs:
        assert load_question(name)["id"] == name


def test_ground_truth_sql_paths_resolve_to_real_files():
    for question in load_question_bank():
        path = question.get("ground_truth_sql_path")
        if path:
            assert Path(path).is_file(), f"{question['id']} ground_truth_sql_path -> {path}"
        for criterion in question.get("criteria") or []:
            path = criterion.get("ground_truth_sql")
            if path:
                assert Path(path).is_file(), f"{question['id']}/{criterion['id']} -> {path}"


def test_missing_question_names_the_alternatives():
    with pytest.raises(QuestionBankError, match="Available:"):
        load_question("does-not-exist")


def test_id_must_match_directory_name(tmp_path, monkeypatch):
    question_dir = tmp_path / "q-001"
    question_dir.mkdir()
    (question_dir / "question.yaml").write_text(
        yaml.safe_dump({"id": "q-002", "text": "?", "category": "executive"})
    )
    monkeypatch.setattr("eval.question_bank.QUESTIONS_DIR", tmp_path)
    with pytest.raises(QuestionBankError, match="must match the directory name"):
        load_question("q-001")


def test_dangling_ground_truth_path_fails_loudly(tmp_path, monkeypatch):
    question_dir = tmp_path / "q-001"
    question_dir.mkdir()
    (question_dir / "question.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "q-001",
                "text": "?",
                "category": "executive",
                "criteria": [
                    {"id": "001", "match_criteria": "x", "ground_truth_sql": "ground_truth/gone.sql"}
                ],
            }
        )
    )
    monkeypatch.setattr("eval.question_bank.QUESTIONS_DIR", tmp_path)
    with pytest.raises(QuestionBankError, match="does not exist"):
        load_question("q-001")


def test_agent_question_text_appends_extract_vintage():
    q = load_question("fa-001")
    posed = agent_question_text(q)
    assert q["text"].strip() in posed
    assert "2026-05-20" in posed
    assert "Data vintage:" in posed
    assert posed != q["text"].strip()


def test_agent_question_text_without_vintage_is_plain_text():
    posed = agent_question_text({"text": "How many branches?"})
    assert posed == "How many branches?"


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


def test_aggregate_three_conditions_pass_rate_and_cost():
    record = {
        "question": {"id": "q1", "category": "factual"},
        "trial": 0,
        "schema_only": _fake_run_log("schema_only"),
        "unified": _fake_run_log("unified"),
        "tool_routed": _fake_run_log("tool_routed"),
        "schema_only_score": {
            "criterion_pass_rate": 0.5,
            "n_passed": 1,
            "n_criteria": 2,
            "all_pass": False,
        },
        "unified_score": {
            "criterion_pass_rate": 1.0,
            "n_passed": 2,
            "n_criteria": 2,
            "all_pass": True,
        },
        "tool_routed_score": {
            "criterion_pass_rate": 0.5,
            "n_passed": 1,
            "n_criteria": 2,
            "all_pass": False,
        },
    }
    summary = aggregate([record])
    assert set(summary) == set(PRIMARY_CONDITIONS)
    assert summary["unified"]["criterion_pass_rate_pooled"] == 1.0
    assert summary["tool_routed"]["criterion_pass_rate_pooled"] == 0.5
    assert summary["schema_only"]["criterion_pass_rate_pooled"] == 0.5
    assert summary["unified"]["all_pass_rate"] == 1.0
    assert summary["tool_routed"]["all_pass_rate"] == 0.0
    assert summary["unified"]["total_input_tokens"] == 100
    assert summary["unified"]["estimated_cost_usd"] is not None
    assert "routing_accuracy" not in summary["unified"]
    assert "mean_judge_scores" not in summary["unified"]


def test_aggregate_without_scores_leaves_pass_rates_none():
    record = {
        "question": {"id": "q1", "category": "executive"},
        "trial": 0,
        "schema_only": _fake_run_log("schema_only"),
        "unified": _fake_run_log("unified"),
        "tool_routed": _fake_run_log("tool_routed"),
    }
    summary = aggregate([record])
    assert summary["unified"]["criterion_pass_rate_pooled"] is None
    assert summary["tool_routed"]["all_pass_rate"] is None


def test_select_questions_by_id():
    bank = load_question_bank()
    selected = select_questions(bank, ["ex-002"], None)
    assert [q["id"] for q in selected] == ["ex-002"]


def test_select_questions_rejects_unknown_id():
    with pytest.raises(SystemExit, match="Unknown question"):
        select_questions(load_question_bank(), ["no-such-question"], None)
