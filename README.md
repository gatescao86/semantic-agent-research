# Evaluating Data Agent Architectures on Enterprise Questions

A controlled comparison of three agent architectures for answering business questions derived from real enterprise use cases.

Across all three conditions, the study holds constant:

- the underlying structured data, and

- the evaluation framework and criteria.

In every condition, the model writes the SQL. The tools only execute it.

| | schema_only | unified | tool_routed |
|---|---|---|---|
| Context | Physical schema (tables, columns, types) | Generated `unified_model.yaml` | Per-domain YAML via `get_semantic_model` |
| SQL execution | `run_sql` | `run_sql` | `query_<domain>`  |
| Cross-domain JOINS | Yes | Yes | No

## Comparisons

**schema_only vs. unified**
Tests the effect of adding semantic context while keeping the SQL interface the same.

**unified vs. tool_routed**
Tests a unified semantic model against decomposed domain tools using the same underlying semantic content.

## Evaluation & Scoring
See [`eval/eval_strategies.md`](eval/eval_strategies.md).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# fill in ANTHROPIC_API_KEY and SNOWFLAKE_*
```

This account enforces MFA, so Snowflake must use **key-pair** auth (password
auth fails non-interactively).

```bash
mkdir -p ~/.snowflake
openssl genrsa -out ~/.snowflake/rsa_key.p8 2048
openssl rsa -in ~/.snowflake/rsa_key.p8 -pubout -out ~/.snowflake/rsa_key.pub
chmod 600 ~/.snowflake/rsa_key.p8
grep -v -- '-----' ~/.snowflake/rsa_key.pub | tr -d '\n'; echo
```

In Snowsight (`SECURITYADMIN` / `ACCOUNTADMIN`):

```sql
ALTER USER <your_username> SET RSA_PUBLIC_KEY='<one-line public key>';
```

Set `SNOWFLAKE_PRIVATE_KEY_PATH` in `.env` (and `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE`
if the key is encrypted). Then:

```bash
python scripts/setup_snowflake.py   # read-only ping; diffs live tables vs YAML
pytest
```

## Run an agent

```bash
python -m agents.schema_only_agent "What is ONB's Evansville deposit share?"
python -m agents.unified_agent "What is ONB's Evansville deposit share?"
python -m agents.tool_router_agent "What is ONB's Evansville deposit share?"
```

Each write a `RunLog` to `runs/<run_id>.jsonl`.

## Run the eval

Needs Anthropic + Snowflake credentials.

```bash
python -m eval.run_eval --question fa-003          # one question, all three conditions
python -m eval.run_eval --question fa-003 --question fa-009
python -m eval.run_eval --pilot 5
python -m eval.run_eval                           # full bank
```

Re-score existing logs (no new agent runs):

```bash
python -m scripts.score_runs --question fa-003 \
  --runs runs/<schema_only>.jsonl runs/<unified>.jsonl runs/<tool_routed>.jsonl
```

`eval.run_eval` writes `runs/<prefix>-summary.csv`,
`runs/<prefix>-failure-report.md`, and `runs/<run_id>-scores.json`.
Cost/latency from logs already on disk:

```bash
python -m analysis.aggregate_results <run_id_prefix>
```

## Semantic models

Domain YAML in `semantic_models/domains/` is the source of truth. The unified
model and condition-1 catalog are generated:

```bash
python scripts/validate_semantic_models.py
python scripts/audit_semantic_models.py          # live Snowflake; needs .env
python scripts/generate_unified_model.py
python scripts/generate_unified_model.py --check
python scripts/generate_schema_catalog.py        # live columns; needs .env
```

Do not hand-edit `semantic_models/unified/unified_model.yaml`.

## Layout

```
config/             experiment.yaml, domains.yaml
semantic_models/    domain YAML, generated unified model, raw catalog
agents/             loop, executor, three condition wrappers, prompts
eval/               question bank, judge, run_eval, scoring
analysis/           cost/latency rollup
scripts/            Snowflake setup + generators
runs/               gitignored logs
```
