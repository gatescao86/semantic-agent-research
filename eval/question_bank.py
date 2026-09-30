"""Question bank loading. One directory per question.

    eval/questions/<question-id>/
        question.yaml
        ground_truth/*.sql        (optional)

A question's reference queries live beside it rather than in a shared
eval/ground_truth/ directory, so everything a question depends on is visible
in one place and `ground_truth_sql` paths stay local. Paths inside
question.yaml are written relative to the question's own directory and
resolved to absolute paths here, at load time — a criterion pointing at a
missing .sql file fails immediately, rather than surviving until the moment
someone tries to regenerate its expected value.

Both eval/run_eval.py and scripts/score_runs.py load through this module so
the two entry points cannot drift.
"""

from __future__ import annotations

from pathlib import Path

import yaml

QUESTIONS_DIR = Path(__file__).resolve().parent / "questions"


class QuestionBankError(ValueError):
    """Raised when a question directory is malformed or a referenced file is missing."""


def _resolve_sql_paths(question: dict, question_dir: Path) -> None:
    def resolve(raw: str, where: str) -> str:
        path = (question_dir / raw).resolve()
        if not path.is_file():
            raise QuestionBankError(
                f"[{question_dir.name}] {where} -> {raw!r} does not exist (looked in {path})"
            )
        return str(path)

    if question.get("ground_truth_sql_path"):
        question["ground_truth_sql_path"] = resolve(
            question["ground_truth_sql_path"], "ground_truth_sql_path"
        )

    for criterion in question.get("criteria") or []:
        if isinstance(criterion, dict) and criterion.get("ground_truth_sql"):
            criterion["ground_truth_sql"] = resolve(
                criterion["ground_truth_sql"], f"criteria[{criterion.get('id')}].ground_truth_sql"
            )


def load_question_dir(question_dir: Path, resolve_paths: bool = True) -> dict:
    path = question_dir / "question.yaml"
    if not path.is_file():
        raise QuestionBankError(f"[{question_dir.name}] has no question.yaml")

    with open(path) as f:
        question = yaml.safe_load(f)
    if not isinstance(question, dict):
        raise QuestionBankError(f"[{question_dir.name}] question.yaml must be a mapping")

    for required in ("id", "text", "category"):
        if not question.get(required):
            raise QuestionBankError(f"[{question_dir.name}] question.yaml is missing {required!r}")
    if question["id"] != question_dir.name:
        raise QuestionBankError(
            f"[{question_dir.name}] id is {question['id']!r} — it must match the directory name"
        )

    if resolve_paths:
        _resolve_sql_paths(question, question_dir)
    return question


def load_question_bank(resolve_paths: bool = True) -> list[dict]:
    """Every question, ordered by directory name."""
    dirs = sorted(d for d in QUESTIONS_DIR.iterdir() if d.is_dir())
    if not dirs:
        raise QuestionBankError(f"No question directories found in {QUESTIONS_DIR}")
    return [load_question_dir(d, resolve_paths=resolve_paths) for d in dirs]


def load_question(question_id: str, resolve_paths: bool = True) -> dict:
    question_dir = QUESTIONS_DIR / question_id
    if not question_dir.is_dir():
        available = ", ".join(sorted(d.name for d in QUESTIONS_DIR.iterdir() if d.is_dir()))
        raise QuestionBankError(f"Question {question_id!r} not found. Available: {available}")
    return load_question_dir(question_dir, resolve_paths=resolve_paths)


def agent_question_text(question: dict) -> str:
    """Question text the agent (and judge) actually see.

    `data_vintage` is extract metadata, not shown unless appended here.
    Without it, "latest" means live MAX(date) and gold values freeze a
    different week.
    """
    text = (question.get("text") or "").strip()
    vintage = (question.get("data_vintage") or "").strip()
    if not vintage:
        return text
    return (
        f"{text}\n\n"
        f"Data vintage: {vintage}. Treat “latest” as the last observation "
        f"on or before that extract cutoff — not a later date in the warehouse."
    )
