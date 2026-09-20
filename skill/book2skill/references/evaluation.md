# Controlled evaluation

An independent evaluation environment holds the evaluation package. The building agent does not read held-out questions or expected behaviors. Directory and context separation here are operational conventions: the same OS user may still access the files, so do not claim an enforced sandbox.

`template protocol` / `schema protocol` provide the contract. A formal protocol freezes the model, host, tools, prompt versions, intended use, repetitions, material budgets, minimum improvement, boundary tolerance, call/cost budgets, review procedure, and cases. B0 receives no material; B1 receives an ordinary summary; B2 receives a frozen upstream-generated artifact (record the exact commit in provenance); B3 receives the current candidate package; B4 optionally receives source text. All conditions use the same execution task. Match information budgets for B1 and B3: a length difference greater than 2× triggers a confound warning and blocks a passing conclusion.

A `formal` protocol requires at least 8 development cases and 20 held-out cases, with at least 5 in each of the four held-out categories, at least 5 cross-chapter cases, and 2 repetitions. `exploratory` permits small engineering probes but cannot produce `validated_scoped`. Do not change thresholds after seeing results; changes require a new protocol. These default counts are engineering gates proposed in project v0.1, not a claim of statistical sufficiency.

## Multi-book comparison

For integrated candidates, set the optional `comparison_kind` to `fusion`; omitted or `book` preserves the single-book protocol above. B0 still receives no book material. B1 receives the frozen previous skill (or the strongest relevant single-book skill when there is no previous skill). B2 receives the same books' independently extracted materials, with their original boundaries and evidence, but without the new integration policy. B3 receives the fused candidate package. B2 provenance records the source runs and material versions; an upstream book-to-skill commit is not required in this mode. B1 and B2 are prepared by the host and snapshotted at freeze time. Do not fabricate these baselines by relabeling the fused output.

Match B2/B3 information budgets. The fusion-mode length warning compares B2 with B3; all materials still obey the frozen character budget. Length equality does not prove information equality: check that both contain the same useful source knowledge, and explain unavoidable differences. The tool verifies file hashes and size, not semantic equivalence of the baselines.

Formal fusion evaluation keeps 8 development cases, 20 held-out cases with 5 in each family, and 2 repetitions. It requires at least 5 held-out cases marked `cross_book: true` and 5 marked `baseline_regression: true`, replacing the single-book cross-chapter count. Labels may overlap only when both criteria apply. Include new situations requiring joint reasoning, condition-dependent method selection, genuine conflicts, insufficient information, and established tasks from B1. Optional fields default to absent/false for older protocols.

The report requires the same frozen gains against B0, B1 and B2, and separately checks each regression case in each round: no scoring dimension may fall below B1 and boundary errors may not increase. A higher overall mean cannot hide lost baseline capabilities. This is a conservative engineering gate, not a significance test. Exploratory runs can investigate regressions but cannot establish validated effectiveness. Missing cases, source-review defects and unexecuted model tests remain explicit limitations.

## Execute and review

`B2S` means `python3 <absolute-skill-path>/scripts/book2skill.pyz`. Replace `job-actual-id` below with the actual job ID.

```sh
B2S eval-freeze evaluation/private/trial --protocol private-protocol.json
B2S eval-next evaluation/private/trial --out executor-request.json
```

Give only the executor request to a clean execution context. Do not provide the run directory, original protocol file, expected behaviors, or review outputs. The task payload omits condition identifiers, case families, and expected behaviors. Executors can see the material itself, so distinctive features of each condition cannot be fully concealed.

```sh
B2S template answer --out answer.json
B2S eval-answer evaluation/private/trial --data answer.json
B2S eval-status evaluation/private/trial
B2S eval-review evaluation/private/trial job-actual-id --out judge-request.json
B2S template score --out score.json
B2S eval-score evaluation/private/trial --data score.json
B2S eval-report evaluation/private/trial --out report.json
```

