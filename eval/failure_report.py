"""Post-hoc failure analysis: criterion verdicts joined to the SQL/tool trace.

The judge is blinded to `generated_sql` on purpose. This module is the
other half: after scoring, walk each criterion across conditions and show
the queries that produced the answer, so a FAIL is inspectable the same
way a manual criteria-by-criteria review is.
"""

from __future__ import annotations

import re
from pathlib import Path

from agents.sql_tables import referenced_tables

PRIMARY_CONDITIONS = ("schema_only", "unified", "tool_routed")
_SQL_CLIP = 2000


def _as_dict(log) -> dict:
    if hasattr(log, "model_dump"):
        return log.model_dump()
    return dict(log)


def _clip_sql(sql: str) -> str:
    text = sql.strip()
    if len(text) > _SQL_CLIP:
        return text[:_SQL_CLIP] + "\n-- … truncated"
    return text


def _criterion_title(match_criteria: str) -> str:
    text = " ".join((match_criteria or "").split())
    if ". FAIL" in text:
        text = text.split(". FAIL", 1)[0]
    if text.lower().startswith("pass if "):
        text = text[8:]
    return text[:90]


def _short_table(name: str) -> str:
    return name.rsplit(".", 1)[-1]


def detect_trace_notes(sqls: list[str], run_log: dict | None = None) -> list[str]:
    """Cheap, deterministic tags for how the agent queried — not a second judge."""
    notes: list[str] = []
    seen: set[str] = set()

    def add(note: str) -> None:
        if note not in seen:
            seen.add(note)
            notes.append(note)

    for sql in sqls:
        upper = sql.upper()
        tables = {t.upper() for t in referenced_tables(sql)}
        if "ILIKE" in upper:
            add("ilike")
        if tables and all("ATTRIBUTES" in t for t in tables):
            add("attributes_only_browse")
        if re.search(r"SELECT\s+DISTINCT", sql, re.I) and any("TIMESERIES" in t for t in tables):
            add("timeseries_distinct")
        if "ILIKE" in upper and any("TIMESERIES" in t for t in tables) and not any(
            "ATTRIBUTES" in t for t in tables
        ):
            add("ilike_on_timeseries")

    log = run_log or {}
    if log.get("sql_execution_errors"):
        add("sql_execution_error")
    if log.get("hit_iteration_cap"):
        add("hit_iteration_cap")
    tools = log.get("tool_calls") or []
    if any(tc.get("is_error") for tc in tools):
        add("tool_error")
    return notes


def summarize_trace(run_log) -> dict:
    log = _as_dict(run_log)
    sqls = list(log.get("generated_sql") or [])
    tools = list(log.get("tool_calls") or [])
    tables: set[str] = set()
    for sql in sqls:
        tables |= referenced_tables(sql)
    return {
        "condition": log.get("experiment", ""),
        "run_id": log.get("run_id", ""),
        "n_tools": len(tools),
        "tool_sequence": [tc.get("tool_name", "?") for tc in tools],
        "sql": sqls,
        "tables": sorted(tables),
        "sql_errors": list(log.get("sql_execution_errors") or []),
        "hit_iteration_cap": bool(log.get("hit_iteration_cap")),
        "notes": detect_trace_notes(sqls, log),
        "coverage": None,
    }


def _verdict_cell(result: dict) -> str:
    verdict = result.get("verdict", "?")
    if verdict != "FAIL":
        return verdict
    reason = result.get("failure_reason") or "fail"
    claimed = result.get("claimed_value")
    expected = result.get("expected_value")
    if claimed is not None and expected is not None:
        return f"FAIL {reason} ({claimed} vs {expected})"
    return f"FAIL {reason}"


def _result_by_id(score: dict | None) -> dict[str, dict]:
    if not score:
        return {}
    return {r["id"]: r for r in score.get("criteria_results") or []}


