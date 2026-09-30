# Evaluation Methodology

This is an intentionally opinionated evaluation strategy. It prioritizes explicit, task-specific PASS/FAIL criteria over general-purpose quality scores. The benefit is interpretability and tighter control over what is being measured; the cost is manual rubric construction, limited scalability, and dependence on domain expertise.

## Criteria

Each question has a manually curated list of **atomic PASS/FAIL criteria**. The agent's response is evaluated against each criterion independently.

This approximates how enterprise users evaluate real work, i.e., whether the answer contains the required facts, scope, numbers, and conclusions.

## Scoring

The study avoids asking an LLM judge to assign numerical scores such as 0-1 or 1-5 because:

- **Numerical scores are hard to intepret**. The practical difference between a score of 0.7 and 0.8 is unclear.
- **Broad metrics are ambiguous.** Terms such as comprehensiveness, groundedness, or consistency depends heavily on rubric wording and judge prompts.
- **LLM judges are probabilisitc**. Repeated evaluations may produce different scores.

Instead, the judge is asked to evaluate whether each specific criterion is satisfied.

The tradeoff is scalability: criteria must be manually curated for each question, which is time-consuming and often requires domain expertise.

## Question Types

The benchmark includes:

- **Factual / numeric**: narrow questions with objectively verifiable answers.
- **Executive / open-ended**: broader tasks requiring retrieval, analysis, and synthesis across multiple facts.

This tests both factual accuracy and performance on more complex enterprise tasks.

---



## Criterion Schema


| Field              | Type   | Description                                                                       |
| ------------------ | ------ | --------------------------------------------------------------------------------- |
| `id`               | string | Unique within the question (e.g. `"001"`). YAML: quote it (`"001"`).              |
| `match_criteria`   | string | `PASS if … FAIL if …`. One assertion.                                             |
| `value`            | number | Gold number. Requires `unit`.                                                     |
| `unit`             | string | `USD`, `USD_thousands`, `percent`, `percentage_points`, `count`, `ratio`, `year`. |
| `tolerance`        | number | Relative. Mutually exclusive with `tolerance_abs`.                                |
| `tolerance_abs`    | number | Absolute, in `unit`. Prefer for percents and counts.                              |
| `ground_truth_sql` | string | Query that produces `value` (authoring, not re-run at score time).                |


From `ex-001`:

```yaml
- id: "003"
  match_criteria: >
    PASS if the answer names Old National Bank, United Fidelity Bank,
    Fifth Third Bank, German American Bank, and Stock Yards Bank among
    the largest deposit holders in the Evansville market. FAIL if any
    of the five is missing.
```

---

### Judge Instructions

- Match on substance, not wording. An answer stating the required content in
different language still PASSes.
- Do not reward length, confidence, or hedging language.
- Judge only the criterion in front of you. Do not penalize the answer for
anything outside it.
- Return `verdict` `PASS` or `FAIL` according to the criterion's
`match_criteria`.
- Report the number the answer actually states, converted to the criterion's
unit. Do not judge whether it is close enough to any expected value.
- An answer that explicitly says the data does not support a conclusion is
`FAIL` for the criteria it did not address, but is not itself a fabrication.
- Do not infer or guess which system produced the answer.

