# Native multi-book integration

The unit of extraction is one book; the unit of integration is a target task. This workflow supports two or more books without assuming that all of them should contribute. The host performs semantic work; the CLI stores, checks and packages the results. It does not execute models or create fresh contexts.

## 1. Preserve independent interpretations

Clarify the target capability and what the existing skill cannot yet do. Keep the current candidate as a frozen baseline. Run the [single-book workflow](workflow.md) separately for each new book, including suitability, complete reading coverage, model reconstruction, source review and final scope review. Reuse an existing run when its source, purpose and interpretation are still appropriate; do not reread an unchanged book solely to add another one.

Inputs must have completed source reviews for every claim and relationship, valid evidence, no pending task, and a final `whole` or `partial` scope. A text file containing `SKILL.md` is insufficient. If only a draft or installed skill is available, locate its extraction run and complete the missing review. If evidence cannot be recovered, report the gap rather than manufacturing a review. A book judged reference-only can remain outside the fusion run, with the exclusion documented; included eligible books may still contribute nothing to the final model.

`B2S` below means `python3 <absolute-skill-path>/scripts/book2skill.pyz`. Create a `books.json` manifest; paths are relative to that manifest, or absolute:

```json
{
  "schema_version": "0.0.1",
  "books": [
    {"id": "book-a", "run_path": "runs/book-a"},
    {"id": "book-b", "run_path": "runs/book-b"}
  ]
}
```

Use short unique book IDs. Duplicate source books cannot count as distinct inputs. Fill `fusion-config` with the target purpose, language, model/host identity, prompt version and budgets. Book versions come from the parent runs; the new configuration has no manual `book_version` field.

```sh
B2S template fusion-config --out fusion-config.json
B2S fusion-init runs/integration-v1 --books books.json --config fusion-config.json
B2S status runs/integration-v1
B2S fusion-catalog runs/integration-v1 --offset 0 --limit 20
```

Initialization freezes book text, models, source reviews, suitability decisions and version hashes. IDs are namespaced by book, including evidence IDs. Parent paths are used only for later change detection, not as a live dependency when reading the frozen snapshot.

## 2. Build an explicit integration plan

```sh
B2S task runs/integration-v1 fusion-plan --out plan-request.json
B2S fusion-context runs/integration-v1 --ids book-a--framework-actual-id
B2S fusion-context runs/integration-v1 --ids book-b--framework-actual-id
B2S template fusion-plan --out plan.json
B2S template usage --out usage.json
B2S submit runs/integration-v1 task-actual-id --data plan.json --usage usage.json
```

Use actual qualified IDs from the catalog. During this task, load every input framework with `fusion-context`. It returns dependency closure, related constraints and cited passages, not an isolated summary. Paginate the catalog; do not assume the first page contains everything. Prior access in another task does not replace a current reread.

For each framework, record `use`, `reference_only` or `exclude`, with a task-specific reason. A used framework cannot silently discard dependencies. Compare each pair of contributing books explicitly. A bridge compares concrete input objects from two books and cites both books' passages. Multiple bridges may be needed when a pair agrees about one premise but conflicts about another.

Use these questions to construct bridges:

1. **Problem and unit:** Do the frameworks address the same decision, actor, time scale and outcome? Similar terminology alone is not alignment.
2. **Mechanism and premises:** What explains the proposed effect? What must already hold? Map concepts by their role in the mechanism, preserving meaningful differences.
3. **Relationship:** Classify equivalence, refinement, complementarity, conditional alternatives, contradiction or unrelatedness. Explain the relationship using evidence, not just labels.
4. **Resolution:** Combine genuinely compatible elements, select by explicit conditions, retain separate alternatives, exclude an irrelevant comparison, or leave it unresolved. Contradictory and unrelated frameworks cannot be marked `combine`. Conditional routing needs both conditions and differences.
5. **Selection:** State what observable facts choose a method and what missing information prevents the choice. Do not resolve conflict by popularity, author prestige, or averaging incompatible advice. If the sources do not establish a priority rule, label a proposed rule as a hypothesis.

The plan outcome is `integrate`, `keep_separate`, or `insufficient_evidence`. Integration requires useful contributions from at least two books. Otherwise keep the existing capability and retain a reviewed non-integration decision. Non-integration dispositions are reference-only or excluded. Do not force an empty or cosmetic second contribution to make the validator pass.

## 3. Reconstruct a task-oriented model

```sh
B2S task runs/integration-v1 fusion-model --out model-request.json
B2S fusion-context runs/integration-v1 --ids book-a--framework-actual-id
B2S fusion-context runs/integration-v1 --ids book-b--framework-actual-id
B2S template fusion-model --out model.json
B2S submit runs/integration-v1 task-actual-id --data model.json --usage usage.json
```

Skip this step for non-integration outcomes. Unresolved bridges block synthesis until the plan is revised. Reconstruct 1–3 output frameworks organized around the target decisions, not one chapter list per book. Keep input acquisition, situation mapping, method selection, action, feedback and revision connected. Different methods can remain separate output frameworks with explicit routing; fusion does not require one universal formula.

