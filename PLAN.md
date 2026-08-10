# Semantic Agent Study — Development Plan

## Context

The user is building an independent research project to study how semantic-layer
architecture (a single unified semantic model vs. multiple decomposed domain
models) affects the performance of enterprise AI data agents that translate
natural-language business questions into SQL. This is a controlled research
experiment, not a production build — the brief explicitly asks to prioritize
experimental validity over implementation complexity, and to challenge
assumptions and identify confounders rather than assume either architecture is
superior.

The repository is currently empty (no code, no commits) — this is a greenfield
design.

**Dataset correction (important divergence from the initial brief draft):**
the user's intended dataset is the Snowflake Marketplace listing *"Snowflake
Public Data (Free)"* (`GZTSZ290BV255`, provider "Snowflake Public Data
Products", database `SNOWFLAKE_PUBLIC_DATA_FREE`). This is **not** the
generic `SNOWFLAKE_SAMPLE_DATA` (TPC-H/TPC-DS) database initially assumed.
Per Snowflake's own docs (`data-docs.snowflake.com`), it is a foundational
layer of public-domain data built around standardized index + timeseries
tables, covering:

- **Geography** — `GEOGRAPHY_INDEX` / `GEOGRAPHY_RELATIONSHIPS`: states,
  counties, cities/CBSAs, zip codes, census block groups (Census Bureau +
  Data Commons + Statistics Canada).
- **Financial & economic indicators** — timeseries covering GDP, unemployment,
  CPI, retail sales, consumer credit, interest rates, **mortgage rates**, and
  **banking-sector indicators**, by geography.
- **Demographics** — Census ACS social/economic/housing/demographic stats by
  geography.
- **Company / competitor data** — `COMPANY_INDEX` (~100k public + private
  companies, OpenFIGI/PermID) joined to full **SEC EDGAR** history (10-K,
  10-Q, 8-K, 13F, etc.), with `SEC_METRICS_TIMESERIES` (parsed XBRL segment
  financials) and `SEC_CORPORATE_REPORT_ITEM_ATTRIBUTES`. Public **bank
  holding companies** report deposits, loans, and other balance-sheet line
  items in their 10-K/10-Q XBRL data — this is the only way "deposits" and
  "lending" data actually exist in this dataset, at company-filing grain,
  not customer/account grain.
- Government spending, NAICS industry classification index.

**What this means for the brief's domain list:** "geographic markets,"
"economic indicators," and "competitor information" are directly and well
supported. "Customers," "accounts," "deposits," "transactions," "lending,"
"mortgages," "branches" as *customer/account-level transactional* domains are
**not available** — no public dataset exposes real bank customer or account
data. The closest honest equivalent is company-level: individual public bank
holding companies' reported deposits/loans via SEC filings. The plan
reframes the study around this — a **regional bank competitive-intelligence
study** (economic conditions + demographics + public bank holding company
filings, joined by geography) — rather than fabricating customer-level
banking data. This keeps every number in the dataset real and traceable to a
public source, which matters for an experiment whose entire premise is
measuring SQL/semantic correctness against ground truth.

The user confirmed: LLM provider = **Anthropic Claude API** (direct, no
provider abstraction layer); eval quality scoring = **LLM-as-judge with a
rubric, calibrated against a human-labeled subset**; judge model = **same
tier as the agents** (relying on blinding + human calibration to catch
self-preference bias, not a pricier judge tier); **3 trials per question**
per experiment to average out LLM non-determinism.

**Two-phase addition (added after initial build started):** the user asked
to run the study in two phases against two different platforms — Phase 1 on
**Snowflake Cortex Analyst** (Snowflake's managed text-to-SQL product,
registering multiple Semantic Views + its built-in Routing Mode as the
"decomposed" condition, one combined Semantic View as "unified"), and
Phase 2 on the **custom Claude-based agent** already being built (§1–§9
below, largely unchanged). See "Two-Phase Experimental Design" and "Phase 1:
Cortex Analyst" below for what this adds and why it does *not* collapse into
a single four-way comparison. The `FDIC`/`CFPB`/`HMDA` dataset correction the
user flagged (real institution-level deposits/loans/mortgage-origination
data, not the SEC-filing workaround originally assumed) still needs to be
applied to `semantic_models/domains/*.yaml` — see Implementation status.
Because Phase 1's semantic views are generated from that same YAML source of
truth (§P1.2), fixing it once benefits both phases.

---

## Two-phase experimental design

**Phase 2 (custom agent, frontier model)** is the core ablation study from
the original brief: one shared agent-loop implementation, semantic
architecture as the only variable, full instrumentation. This is what §1–§9
below describe, and what's already partially built (agent loop, tools,
sql_executor, logging).

**Phase 1 (Cortex Analyst)** repeats the *same* unified-vs-decomposed
question on Snowflake's managed product, using the same underlying data, the
same frozen question bank, the same ground truth, and the same LLM judge.
See "Phase 1: Cortex Analyst" below.