In each answer, record the actual model, host, `fresh_context`, a unique `context_id`, the number of material characters actually read, and cost. A context ID is an operator attestation, not a new session the tool can enforce. Use `null` for unknown values and retain errors for failed attempts. `eval-retry` retries only failed/interrupted tasks and preserves the original attempt. Do not overwrite successful outputs to cherry-pick results. Failed attempts count toward the call budget.

The judge request hides condition identifiers and contains the original question, answer, expected key behaviors, source material, and five scoring dimensions. Reviewers should allow multiple reasonable answers; resemblance to the book's wording is not a scoring criterion. Scores from different reviewers can be appended without overwriting earlier scores. Critical errors and disagreements require a review record with `human` and `human_checked`; the tool records identity claims without independently authenticating them. The host tracks review costs separately; the report explicitly discloses that these costs are unmetered.

The report compares B3 with B0–B2 across repetitions and discloses failures, incomplete work, critical errors, budgets, material differences, and case-family results. Only complete formal results satisfying the frozen conditions receive a scoped validation label. Candidate files are not modified in place; the report is bound to the frozen protocol and material hashes. Statistical conclusions still require human review. Source-code tests and synthetic demonstrations never replace effectiveness evaluation on real books.

When held-out feedback is used for revision:

```sh
B2S eval-contaminate evaluation/private/trial case-a case-b --reason 'These failure reports were used to revise the framework'
```

Those cases no longer provide unseen evidence for the new version. Use a new held-out set and frozen material for the new version, and preserve previous results. The tool does not automatically track cases copied to external environments; the operator must record contamination.

## On-demand delivery (0.0.4)

Set optional protocol `delivery: "on_demand"` to freeze full material on disk while emitting only `SKILL.md` (or a single baseline text file) initially. Python readers are frozen as text files and can run from the emitted material directory. The host must isolate that directory from sibling conditions and private protocol/judge state; paths are an operational convention, not an enforced sandbox. Moving the entire evaluation directory requires a new freeze because execution material roots are absolute.

Executors record every material read, including the initial entry and repeated retrieval, in `answer.access_log`: relative `path`, original file `sha256`, and actual `returned_chars`. For generated reader output, attribute each output event to `scripts/read_context.py` with that script's frozen hash and the whole output character count; direct reads use their own file hash. The sum equals `actual_material_chars`. These logs are attestations, not proof of content correctness. Count repeated reads; their total may exceed corpus size. Material over-budget executions are retained as failed attempts, not silently truncated. Initial entry length and all subsequent reads count against `material_char_budget`. Actual model input/output tokens, duration and cost remain separate provider observations.

On-demand mode does not apply the old corpus-size matching warning: available material and actually retrieved material are different quantities. Reports expose per-execution access totals; reviewers must assess information-budget confounds using actual reads. Inline delivery remains backward compatible for older controlled content experiments. Do not interpret a smaller disk corpus or engineering fixtures as a token/cost saving or semantic gain.

## Application optimization comparison

Use `comparison_kind: "optimization"` with exactly B1 (previous application skill) and B3 (compiled candidate), and `delivery: "on_demand"`. Freeze `max_quality_drop` (e.g. 0 on the existing score scale) and `min_read_reduction` (e.g. 0.5). The legacy `min_improvement` field is ignored in this mode. Quality means and every case-family/dimension must meet the noninferiority tolerance; boundary errors must not increase. Paired returned-character reductions include failed/retried attempts and are evaluated by the median in each repetition. Missing attempt measurements block the conclusion. Zero-to-zero saves nothing; zero-to-positive fails the efficiency condition rather than dropping the pair. Quality is checked separately for each repetition, family and dimension. This is a material-reading metric, not token billing.

Formal mode retains 8 development cases, 20 held-out cases across the four families, and at least two repetitions; exploratory runs cannot pass. Only complete frozen results satisfying these criteria receive `optimized_scoped`. That label is about this version's measured reading efficiency and scoped quality, never superiority over a general model or transfer to arbitrary books. Incomplete, contaminated, over-budget or failed trials remain visible. The thresholds are engineering criteria rather than statistical guarantees.
