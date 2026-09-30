# Question bank

One directory per question, named for the question's `id`:

```
eval/questions/<question-id>/
    question.yaml           # the question, its expected domains, its criteria
    ground_truth/*.sql      # reference queries this question's criteria depend on
```

`ground_truth_sql` paths inside `question.yaml` are relative to the question's
own directory and are resolved (and existence-checked) by
`eval/question_bank.py` at load time. Load through that module — never glob
these files directly — so `run_eval.py` and `scripts/score_runs.py` cannot
drift apart.

Criterion schema is specified in [`../eval_strategies.md`](../eval_strategies.md)
and enforced by `eval/criteria.py`.

## Status

Two tracks (see [`../eval_strategies.md`](../eval_strategies.md)):

- **Executive** — retrieval and synthesis. Current bank: `ex-001`
  (Evansville competitive landscape), `ex-002` (Renasant footprint /
  expansion / risks), `ex-003` (United Community Bank vs weekly H.8),
  `ex-004` (Forward Bank WI footprint screen: thin deposit share × ACS
  growth).
- **Factual** — numerical accuracy on short questions with gold SQL.
  Current bank: `fa-001`–`fa-012`, drawn from the three executive questions
  (Evansville deposits, Renasant shares, H.8 / United Community Bank
  call-report).

This is not the frozen eval-v1 bank.