**Why two phases instead of one four-way comparison:** Cortex Analyst and
the custom agent differ in far more than semantic architecture — different
underlying model (Snowflake's Arctic-Text2SQL-R2 vs. Claude), different
routing mechanism (Cortex's opaque internal routing vs. our own LLM router),
different retrieval (Cortex's Verified Query Repository exemplar-matching
vs. none), and different logging granularity (Cortex Analyst exposes far
less internal reasoning than code we write ourselves). Comparing "Cortex
Analyst unified" against "custom agent decomposed" would conflate platform,
model, and architecture into one number — meaningless for answering
H1/H2/H3.

**What each phase can and cannot claim:**
- *Within* each phase (Cortex unified vs. Cortex decomposed; custom-agent
  unified vs. custom-agent decomposed): a controlled comparison, same rigor
  rules as the original plan — model/config pinned, only semantic
  architecture varies.
- *Across* phases: only a **directional replication check** — "does the
  same qualitative pattern (e.g. decomposition helping bounded questions,
  hurting cross-domain synthesis) show up on both platforms?" This is
  evidence about generality, not a causal "platform X beats platform Y"
  claim, and the eventual writeup must not present it as the latter.
- **What stays constant across both phases** (this is what makes the
  replication meaningful at all): the underlying Snowflake data, the frozen
  question bank (`eval/questions/*.yaml`), the ground-truth SQL for
  category 1, the LLM judge and rubric, and — critically — the semantic
  *content* (entities/metrics/relationships) defined once in
  `semantic_models/domains/*.yaml` and translated into each platform's own
  representation (§P1.2), not re-authored from scratch per phase.

---

## 1. Repository structure — Phase 2 (custom agent)

```
semantic-agent-study/
├── README.md                       # research framing, how to reproduce
├── pyproject.toml                  # anthropic, snowflake-connector-python, pyyaml,
│                                    #   pandas, pydantic, python-dotenv, rich, pytest
├── .env.example                    # SNOWFLAKE_*, ANTHROPIC_API_KEY (never committed)
├── config/
│   ├── experiment.yaml             # frozen run config: model id, effort, n_trials, seeds
│   └── domains.yaml                # maps logical domain name -> DB objects + router label
├── semantic_models/
│   ├── unified/
│   │   └── unified_model.yaml      # GENERATED from domain files, not hand-authored
│   └── domains/
│       ├── geography.yaml
│       ├── economic_indicators.yaml
│       ├── demographics.yaml
│       └── competitor_intelligence.yaml   # company index + SEC filings
├── agents/
│   ├── tools.py                    # get_semantic_model, run_sql tool defs (shared)
│   ├── sql_executor.py             # single shared Snowflake execution wrapper
│   ├── loop.py                     # ONE shared agent-loop implementation
│   ├── unified_agent.py            # loop.py + full semantic model
│   ├── router.py                   # Experiment B: LLM-based domain classifier
│   ├── routed_agent.py             # loop.py + domain-scoped semantic model(s)
│   └── prompts/
│       ├── shared_system_core.md   # identical boilerplate in BOTH agents
│       ├── unified_system.md
│       ├── routed_system.md
│       └── router_system.md
├── logging_/
│   ├── schema.py                   # pydantic RunLog / ToolCallLog models
│   └── sink.py                     # JSONL writer, one file per run_id
├── eval/
│   ├── questions/
│   │   ├── single_domain.yaml
│   │   ├── cross_domain.yaml
│   │   └── executive.yaml
│   ├── ground_truth/*.sql          # hand-verified reference queries (category 1)
│   ├── judge.py                    # LLM-as-judge harness
│   ├── judge_rubric.md             # frozen, versioned rubric
│   ├── calibration.py              # judge-vs-human agreement (Cohen's kappa)
│   └── run_eval.py                 # orchestrates full eval run
├── analysis/
│   ├── aggregate_results.py
│   └── notebooks/results_analysis.ipynb
├── runs/                            # gitignored; JSONL logs per run
├── scripts/
│   ├── setup_snowflake.py          # verifies read-only access, no mutation
│   ├── generate_unified_model.py   # concatenates domain YAMLs -> unified_model.yaml
│   └── validate_semantic_models.py
└── tests/
    ├── test_semantic_model_schema.py
    ├── test_router.py
    ├── test_sql_executor.py
    └── test_judge_calibration.py
```

(`logging_` avoids shadowing Python's stdlib `logging` module.)

**Key validity decision:** `agents/loop.py` is the *single* shared agent-loop
implementation used by both `unified_agent.py` and `routed_agent.py` — they
differ only in which semantic model(s) get injected and whether a routing
step precedes the loop. If the two experiments had independently written
loops, any measured performance delta would be confounded by incidental
implementation differences (retry logic, error handling, prompt phrasing),
not just semantic architecture.

---

## 2. System architecture

```
                  Question Set (single-domain / cross-domain / executive)
                                    │
           ┌────────────────────────┴────────────────────────┐
      Experiment A                                     Experiment B
  ┌─────────────────────┐                    ┌───────────────────────────┐
  │  Unified Agent Loop  │                    │  Router (Claude, same     │
  │  tools: get_semantic │                    │  model, classification)   │
  │  _model (full),      │                    └─────────────┬─────────────┘
  │  run_sql             │                                  │ domain(s)
  └──────────┬───────────┘                                  ▼
             │                                ┌───────────────────────────┐
             │                                │  Specialist Agent Loop     │
             │                                │  (SAME loop code, scoped   │
             │                                │  to routed domain model(s))│
             │                                └──────────────┬──────────────┘
             └───────────────────┬────────────────────────────┘
                                 ▼
                   Shared SQL Executor (one Snowflake conn pool,
                   one read-only role, same warehouse for both)
                                  ▼
                   Structured Logger (JSONL): routing decision, SQL,
                   result, tokens, latency
                                  ▼
                   Eval Harness: ground-truth diff (cat. 1),
                   LLM-judge, blinded (cat. 2/3)
```

Constants held fixed across A and B, so the only thing that varies is
semantic architecture: model ID/version (pinned), `effort` level, thinking
config, underlying data (same database, same warehouse), SQL executor code
path, question set (verbatim identical), judge (identical prompt/model),
trial count, max tool-call iterations.

---

## 3. Data ingestion strategy

This is a **read-only access layer**, not a pipeline — `SNOWFLAKE_PUBLIC_DATA_FREE`
is queried directly, nothing is copied or mutated, which guarantees Experiment
A and B see byte-identical data.

1. `scripts/setup_snowflake.py` connects with the user's account, confirms
   read access to the relevant schemas (geography, financial/economic
   indicators, demographics, company/SEC), and prints row counts as a smoke
   test.
2. If friendlier joins are needed (e.g. pre-filtering SEC filings to bank
   holding companies via NAICS/SIC code, or pre-joining geography to a
   specific metro area like Evansville, IN for the executive-question
   category), define them as SQL **views** in `sql/views/*.sql`, applied once
   via a setup script. Both experiments' semantic models must reference the
   *same* view set — never let Experiment A and B see different view
   definitions, or that becomes a confound independent of architecture.
3. Identify and freeze a small set of target companies/geographies up front
   (e.g. 5–10 public regional bank holding companies with a presence in 2–3
   named metro areas) so questions in the eval bank are answerable and
   ground-truth-verifiable, rather than open-ended over the full ~100k
   company universe.

---

## 4. Semantic model representation

One YAML schema, shared by domain files and the generated unified file
(same validator for both), inspired by dbt Semantic Layer / Cube but
minimal. **The unified model is generated by concatenating the domain
files** (`scripts/generate_unified_model.py`), never hand-authored — this
controls for "semantic model authoring effort" as a hidden variable: if the
unified model were separately hand-crafted, it could be better-written than
the sum of the domain parts for reasons unrelated to architecture.

```yaml
# semantic_models/domains/competitor_intelligence.yaml
domain: competitor_intelligence
description: >
  Public bank holding companies: identity, and reported financials
  (deposits, loans, revenue) from SEC filings.

entities:
  - name: company
    table: SNOWFLAKE_PUBLIC_DATA_FREE.CYBERSYN.COMPANY_INDEX
    primary_key: company_id
    description: A public company, filtered to bank holding companies (NAICS 522110).
  - name: sec_report
    table: SNOWFLAKE_PUBLIC_DATA_FREE.CYBERSYN.SEC_REPORT_INDEX
    primary_key: adsh
  - name: sec_metric
    table: SNOWFLAKE_PUBLIC_DATA_FREE.CYBERSYN.SEC_METRICS_TIMESERIES
    primary_key: [company_id, metric, period_end_date]

relationships:
  - from: sec_report.company_id
    to: company.company_id
    type: many_to_one
  - from: sec_metric.company_id
    to: company.company_id
    type: many_to_one

dimensions:
  - name: filing_type
    entity: sec_report
    column: form_type
  - name: fiscal_period
    entity: sec_metric
    column: period_end_date
    type: date

metrics:
  - name: total_deposits
    entity: sec_metric
    expression: "VALUE WHERE metric = 'Deposits'"
  - name: total_loans
    entity: sec_metric
    expression: "VALUE WHERE metric = 'LoansAndLeasesReceivableNetReportedAmount'"

cross_domain_keys:
  - entity: company
    join_key: hq_geography_id
    referenced_by: [geography.geography.geography_id]
```

`config/domains.yaml` keeps the router's classification labels and the
semantic-model domain set in lockstep (single source of truth for domain
descriptions, used by both the semantic models and the router prompt).

---

## 5. Agent implementation design

**Model & config:** `claude-opus-5` for both the router and answering
agents (same model for routing and answering, so routing failures can't be
blamed on a deliberately weaker router model); adaptive thinking; `effort`
fixed at `high` for **all** conditions (never swept per-condition — that
would itself be a confound); ~8000 max tokens, streaming.

**Tool surface — identical definitions in both experiments:**

- `get_semantic_model` — no-arg fallback recall tool; the model is also
  injected directly into the system prompt. Kept identical across both
  experiments so tool-call counts aren't an artifact of context size
  differences.
- `run_sql` — executes a single read-only `SELECT` via `sql_executor.py`
  (regex pre-check rejecting non-SELECT statements, read-only role as
  defense in depth), returns rows + column types, capped at 500 rows.

**Shared loop (`agents/loop.py`):** build system prompt
(`shared_system_core.md` + injected model(s)) → send question → standard
tool-use loop, executing `run_sql`/`get_semantic_model` calls and returning
results, until `end_turn` or an 8-call iteration cap (hitting the cap is
logged as a failure-mode signal for H3). Final answer must include a small
structured JSON footer (`sql_used`, `domains_touched`, `confidence`) parsed
by the logger for failure-mode analysis.

**Router (Experiment B) — LLM classification, not keyword/embedding.**
Rationale: the research question is about architectural tradeoffs of
decomposition, not routing-infrastructure quality. An LLM router (same
model, low-effort classification call) is simplest, most auditable (its
reasoning is inspectable text), and keeps "routing failure" attributable to
genuine domain ambiguity rather than a second uncontrolled variable
(embedding/keyword routing quality). Router prompt lists domains from
`config/domains.yaml`, returns structured JSON: `{domains: [...], reasoning,
ambiguous}`. When 2+ domains are returned, the specialist loop runs with the
union of those domains' models injected.

Router failure modes to log explicitly (operationalizes H3): `wrong_domain`,
`incomplete_domain_set` (cross-domain question routed to only some required
domains), `over_routing` (single-domain question routed to multiple
domains), `no_domain_found`.

---

## 6. Logging design

One JSONL file per `run_id`, one line per question-attempt, capturing:
experiment condition, model/effort/thinking config, question metadata,
trial index, routing decision + latency (Exp. B), full ordered tool-call log,
generated SQL, execution errors, final answer (text + structured footer),
token counts (input/output/cache-read), wall-clock latency,
`hit_iteration_cap`, and Claude API request IDs for debugging. Written
immediately per question (not buffered) so partial runs are recoverable.
`analysis/aggregate_results.py` rolls this up into $/question and
latency/question comparisons between A and B, not just accuracy — cost and
latency are first-class metrics per the brief.

---

## 7. Evaluation framework

**Question authoring:** author and freeze (git-committed, tagged) all
question banks *before* the first real run, to prevent iteratively tuning
questions until one architecture looks better. Recommended floor: ≥15
single-domain, ≥15 cross-domain, ≥10 executive. Each question carries `id`,
`text`, `category`, `expected_domains` split into *minimum required* vs.
*optional-enrichment* (routing accuracy is scored against the minimum-required
set, since "the correct domain set" is itself debatable for open-ended
questions), `difficulty`, and for category 1, a `ground_truth_sql_path`.
Author from the business-question space, not from known system weak points
or known semantic-model joins (leakage guard).

**Category 1 (single-domain) ground truth:** hand-verified reference SQL per
question; correctness = execute both agent SQL and reference SQL, compare
result sets after normalizing sort order/float tolerance — not string
comparison. Report exact-match and row-count-only match separately.

**LLM-as-judge:** separate Claude call, same model as agents (per user's
choice), **blinded** to which experiment produced the answer (sees only
question + answer, not system identity) to reduce self-preference and
expectation bias. Rubric per category (correctness for cat. 1; domain
coverage/reasoning quality/genuine-vs-fabricated synthesis for cat. 2;
completeness/usefulness/synthesis/actionability for cat. 3), 1–5 per
dimension, structured JSON output with justification text. Judge runs 3x per
(system, question) pair, median score taken, to average out judge
non-determinism (separate from the 3 agent trials).

**Calibration (binding, per user's choice of judge tier):** since the judge
uses the same model tier as the agents (higher self-preference-bias risk
than a stronger-tier judge), human calibration is the primary bias
safeguard — not optional. Sample a stratified ~20% subset across categories
and both conditions, score independently and blind with a human, compute
Cohen's weighted kappa (+ Spearman). **Do not proceed to judge-only scoring
on the full run unless agreement clears a pre-registered threshold
(recommend κ ≥ 0.6)** — below that, revise the rubric and recalibrate first.

**Aggregation:** primary comparison is paired (same questions, both
architectures) — Wilcoxon signed-rank on judge scores, paired proportion
test on SQL correctness — controlling for question-level difficulty
variance. Secondary: routing accuracy, cross-domain completion rate, $/question,
latency/question, tokens/question, and a qualitative eval-maintenance-cost
count (number of eval cases / routing tests / domain-interaction tests each
architecture needs) — this last metric structurally favors the unified
architecture in a way accuracy scores won't capture and should be reported
explicitly as its own tradeoff axis. Report confidence intervals /
bootstrap resampling given modest sample sizes (n≈15–40/category) rather
than p-value-only claims.

---

## 8. Experiment workflow

1. Freeze `config/experiment.yaml`, freeze semantic models (schema-validated,
   unified regenerated from domains), freeze question bank (tagged, e.g.
   `eval-v1`).
2. Run Experiment A and B **interleaved by question** (Q1→A, Q1→B, Q2→A, ...)
   rather than blocked by experiment, so time-of-day API latency variance is
   averaged across conditions rather than concentrated in one — 3 trials
   each per question.
3. Run automated SQL correctness checks (category 1, both experiments).
4. Run judge (3x per pair, blinded) for categories 2 and 3 (optionally 1 as
   a secondary signal too).
5. Run calibration check against the human-labeled subset; gate before
   trusting judge-only results if agreement is below threshold.
6. Aggregate: comparison tables, significance tests, cost/latency tables,
   eval-maintenance-cost summary.
7. Reproducibility check: re-run a small subset (~10 questions × both
   conditions) unchanged and confirm run-to-run variance sits within the
   expected non-determinism band before trusting the main results.
8. Write up findings addressing H1/H2/H3 explicitly — for each hypothesis,
   state supported/contradicted/inconclusive, tied to specific failure-mode
   tags and example transcripts, not just aggregate scores.

---

## 9. Milestones

- **M0 — Dataset & infra setup.** Confirm Snowflake read access to
  `SNOWFLAKE_PUBLIC_DATA_FREE` schemas (geography, financial/economic
  indicators, demographics, company/SEC), freeze the target company/geography
  set (§3.3), stand up repo skeleton, `sql_executor.py` with read-only
  guardrails. *Exit: arbitrary read-only SELECT executes and returns typed
  results.*
- **M1 — Semantic models + unified agent (Exp. A).** Author 4 domain YAML
  files, generate unified model, build shared loop + tools, unified agent
  answering single-domain questions end-to-end with logging. *Exit: 5
  hand-picked single-domain questions answered correctly, fully logged.*
- **M2 — Router + routed agent (Exp. B).** Build LLM router, wire shared
  loop to accept domain-scoped model(s), handle multi-domain union routing.
  *Exit: same 5 questions answered via routed path with correct routing,
  plus 2–3 deliberately cross-domain questions exercising multi-domain
  routing.*
- **M3 — Eval harness.** Author full frozen question bank + ground-truth SQL
  (cat. 1), judge + rubric, calibration pipeline. *Exit: `run_eval.py` runs
  end-to-end on a 5-question pilot through both experiments, producing a
  comparison table with judge calibration measured on the pilot.*
- **M4 — Full experiment run.** Execute frozen question bank × 3 trials ×
  both experiments per §8, including reproducibility check. *Exit: all logs
  present, aggregation runs cleanly, judge calibration meets or is reported
  against the κ ≥ 0.6 threshold.*
- **M5 — Analysis & writeup.** Statistical comparison, failure-mode
  breakdown, cost/latency tables, H1/H2/H3 verdict, risks/limitations,
  recommendation on when decomposition helps vs. hurts.

M1/M2 overlap once the shared loop exists. M3 can start in parallel with M2
as long as question authors don't peek at agent transcripts.

---

## Phase 1: Cortex Analyst

Repeats the unified-vs-decomposed question on Snowflake's managed product.
Deliberately reuses as much of Phase 2's infrastructure as possible (SQL
execution, question bank, ground truth, judge) so the only genuinely new
work is the Cortex Analyst integration itself.

### P1.1 Repository additions

```
cortex_analyst/
├── semantic_views.py     # generates Cortex semantic view DDL from the SAME
│                          #   semantic_models/domains/*.yaml used by Phase 2
├── client.py              # queries Cortex Analyst (REST or SQL function),
│                          #   returns generated SQL + confidence/VQR match info
└── schema.py               # CortexAnalystRunLog — reduced-visibility log schema
scripts/
└── generate_cortex_semantic_views.py   # emits DDL for 4 per-domain views
                                          #   (decomposed) + 1 combined view
                                          #   (unified), analogous to
                                          #   scripts/generate_unified_model.py
```

`cortex_analyst/client.py` calls into the **same `agents/sql_executor.py`**
already built for Phase 2 to actually execute the SQL Cortex Analyst
generates, rather than trusting Cortex Analyst's own execution path. This
matters for two reasons: it guarantees both phases run SQL through an
identical code path against the identical warehouse/role, and it lets the
category-1 ground-truth diff (§7) work unmodified against Phase 1 results.

### P1.2 Semantic view translation (single source of truth)

Exactly like Phase 2's `generate_unified_model.py`, the Cortex semantic
views must be *generated*, not hand-authored, from
`semantic_models/domains/*.yaml` — otherwise "semantic model authoring
effort" becomes a hidden variable a second time, and worse, a variable that
could differ *between phases* in a way that makes cross-phase replication
meaningless. `scripts/generate_cortex_semantic_views.py` reads the same 4
domain YAML files Phase 2 uses and emits:
- 4 separate Cortex semantic view definitions (Phase 1 "decomposed")
- 1 combined semantic view spanning all entities (Phase 1 "unified"),
  built the same way Phase 2's unified model is — by promoting each
  `cross_domain_keys` entry into a native relationship

Exact DDL syntax (`CREATE SEMANTIC VIEW ...` vs. the YAML-based semantic
model spec Cortex Analyst also supports) needs to be verified against
current Snowflake docs during P1-M0 — do not assume the syntax sketched here
without checking, the same caveat that applies to table/column names in
Phase 2's domain YAMLs.

### P1.3 Querying Cortex Analyst

Two configurations, both driven by the same frozen question bank:
- **Unified**: single semantic view registered; every question sent
  against it.
- **Decomposed**: all 4 domain semantic views registered, Cortex Analyst's
  Routing Mode / runtime model selection enabled, questions sent without
  specifying which view to use (letting Cortex Analyst route).

For each question, `client.py` captures: which semantic view(s) Cortex
Analyst used (if exposed in the response), the generated SQL, the VQR
confidence score (if a verified-query match occurred), the execution result
(via our own `sql_executor.py`), and latency.

### P1.4 Logging — reduced visibility, by necessity

Cortex Analyst does not expose tool-call traces, iteration counts, or
router reasoning text the way the custom agent's `RunLog` does. A separate,
narrower `CortexAnalystRunLog` schema (in `cortex_analyst/schema.py`)
captures only what's actually available: question, semantic view(s) used,
generated SQL, VQR confidence, execution result/errors, latency, and — as a
proxy for the `hit_iteration_cap` / failure-mode signals Phase 2 tracks —
whether Cortex Analyst abstained and returned clarifying-question
suggestions instead of an answer (its own documented hallucination-
prevention behavior). This means H3's failure-mode taxonomy is necessarily
coarser for Phase 1: "routed to wrong view" is measurable (compare the
view(s) used against `expected_domains` in the question bank, same as
Phase 2's routing-accuracy check), but *why* is not directly inspectable.

### P1.5 Cost tracking

Cortex Analyst cost is Snowflake credits, not Anthropic tokens — pull
consumption from Snowflake's `ACCOUNT_USAGE` views (exact view name to
confirm during P1-M0) rather than from API response token counts. Report
Phase 1 cost/question and Phase 2 cost/question on separate axes in the
final writeup — they are not directly interchangeable units, and forcing
them into one number would hide more than it reveals.

### P1.6 Milestones

- **P1-M0 — Access & discovery.** Confirm Cortex Analyst is enabled on the
  account (may require a specific Snowflake edition/role grant), confirm
  permission to create Semantic Views, confirm `ACCOUNT_USAGE` visibility
  for credit tracking, confirm exact DDL syntax. *Blocked on the same
  FDIC/CFPB/HMDA schema verification Phase 2 needs — do this together with
  Phase 2's M0.*
- **P1-M1 — Semantic view generation.** Build and run
  `generate_cortex_semantic_views.py`, register both the decomposed (4-view)
  and unified (1-view) configurations in Snowflake. *Exit: both
  configurations queryable via Snowsight or the Cortex Analyst REST API.*
- **P1-M2 — Client + logging.** Build `cortex_analyst/client.py` and
  `schema.py`, run the same 5 pilot questions from Phase 2's M1/M2 through
  both configurations. *Exit: pilot questions logged with generated SQL,
  confidence scores, and execution results.*
- **P1-M3 — Full run.** Run the full frozen question bank (same
  `eval/questions/*.yaml` as Phase 2) through both configurations; reuse
  `eval/run_eval.py`'s ground-truth diff and LLM-judge logic unchanged
  against Phase 1's outputs. *Exit: Phase 1 comparison table, same shape as
  Phase 2's.*

P1-M1 can start as soon as Phase 2's domain YAMLs are corrected against the
real FDIC/CFPB/HMDA schema (Phase 2 M0) — no need to wait for Phase 2's
agent loop (M1/M2) to be finished first, since Phase 1 doesn't depend on it.

---

## Cross-phase synthesis (M6)

After both Phase 1 (P1-M3) and Phase 2 (M5) are complete:
- Report each phase's within-phase unified-vs-decomposed comparison
  independently, in the same format (accuracy by category, routing
  accuracy, cost/question, latency/question).
- Report whether the *direction* of each finding (e.g. "decomposition wins
  on single-domain, unified wins on cross-domain") replicates across both
  phases — a simple agree/disagree/inconclusive call per hypothesis
  (H1/H2/H3), not a merged statistical test across phases.
- Report platform-level differences explicitly as their own finding, not
  folded into the architecture comparison: implementation effort (Cortex
  Analyst decomposition is ~config-only; custom-agent decomposition required
  building a router), cost model (credits vs. tokens), and observability
  (full traces vs. coarse routing outcome only).

---

## 10. Risks and open questions

- **No customer/account-level banking data exists in this dataset.** The
  study is necessarily reframed around company-level (public bank holding
  company) competitive intelligence, not customer segmentation/transaction
  analysis. This should be stated up front in the writeup so results aren't
  mistaken for a customer-behavior study.
- **LLM non-determinism** — addressed via 3 agent trials + 3x judge scoring
  with median aggregation; this multiplies API cost roughly 6–9x over a
  naive single-shot design.
- **Prompt engineering effort asymmetry** — easy to over-tune one condition.
  Mitigated by shared boilerplate (`shared_system_core.md`) and resisting
  per-domain hand-tuning once frozen.
- **Semantic model authoring effort as a hidden variable** — mitigated by
  generating the unified model from the domain models (§4), not hand-authoring
  it separately.
- **Judge bias** — same-model-family judge (per user's choice) has more
  self-preference risk than a stronger-tier judge; mitigated by blinding and
  the mandatory human-calibration gate (§7). Verbosity bias mitigated with
  explicit rubric instruction to not reward length/hedging.
- **Eval-question / dataset-structure leakage** — mitigated by authoring
  questions from business-question space, not from known model joins.
- **SEC XBRL data quality/coverage gaps** — not every bank holding company
  reports every metric in a perfectly standardized XBRL tag every period;
  ground-truth SQL for category 1 must be verified against actual returned
  data, not assumed schema completeness, during M1.
- **Cost** — roughly 40 questions × 2 experiments × 3 trials = 240 agent
  runs, plus ~30 judged questions × 2 experiments × 3 judge calls = 180 judge
  calls. Estimate concretely with a token-counted pilot batch before the
  full M4 run; agree a budget ceiling with the user beforehand.
- **SQL execution parity** — both experiments must run against the identical
  warehouse/database/role; no scoped-down grants for one condition.
- **Small sample sizes** — ~15–20 questions/category limits statistical
  power; report confidence intervals/bootstrap resampling and frame this as
  a directional pilot, not a high-power confirmatory trial.
- **Multi-domain routing ground truth ambiguity** — mitigated by the
  minimum-required vs. optional-enrichment split in `expected_domains` (§7).
- **Cross-phase over-claiming** — the biggest new risk from the two-phase
  design: it is tempting to report "Cortex Analyst beat the custom agent" or
  vice versa as if it were a controlled result. It is not — model, routing,
  and retrieval all differ simultaneously between phases. The writeup must
  restrict cross-phase claims to directional replication of the
  within-phase findings (see "Cross-phase synthesis"), and say so explicitly
  rather than letting the reader infer a causal platform comparison.
- **Cortex Analyst access/availability** — Cortex Analyst and Semantic Views
  may require a specific Snowflake edition, role grants, or region
  availability not yet confirmed for this account. P1-M0 must resolve this
  before any other Phase 1 work; if unavailable, Phase 1 either waits on an
  edition/role change or is dropped without blocking Phase 2.
- **Coarser Phase 1 observability limits H3 analysis for that phase** — see
  §P1.4. Framed as a known limitation in the writeup, not worked around by
  inventing signals Cortex Analyst doesn't actually expose.

---

## Verification

- **M0:** run `scripts/setup_snowflake.py`; confirm it prints non-zero row
  counts for each target schema (geography, economic indicators,
  demographics, company/SEC) without error.
- **M1/M2:** run the unified and routed agents against the 5 pilot questions
  via a small CLI/script invocation; inspect the JSONL logs in `runs/` to
  confirm routing decisions, SQL, and answers are captured correctly; spot
  check 2–3 generated SQL queries by hand for correctness.
- **M3:** run `eval/run_eval.py` on the 5-question pilot; confirm it produces
  a comparison table and that `eval/calibration.py` computes a kappa value
  against a small manually-labeled sample.
- **M4:** run `pytest tests/` (schema validation, router unit tests, SQL
  executor guardrail tests, judge calibration test) and confirm all pass;
  run the full eval and confirm `analysis/aggregate_results.py` produces
  complete comparison/cost/latency tables with no missing runs.
- **M5:** manually review a sample of full transcripts per hypothesis
  (H1/H2/H3) to confirm the quantitative verdict matches what's visible in
  the actual agent behavior, not just the aggregate number.
- **P1-M0:** confirm Cortex Analyst / Semantic View creation succeeds under
  the account's current edition and role; confirm an `ACCOUNT_USAGE` query
  returns Cortex credit consumption rows.
- **P1-M1:** run `generate_cortex_semantic_views.py --check` (mirroring
  Phase 2's `generate_unified_model.py --check`) to confirm the registered
  DDL matches a fresh regeneration from the domain YAMLs.
- **P1-M3:** confirm `eval/run_eval.py` produces a Phase 1 comparison table
  in the same shape as Phase 2's, and that the cross-phase synthesis (M6)
  correctly labels each claim as within-phase (causal) or cross-phase
  (directional replication only).

---

## Implementation status

Tracking progress against this plan (updated as work proceeds):

- [x] M0 (partial) — repo skeleton, config files, `sql_executor.py` with
      read-only guardrails, `setup_snowflake.py` discovery script written.
      **Not yet run against a live account** — no Snowflake credentials
      available in this environment; table/column names in
      `semantic_models/domains/*.yaml` are best-effort from public docs and
      need verification (`scripts/setup_snowflake.py` prints a diff against
      what's assumed once run).
- [x] Semantic models — 4 domain YAMLs + generated `unified_model.yaml`
      (`scripts/generate_unified_model.py`), schema-validated
      (`scripts/validate_semantic_models.py`).
- [x] Logging — `logging_/schema.py` (RunLog/ToolCallLog/RoutingDecision),
      `logging_/sink.py` (JSONL, round-trip tested).
- [x] M1 — shared agent loop (`agents/loop.py`), tools (`agents/tools.py`),
      prompts, `agents/unified_agent.py`. Manual Claude tool-use loop (not
      the beta Tool Runner) for full per-tool-call instrumentation; adaptive
      thinking + `effort` per `config/experiment.yaml`; system-prompt
      prompt-caching on the semantic-model block. Verified via unit tests
      and offline pure-function checks — **not yet run against live
      Anthropic/Snowflake credentials.**
- [x] M2 — `agents/router.py` (LLM classifier, structured JSON output,
      domain names constrained via schema `enum`), `agents/routed_agent.py`.
      `semantic_models/schema.py::merge_domain_models` promotes a
      cross-domain relationship only when *both* routed domains are
      present, and otherwise surfaces the dangling reference as a comment
      in the rendered model — directly operationalizes H3 (routing that
      omits a required domain should manifest as an agent that can't join
      to it, not a hidden capability the agent has anyway).
- [x] M3 — eval harness: `eval/judge.py` (blinded, structured per-category
      rubric scoring), `eval/judge_rubric.md`, `eval/calibration.py`
      (weighted Cohen's kappa + Spearman vs. the κ ≥ 0.6 gate),
      `eval/run_eval.py` (interleaved A/B execution, ground-truth SQL
      diffing, judge scoring, aggregation, CSV output). **Question banks in
      `eval/questions/*.yaml` are starter placeholders (3 per category)**,
      explicitly marked as such — not the frozen ≥15/≥15/≥10 `eval-v1` bank,
      which needs authoring against verified real data.
- [x] `analysis/aggregate_results.py` — cost/latency/routing-accuracy
      rollup from persisted JSONL logs, independent of a live eval run.
- [x] Tests — 38 passing (`pytest`): semantic model schema/merge logic, SQL
      guardrails, router (mocked client, no live calls), judge/calibration
      math, eval aggregation. Everything that doesn't require a live
      Anthropic or Snowflake connection is exercised.
- [ ] M4 — full experiment run (requires live Snowflake + Anthropic API
      credentials, the real question bank, and a budget decision — not run
      in this session).
- [ ] M5 — analysis and writeup (depends on M4).

**Phase 1 (Cortex Analyst) — added after the two-phase decision:**
- [ ] P1-M0 — confirm Cortex Analyst / Semantic View access on the account.
- [ ] P1-M1 — `generate_cortex_semantic_views.py`, register decomposed +
      unified configurations.
- [ ] P1-M2 — `cortex_analyst/client.py` + `schema.py`, pilot run.
- [ ] P1-M3 — full frozen-question-bank run through Cortex Analyst.
- [ ] M6 — cross-phase synthesis (after both M5 and P1-M3).

**Still open, blocks both phases' domain-model accuracy:** the FDIC/CFPB/
HMDA dataset specifics (real institution-level deposits/loans/mortgage-
origination data) have not yet been provided — `semantic_models/domains/*.yaml`
currently reflects an earlier, likely-wrong guess (Cybersyn/SEC-EDGAR
shape) and needs correction once the user shares the actual tables/schemas
in use. Both phases inherit this fix automatically once applied, since
Phase 1's semantic views are generated from the same YAML files.
