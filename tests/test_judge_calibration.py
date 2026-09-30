import pytest

from eval.calibration import compute_agreement
from eval.criteria import FAIL, PASS, Criterion, CriterionSchemaError, parse_criteria
from eval.judge import JUDGE_INSTRUCTIONS, _output_schema, build_user_content
from eval.scoring import within_tolerance


def test_perfect_agreement_meets_threshold():
    scores = [3, 4, 5, 2, 1, 3, 4, 5]
    result = compute_agreement(scores, list(scores))
    assert result.weighted_kappa == pytest.approx(1.0)
    assert result.meets_threshold


def test_inverted_scores_fail_threshold():
    result = compute_agreement([1, 1, 5, 5], [5, 5, 1, 1])
    assert not result.meets_threshold


def test_mismatched_length_raises():
    with pytest.raises(ValueError):
        compute_agreement([1, 2, 3], [1, 2])


def test_too_few_scores_raises():
    with pytest.raises(ValueError):
        compute_agreement([1], [1])


def _question(items):
    return {"id": "q-1", "text": "?", "category": "executive", "criteria": items}


def test_parses_minimal_criterion():
    [c] = parse_criteria(_question([{"id": "001", "match_criteria": "PASS if it names the largest holder. FAIL if not."}]))
    assert c.id == "001"
    assert not c.is_numeric


def test_required_facts_key_is_rejected():
    with pytest.raises(CriterionSchemaError, match="renamed to `criteria`"):
        parse_criteria({"id": "q-1", "required_facts": [{"id": "a", "match_criteria": "x"}]})


def test_bare_string_criteria_rejected():
    with pytest.raises(CriterionSchemaError, match="Bare strings"):
        parse_criteria(_question(["Reports deposit market share"]))


@pytest.mark.parametrize(
    "items,fragment",
    [
        ([{"id": "a", "match_criteria": "x", "requred_facts": 1}], "unknown key"),
        ([{"id": "a", "match_criteria": "x"}, {"id": "a", "match_criteria": "y"}], "duplicate id"),
        ([{"id": "a", "match_criteria": "x", "value": 1}], "no `unit`"),
        ([{"id": "a", "match_criteria": "x", "value": 1, "unit": "furlongs"}], "unrecognized unit"),
        (
            [{"id": "a", "match_criteria": "x", "value": 1, "unit": "percent", "tolerance": 0.1, "tolerance_abs": 1}],
            "both",
        ),
        ([{"id": "a", "match_criteria": "x", "tolerance": 0.1}], "no `value`"),
        ([{"id": "a"}], "missing required key"),
        ([{"id": 1, "match_criteria": "x"}], "quoted string"),
    ],
)
def test_schema_violations_fail_loudly(items, fragment):
    with pytest.raises(CriterionSchemaError, match=fragment):
        parse_criteria(_question(items))


def test_unset_default_tolerance_raises_rather_than_defaulting():
    items = [{"id": "a", "match_criteria": "x", "value": 10, "unit": "percent"}]
    with pytest.raises(CriterionSchemaError, match="default_tolerance"):
        parse_criteria(_question(items), default_tolerance="TODO")

    [c] = parse_criteria(_question(items), default_tolerance=0.01)
    assert c.tolerance == 0.01


@pytest.mark.parametrize(
    "claimed,expected,rel,abs_,ok",
    [
        (2138000, 2140000, 0.01, None, True),
        (1900000, 2140000, 0.01, None, False),
        (39.2, 39.16, None, 1.0, True),
        (36.0, 39.16, None, 1.0, False),
        (5.0, 5.0, None, None, True),
    ],
)
def test_within_tolerance(claimed, expected, rel, abs_, ok):
    assert within_tolerance(claimed, expected, rel, abs_) is ok


def test_judge_instructions_exclude_spec_sections_the_judge_should_not_see():
    for leaked in ("Validity Gates", "Known Limitations", "self-preference", "McNemar"):
        assert leaked not in JUDGE_INSTRUCTIONS


def test_numeric_criterion_asks_for_claimed_value():
    c = Criterion(
        id="a",
        match_criteria="PASS if it reports deposits. FAIL if omitted.",
        value=1.0,
        unit="USD_thousands",
        tolerance=0.01,
    )
    content = build_user_content("Q?", "A.", c)
    assert "claimed_value" in content and "USD_thousands" in content
    schema = _output_schema(numeric=True)["schema"]["properties"]
    assert schema["verdict"]["enum"] == [PASS, FAIL]
    assert "claimed_value" in schema


def test_qualitative_criterion_omits_claimed_value():
    content = build_user_content(
        "Q?", "A.", Criterion(id="a", match_criteria="PASS if it names the leader. FAIL if not.")
    )
    assert "claimed_value" not in content
    assert "claimed_value" not in _output_schema(numeric=False)["schema"]["properties"]