def _render_trace(trace: dict) -> list[str]:
    lines = []
    tools = trace.get("tool_sequence") or []
    lines.append(f"- tools ({trace.get('n_tools', 0)}): {', '.join(tools) or '(none)'}")
    notes = trace.get("notes") or []
    if notes:
        lines.append(f"- notes: {', '.join(notes)}")
    tables = trace.get("tables") or []
    if tables:
        lines.append("- tables: " + ", ".join(_short_table(t) for t in tables))
    coverage = trace.get("coverage") or {}
    if coverage:
        missing = coverage.get("missing_domains") or []
        queried = coverage.get("domains_queried") or []
        lines.append(f"- domains queried: {', '.join(queried) or '(none)'}")
        if missing:
            lines.append(f"- missing required domains: {', '.join(missing)}")
    errors = trace.get("sql_errors") or []
    if errors:
        lines.append("- sql errors:")
        for err in errors:
            lines.append(f"  - {err}")
    if trace.get("hit_iteration_cap"):
        lines.append("- hit iteration cap")
    sqls = trace.get("sql") or []
    if not sqls:
        lines.append("- SQL: (none)")
        return lines
    for i, sql in enumerate(sqls, 1):
        lines.append("")
        lines.append(f"Query {i}:")
        lines.append("```sql")
        lines.append(_clip_sql(sql))
        lines.append("```")
    return lines


def _render_failure(condition: str, result: dict, trace: dict) -> list[str]:
    lines = [f"**{condition}** — {_verdict_cell(result)}"]
    if result.get("unit"):
        lines.append(f"- unit: {result['unit']}")
    notes = trace.get("notes") or []
    if notes:
        lines.append(f"- trace notes: {', '.join(notes)}")
    reasoning = (result.get("reasoning") or "").strip()
    if reasoning:
        lines.append(f"- judge: {reasoning}")
    return lines


def render_failure_report(
    records: list[dict],
    conditions: tuple[str, ...] = PRIMARY_CONDITIONS,
) -> str:
    """Markdown: per-question criterion grid, then each FAIL with judge + trace."""
    chunks: list[str] = ["# Failure analysis", ""]
    chunks.append(
        "Pass rate is the headline. This report is the criteria-by-criteria "
        "walkthrough: verdict, judge reasoning (why the *answer* failed), and "
        "the SQL/tool trace (what the agent actually queried)."
    )
    chunks.append("")

    for rec in records:
        question = rec["question"]
        qid = question["id"]
        trial = rec.get("trial", 0)
        criteria = question.get("criteria") or []
        chunks.append(f"## {qid} (trial {trial})")
        chunks.append("")

        rate_bits = []
        for condition in conditions:
            score = rec.get(f"{condition}_score")
            if not score:
                continue
            rate_bits.append(
                f"{condition} {score.get('n_passed')}/{score.get('n_criteria')} "
                f"({score.get('criterion_pass_rate')})"
            )
        if rate_bits:
            chunks.append("Pass rate: " + " · ".join(rate_bits))
            chunks.append("")

        header = "| id | check | " + " | ".join(conditions) + " |"
        chunks.append(header)
        chunks.append("|---|---|" + "|".join(["---"] * len(conditions)) + "|")
        for criterion in criteria:
            cid = criterion["id"]
            title = _criterion_title(criterion.get("match_criteria", ""))
            cells = []
            for condition in conditions:
                result = _result_by_id(rec.get(f"{condition}_score")).get(cid)
                cells.append(_verdict_cell(result) if result else "—")
            chunks.append(f"| {cid} | {title} | " + " | ".join(cells) + " |")
        chunks.append("")

        traces = {}
        for condition in conditions:
            if condition not in rec:
                continue
            trace = summarize_trace(rec[condition])
            score = rec.get(f"{condition}_score") or {}
            trace["coverage"] = score.get("domain_coverage") or {}
            traces[condition] = trace

        wrote_fail = False
        for criterion in criteria:
            cid = criterion["id"]
            failing = []
            for condition in conditions:
                result = _result_by_id(rec.get(f"{condition}_score")).get(cid)
                if result and result.get("verdict") == "FAIL":
                    failing.append((condition, result))
            if not failing:
                continue
            if not wrote_fail:
                chunks.append("### Failures")
                chunks.append("")
                wrote_fail = True
            title = _criterion_title(criterion.get("match_criteria", ""))
            chunks.append(f"#### {cid} — {title}")
            chunks.append("")
            for condition, result in failing:
                chunks.extend(_render_failure(condition, result, traces.get(condition, {})))
                chunks.append("")

        chunks.append("### Traces")
        chunks.append("")
        for condition in conditions:
            if condition not in traces:
                continue
            chunks.append(f"#### {condition}")
            chunks.extend(_render_trace(traces[condition]))
            chunks.append("")

    return "\n".join(chunks).rstrip() + "\n"


def write_failure_report(records: list[dict], path: Path, conditions: tuple[str, ...] = PRIMARY_CONDITIONS) -> str:
    report = render_failure_report(records, conditions=conditions)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report)
    return report