Every output claim, relationship and framework needs exactly one lineage record listing its input objects and applicable bridges. Output IDs must differ from input and plan IDs. Only used frameworks supply output lineage. All output claims and relationships must participate in an output framework; unused objects cannot inflate the book count.

- Preserve unchanged `author_explicit` / `author_reconstructed` records verbatim apart from object IDs and correctly remapped relation endpoints. Their lineage has one input and no integration bridge.
- Mark a justified multi-book derivation `cross_book_synthesis`, with supporting bridges and source evidence from every contributing book. This means an integration judgment, not a joint statement by the authors.
- Mark new proposals beyond source support `model_extension`; they remain hypotheses after review. Revising one book's claim without multi-book support is an extension, not cross-book synthesis.
- A `keep_separate`, `exclude` or `unresolved` bridge cannot justify a combined output. Preserve separate alternatives instead. A semantic reviewer must still check that conditions, counterexamples, concept mappings and relative evidential strength survived reconstruction.

Reread lineage inputs and cited passages during this task. The CLI checks references and access records, not whether the host understood them.

## 4. Independently review the integration

```sh
B2S task runs/integration-v1 fusion-review --out review-request.json
B2S template fusion-review --out review.json
B2S submit runs/integration-v1 task-actual-id --data review.json --usage usage.json
```

Review every disposition, bridge, output claim, relationship and framework. For long reviews, use `--targets` with actual object IDs to prepare batches. Requests contain source inputs with dependency closure, passages, the plan and the complete output model. Non-integration outcomes also need review of their dispositions and bridges.

The reviewer declares `fresh_context: true` and a context ID different from all builder contexts. This is a recorded assertion, not enforced context isolation or identity authentication; use an authorized clean execution environment. Source-review declarations from input books are likewise preserved rather than independently authenticated. A builder must never invent an independent review to finish packaging.

Review must match the current integration hash and account for each target's evidence. `supported` for a synthesis means justified derivation, not tested real-world effectiveness. Extensions remain `hypothesis`. Unsupported or uncertain targets, or unresolved review issues, block packaging and require revision. Check especially whether a seemingly reasonable selection rule is actually established, whether incompatible meanings were collapsed, and whether original tasks still work.

## 5. Package, evaluate and evolve

```sh
B2S package runs/integration-v1 dist/my-integrated-skill/0.0.1 --name my-integrated-skill --version 0.0.1
B2S validate-package dist/my-integrated-skill/0.0.1
B2S fusion-source-check runs/integration-v1
```

A fused candidate contains its output frameworks, `routing.md`, selected evidence and `references/integration.json` with original perspectives, exclusions, bridges, lineage and review. Its manifest binds the participating book versions and integration hash. Raw full books are not copied into the candidate, though all cited passages are retained. The package remains a candidate until [controlled evaluation](evaluation.md) supports a scoped conclusion.

Set `comparison_kind: "fusion"` in the evaluation protocol. Freeze B1 as the previous/single-book skill and B2 as the independent multi-book materials without an integration policy. Compare B3 against both. Include cross-book reasoning, conflicting advice, missing selection conditions, out-of-scope cases, and old tasks that must not regress. Do not claim fusion helps merely because the artifact is longer or mentions more books.

Use `status`, `resume`, `pending`, `cancel`, and `history` as for a single-book run. `revise ... model` keeps the plan but invalidates the model, lineage and review. `revise ... plan` also clears the plan. `revise ... config` clears semantic integration work; `revise ... budget --config ...` changes only allowances. Previous packages are marked stale in the run and remain unchanged on disk.

To add or replace a book later, start a new fusion run from all the independently reviewed parent books; reuse unchanged parents. Do not feed a fused output back as if it were an independent book. Keep the previous fused skill as B1. Parent changes detected by `fusion-source-check` do not silently update frozen inputs or carry over an old review.

## Context and scale limits

Input books are read separately, source text stays on disk, and catalogs and reviews can be batched. Each book retains the existing 1–3 framework limit; the fused output also has 1–3 core frameworks. There is no fixed two-book ceiling, but pairwise comparison and snapshots cost more as inputs grow. Every smallest review packet, including the complete output model and integration plan, must fit the configured context allowance. The tool fails on overflow rather than removing boundaries. Narrow the capability or plan multiple separately evaluated skills when the minimum complete context cannot fit. No arbitrary-length or arbitrary-book-count guarantee is made.

## Compile for daily use

After packaging the reviewed integration, follow [Application compilation](runtime.md). Preserve independent parent interpretations in the external audit and decision-changing differences in runtime modules. Do not require `integration.json` or the evidence corpus on every invocation. A compact runtime remains bound to its original model, bridges and review. For oversized research inputs use `context-page --ids <qualified-id> --max-bytes 24000`, finish all cursor pages, and retain cross-batch conflicts. This pages the full research closure; runtime application uses separately reviewed decision units.
