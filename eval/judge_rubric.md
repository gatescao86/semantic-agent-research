# Judge Rubric (v1)

Frozen scoring rubric for the LLM-as-judge (`eval/judge.py`). Do not edit
mid-experiment-run — a rubric change invalidates any judge calibration done
against the old version. Bump the version number and recalibrate if you do
change it.

The judge is **blinded**: it sees only the question and the answer text (not
which experiment/system produced it), to reduce self-preference and
expectation bias. It scores per-dimension on a 1–5 scale with a short
justification per dimension, so results are auditable rather than a single
opaque number.

## Category 1 — single_domain

- **correctness** (1–5): does the answer's stated result match what the data
  actually shows? 5 = fully correct; 3 = directionally right but off on a
  detail (wrong period, wrong units); 1 = wrong or fabricated.

(Category 1 is primarily scored by exact ground-truth SQL diffing —
`eval/run_eval.py` — this judge score is a secondary signal, not the primary
metric, per plan §7.)

## Category 2 — cross_domain

- **domain_coverage** (1–5): did the answer draw on every domain the
  question actually required? 5 = all required domains reflected in the
  answer; 1 = answered from a single domain when multiple were needed.
- **reasoning_quality** (1–5): is the cross-domain reasoning sound — does it
  correctly relate data from different domains rather than just listing
  facts side by side?
- **synthesis_genuineness** (1–5): is the synthesis actually grounded in
  queried data, or does it read as plausible-sounding text not backed by
  what was retrieved? 5 = every claim traces to a queried result; 1 =
  fabricated or unsupported connections between domains.

## Category 3 — executive

- **completeness** (1–5): does the answer address every part of the
  (typically multi-part) executive question?
- **usefulness** (1–5): would this genuinely help a business decision-maker,
  or is it generic/hedge-y filler?
- **synthesis** (1–5): does it integrate data across domains into a coherent
  narrative, or just enumerate disconnected facts?
- **actionability** (1–5): does it point toward a concrete conclusion or
  next step, or stop at description?

## Scoring instructions given to the judge model

- Score strictly against the dimensions above — do not reward length,
  confidence, or hedging language on its own.
- An answer that correctly and concisely says "I don't have enough data to
  answer this" should score reasonably on the dimensions it can be judged
  on (e.g. it can still be "genuine" and non-fabricated) rather than being
  penalized as if it were simply wrong.
- Do not infer or guess which system produced the answer — you are not told,
  and should not try to determine it from writing style.
