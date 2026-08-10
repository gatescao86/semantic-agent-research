import pytest

from eval.calibration import compute_agreement
from eval.judge import DIMENSIONS_BY_CATEGORY, _build_output_schema


def test_perfect_agreement_meets_threshold():
    scores = [3, 4, 5, 2, 1, 3, 4, 5]
    result = compute_agreement(scores, list(scores))
    assert result.weighted_kappa == pytest.approx(1.0)
    assert result.meets_threshold


def test_inverted_scores_fail_threshold():
    judge = [1, 1, 5, 5]
    human = [5, 5, 1, 1]
    result = compute_agreement(judge, human)
    assert not result.meets_threshold


def test_mismatched_length_raises():
    with pytest.raises(ValueError):
        compute_agreement([1, 2, 3], [1, 2])


def test_too_few_scores_raises():
    with pytest.raises(ValueError):
        compute_agreement([1], [1])


@pytest.mark.parametrize("category,expected_dims", DIMENSIONS_BY_CATEGORY.items())
def test_judge_schema_matches_rubric_dimensions(category, expected_dims):
    schema = _build_output_schema(expected_dims)
    props = schema["schema"]["properties"]
    for dim in expected_dims:
        assert props[dim] == {"type": "integer", "minimum": 1, "maximum": 5}
    assert "justification" in props
    assert schema["schema"]["additionalProperties"] is False
