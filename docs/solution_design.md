# Solution Design

This file is the checked-in home for the Solution Design referenced by `improvement_phase.md`. It currently holds the handoff-check topography (DEC-016). Other sections are added as slices land.

## Handoff checks

The pipeline has eight stages. Four checks sit at the handoffs between them. Every check writes its verdict to the `check_verdicts` ledger table. The two human decisions sit at either end of the pipeline.

```
You approve the question (Gate 1, S2)
  -> 1-2 Register, harvest 3 lanes
  -> Check A: on-topic evidence?       model judges, rules decide   -> retry harvest once -> NOT_PUBLISHABLE (zero findings)
  -> 3-4 Extract and grade claims
  -> Check B: claims well formed?      rules only, no model         -> BLOCKED (reason in plain words)
  -> 5 Gap matrix
  -> 6 Draft from ledger only
  -> Check C: hedges kept?             model judges, rules decide   -> rewrite sentence once
  -> 7 Compute gates G1-G6             a gate with no data counts as FAIL
  -> Check D: claim backs sentence?    entailment model, warns only -> flag sentence for review
  -> 8 Publish gate and export
You review and publish
```

| Check | Where | Judge | On failure | Slice |
|---|---|---|---|---|
| A | after harvest (Stage 2) | model per source, rule floor and count rule decide | retry harvest once with wider queries; still thin → `NOT_PUBLISHABLE`, zero findings, no draft | S3 |
| B | after grading (Stage 4) | rules only | `BLOCKED` with a plain-words reason | S4 |
| C | after draft (Stage 6) | model per sentence vs its claim, hedge-term rule overrides | one rewrite, then flag; hold vs warn-only decided by bake-off | S5 |
| G1–G6 | Stage 7 | rules | a gate with no data is FAIL, never PASS | S6 |
| D | before publish (Stage 8) | local NLI / entailment | warn only: badge on sentence, human decides | S8 |

### Invariants
1. **Rules override models, never the reverse.** Each verdict records `model_verdict`, `rule_verdict`, `rule_decisive` and `final`. When `rule_decisive` is true, `final` equals `rule_verdict`. Otherwise `final` comes from the model; if the model abstains, it comes from the rule. The precedence is implemented once, in `src/engine/checks.py::resolve_final`.
2. **Nothing loops more than once.** Check attempts are numbered 0 and 1, and `record_verdict` refuses attempt 2.
3. **Every verdict is written to the ledger**, including passes and abstentions. A verdict row stores the model id and prompt hash, so a decision can be traced back to the exact prompt that produced it.
4. **Run status lives on the run.** `runs.status` and `runs.status_reason` record `RUNNING`, `NOT_PUBLISHABLE`, `BLOCKED`, `REVISE`, `PUBLISH_READY` or `PUBLISHED`. They are no longer only in the returned dict.
5. **A model that is unavailable or returns unparseable output abstains.** It never counts as a pass. The rule then decides.

### Check A details (S3)
- **Input:** the approved question (`refined_question` from the approved S2 package, with `question_sha256` and `package_sha256`), plus every harvested source across the three lanes. An enterprise or practitioner source is its claims grouped by `source_id`.
- **Rule floor (decisive):** a source that shares no salient term with the question is `off_topic`, whatever the model says. Configured synonyms (`research.head_term_synonyms`) count as matches. Above the floor, the model decides.
- **Practitioner notes** get a verdict but are never removed. You attached them to the question yourself.
- **Model:** one batched prompt (`prompts/check_a_on_topic_v1.md`) returns `on_topic` / `off_topic` and a one-line reason per source.
- **Count rule (decisive, run level):** the run proceeds only if at least `checks.check_a.min_on_topic_sources` sources (from `config.yaml`, default 1) are on topic. Volume ("enough claims from enough sources") is Check B's job.
- **Retry:** the academic and enterprise lanes are re-harvested once with doubled query width. If the run is still thin, it stops as `NOT_PUBLISHABLE`. Nothing is drafted and the payload carries zero findings.

### Open risk
Check C is the least certain. A hedge check on a small local model may be unreliable, so the bake-off (`evals/bakeoff_check_c.py`, S5) runs before C is allowed to hold sentences. If it falls short, C ships warn-only, like D.
