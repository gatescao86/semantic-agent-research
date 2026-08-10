# Semantic Agent Study

A research prototype comparing **unified vs. decomposed semantic-layer
architectures** for enterprise AI data agents. Not a production application —
a controlled experiment. Full design rationale, confounders considered, and
milestone tracking: see [`PLAN.md`](./PLAN.md).

Two experiments run against the same underlying Snowflake data and the same
frozen question bank:

- **Experiment A (unified)** — one agent with the full, generated unified
  semantic model.
- **Experiment B (routed)** — an LLM router selects domain(s) per question;
  a specialist agent runs with only the selected domain's semantic model.

Both use the *same* shared agent-loop implementation (`agents/loop.py`), so
the only variable between conditions is semantic architecture, not
incidental implementation differences.

A second track (**Phase 1**, not yet built — see `PLAN.md` § Phase 1)
repeats the same comparison on Snowflake Cortex Analyst, as a directional
replication check against a managed product.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# fill in ANTHROPIC_API_KEY and SNOWFLAKE_* — see .env.example for what's needed
```

### Verify Snowflake access (M0)

```bash
python scripts/setup_snowflake.py
```

Connects read-only, lists tables in the `SNOWFLAKE_PUBLIC_DATA_FREE` schema,
and diffs them against what `semantic_models/domains/*.yaml` assumes. **The
domain YAML files were authored from public Snowflake documentation, not a
live account** — table/column names need correcting against this script's
output before trusting them. See `PLAN.md` → Implementation status for what's
still open (the FDIC/CFPB/HMDA dataset specifics in particular).

## Semantic models

```bash
# Validate all domain + unified semantic model YAML files
python scripts/validate_semantic_models.py

# Regenerate the unified model from the domain files after editing any of them
python scripts/generate_unified_model.py

# CI-style check: fails if the checked-in unified model is stale
python scripts/generate_unified_model.py --check
```

The unified model is **generated, not hand-authored** — see
`semantic_models/schema.py` and `PLAN.md` §4 for why.

## Running an agent manually

```bash
python -m agents.unified_agent "What was the mortgage rate trend last quarter?"
python -m agents.routed_agent "What was the mortgage rate trend last quarter?"
```

Both log a full `RunLog` (routing decision if applicable, tool calls,
generated SQL, token usage, latency) to `runs/<run_id>.jsonl`.

## Tests

```bash
pytest
```

Covers semantic model schema validation, the cross-domain-key
promotion/dropping logic in `merge_domain_models`, the SQL read-only
guardrail, the router's structured-output parsing (mocked, no live API
calls), judge/calibration math, and the eval-aggregation helpers.

## Running the eval harness

```bash
# Pilot: first 5 questions through both experiments (M3 exit criteria)
python -m eval.run_eval --pilot 5

# Full frozen question bank
python -m eval.run_eval
```

Requires live `ANTHROPIC_API_KEY` and `SNOWFLAKE_*` credentials. **The
question banks in `eval/questions/*.yaml` are starter placeholders**, not
the frozen `eval-v1` bank the plan calls for — see the header comment in
each file. Author and freeze the real bank (≥15 single-domain, ≥15
cross-domain, ≥10 executive) before treating results as meaningful.

Before trusting judge-only scores on a full run, calibrate against a
human-labeled subset:

```bash
python -m eval.calibration path/to/paired_scores.json
```

Gate: judge/human agreement must clear `κ ≥ 0.6`
(`config/experiment.yaml` → `judge.calibration_kappa_threshold`) or the
rubric needs revision first — see `eval/judge_rubric.md`.

## Analysis

```bash
python -m analysis.aggregate_results <run_id_prefix>
```

Rolls up persisted `runs/*.jsonl` logs into a cost/latency/routing-accuracy
comparison table between the two experiments. `<run_id_prefix>` matches
what `eval/run_eval.py` printed (reads
`runs/<prefix>-unified.jsonl` and `runs/<prefix>-routed.jsonl`).

## Repository layout

See `PLAN.md` §1 for the full annotated layout and the rationale behind it.

```
config/             frozen experiment + domain config
semantic_models/     domain YAMLs (source of truth) + generated unified model
agents/              shared loop, tools, sql_executor, router, unified/routed agents
logging_/            RunLog schema + JSONL sink
eval/                question banks, ground truth, LLM judge, run orchestration
analysis/            cost/latency/comparison rollups
scripts/             setup + semantic-model generation/validation
tests/
runs/                gitignored — JSONL logs land here
```
