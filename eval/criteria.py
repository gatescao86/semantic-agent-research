"""Criterion schema and validation. See eval/eval_strategies.md § Criterion Schema.
"""

from __future__ import annotations

from dataclasses import dataclass

ALLOWED_KEYS = {
    "id",
    "match_criteria",
    "value",
    "unit",
    "tolerance",
    "tolerance_abs",
    "ground_truth_sql",
}

ALLOWED_UNITS = {
    "USD",
    "USD_thousands",
    "percent",
    "percentage_points",
    "count",
    "ratio",
    "year",
}

PASS = "PASS"
FAIL = "FAIL"


class CriterionSchemaError(ValueError):
    """Raised when a question's `criteria` block is malformed."""


@dataclass(frozen=True)
class Criterion:
    id: str
    match_criteria: str
    value: float | None = None
    unit: str | None = None
    tolerance: float | None = None
    tolerance_abs: float | None = None
    ground_truth_sql: str | None = None

    @property
    def is_numeric(self) -> bool:
        return self.value is not None


def parse_criteria(question: dict, default_tolerance: float | None = None) -> list[Criterion]:
    """Parse and validate one question's `criteria` block.
    """
    qid = question.get("id", "<no id>")
    if "required_facts" in question:
        raise CriterionSchemaError(
            f"[{qid}] `required_facts` has been renamed to `criteria`. Rename the key."
        )
    raw = question.get("criteria")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise CriterionSchemaError(f"[{qid}] criteria must be a list, got {type(raw).__name__}")

    criteria: list[Criterion] = []
    seen_ids: set[str] = set()

    for index, item in enumerate(raw):
        where = f"[{qid}] criteria[{index}]"
        if not isinstance(item, dict):
            raise CriterionSchemaError(
                f"{where} must be a mapping with at least `id` and `match_criteria`. "
                "Bare strings are the pre-v2 format and are no longer accepted."
            )

        unknown = set(item) - ALLOWED_KEYS
        if unknown:
            raise CriterionSchemaError(
                f"{where} has unknown key(s) {sorted(unknown)}. Allowed: {sorted(ALLOWED_KEYS)}"
            )
        for required in ("id", "match_criteria"):
            if not item.get(required):
                raise CriterionSchemaError(f"{where} is missing required key {required!r}")

        cid_raw = item["id"]
        if not isinstance(cid_raw, str):
            raise CriterionSchemaError(
                f"{where} id must be a quoted string — YAML treats 001 as an "
                f"integer (got {cid_raw!r}). Write id: \"001\"."
            )
        cid = cid_raw
        if cid in seen_ids:
            raise CriterionSchemaError(f"{where} has duplicate id {cid!r} within this question")
        seen_ids.add(cid)

        value = item.get("value")
        unit = item.get("unit")
        tolerance = item.get("tolerance")
        tolerance_abs = item.get("tolerance_abs")

        if value is not None and unit is None:
            raise CriterionSchemaError(f"{where} sets `value` but no `unit`")
        if unit is not None and unit not in ALLOWED_UNITS:
            raise CriterionSchemaError(
                f"{where} has unrecognized unit {unit!r}. Allowed: {sorted(ALLOWED_UNITS)}"
            )
        if tolerance is not None and tolerance_abs is not None:
            raise CriterionSchemaError(f"{where} sets both `tolerance` and `tolerance_abs`")
        if value is None and (tolerance is not None or tolerance_abs is not None):
            raise CriterionSchemaError(f"{where} sets a tolerance but no `value` to compare against")

        if value is not None and tolerance is None and tolerance_abs is None:
            if not isinstance(default_tolerance, (int, float)):
                raise CriterionSchemaError(
                    f"{where} sets no tolerance and scoring.default_tolerance is not a number "
                    f"(got {default_tolerance!r}). Pre-register it in config/experiment.yaml."
                )
            tolerance = float(default_tolerance)

        criteria.append(
            Criterion(
                id=cid,
                match_criteria=" ".join(str(item["match_criteria"]).split()),
                value=None if value is None else float(value),
                unit=unit,
                tolerance=None if tolerance is None else float(tolerance),
                tolerance_abs=None if tolerance_abs is None else float(tolerance_abs),
                ground_truth_sql=item.get("ground_truth_sql"),
            )
        )

    return criteria
