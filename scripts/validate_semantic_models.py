#!/usr/bin/env python
"""Schema-validate every semantic model YAML file (domain + unified).

Run: python scripts/validate_semantic_models.py
Exits non-zero and prints all errors found, rather than stopping at the first.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from semantic_models.schema import load_semantic_model, validate_references  # noqa: E402

MODEL_PATHS = sorted((REPO_ROOT / "semantic_models" / "domains").glob("*.yaml")) + sorted(
    (REPO_ROOT / "semantic_models" / "unified").glob("*.yaml")
)


def main() -> None:
    if not MODEL_PATHS:
        raise SystemExit("No semantic model YAML files found.")

    all_errors: list[str] = []
    for path in MODEL_PATHS:
        try:
            model = load_semantic_model(path)
        except Exception as exc:  # pydantic ValidationError or yaml error
            all_errors.append(f"{path}: failed to parse/validate — {exc}")
            continue
        all_errors.extend(validate_references(model))
        print(f"OK  {path.relative_to(REPO_ROOT)}  ({model.domain})")

    if all_errors:
        print()
        for err in all_errors:
            print(f"ERROR: {err}", file=sys.stderr)
        raise SystemExit(1)

    print(f"\nAll {len(MODEL_PATHS)} semantic model files valid.")


if __name__ == "__main__":
    main()
