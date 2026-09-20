# Compile an application skill

Keep the independently reviewed research model as the source of truth. `package` exports that immutable research artifact for compatibility and audit. Before installing a newly generated skill, compile a separate `runtime-1` application package. Do not compress a previously compressed runtime: recover its bound research archive first. Reuse unchanged reviewed book runs; compilation does not require rereading unchanged whole books.

## Author an application plan

`B2S` means `python3 <skill-directory>/scripts/book2skill.pyz`.

```sh
B2S runtime-template research-package --out runtime-draft.json
B2S schema runtime-plan --out runtime-plan.schema.json
```

The draft includes a source catalog for authoring; retain the optional `catalog` unchanged or remove it before submission. Fill `core`, `modules`, `archive_only` and optional `spans`; replace placeholders. Use the target task to choose modules, not book chapters. The number of application modules is independent of the 1–3 research frameworks.

Shared core contains genuinely shared decision constraints and origin policy. Each module specifies `id`, `title`, `when`, `text`, `source_ids`, mandatory `requires` and conditional routes (`module_id`, `condition`). Preserve causal mechanisms, observations that change the decision, competing explanations, boundaries, counterexamples and revision triggers. No mandatory answer template. Unknown conditional triggers must be checked, not assumed false. A required dependency cycle blocks compilation; split shared invariants into the core instead of dropping an edge.

Every source claim, relationship, framework, bridge, input disposition, scope statement and existing application helper must map into a core/module or receive an explicit `archive_only` reason. A source ID appearing in the mapping is not proof its meaning survived. Independent review must check the actual application text. Origins (`author_explicit`, `author_reconstructed`, `cross_book_synthesis`, `model_extension`) remain in source records; runtime text must distinguish synthesis and extensions without printing the full graph. New conclusions require upstream revision or an explicitly reviewed extension, never hidden compression.

Original passages are retained unchanged by default and read only on demand. To offer shorter evidence views, author `spans` with passage ID, SHA256 of its text, Unicode `start`/`end`, and selection reason. Check negation, pronoun referents, conditions and later corrections against the original. Reviewers must read selected spans and the complete relevant original passage. Exact substring checks establish integrity, not semantic adequacy. `--full` retrieves the preserved full segment; it is not a complete-book reread.

## Review and compile

```sh
B2S runtime-review-request research-package --plan runtime-plan.json --out review-request.json
B2S template runtime-review --out review.json
# A separately authorized review context completes every request target.
B2S compile-package research-package runtime-skill --plan runtime-plan.json --review review.json --audit audit-v1 --version 0.0.1 --evidence bundled
B2S validate-package runtime-skill
```

Review source/core/module mappings, alternatives, all decision-changing constraints, conditional routing and archive-only reasons. Every target needs an attributable rationale. `revise`, unresolved findings, stale hashes, missing targets or the builder's own context block compilation. Review identity is an operator attestation, not authenticated isolation. The review gate does not authorize spawning agents on its own.

Plan, source and review hashes bind the runtime to a separate immutable audit containing the original research package. Audit-first creation is recoverable: rerun only with the same verified audit and a new/nonexistent runtime destination. Changing any source or plan requires a newly bound review. Keep old packages intact; do not inherit prior transfer evaluations. `--evidence locators` emits no excerpts, and verification then reports unavailable sources explicitly. This distribution choice is not a copyright permission check.

## Apply, explain, verify

The generated entry lists decision routes. Use `scripts/read_context.py apply <module-id> ...` to return shared core and required units. Its default 12,000-character budget covers the entire compact JSON output, excluding its final newline. It counts characters, not tokens. Paginate with the returned cursor and exactly the same query; no record is silently clipped. If one complete unit exceeds the budget, narrow the task or explicitly increase the allowance. The model must finish required pages before a complete judgment.

`explain <source-id>` returns selected structured records. `evidence <source-id>` returns their source passages or reviewed spans. These modes do not recursively expand the source graph and must not replace application modules for preserving boundaries. Disputed attribution, ambiguous premises and explicit source questions trigger verification; ordinary analysis does not read all evidence or the audit. Missing original books/images remain unavailable, never inferred from successful parsing.

Optional `--seen <unit-id> ... --acknowledge <snapshot-hash>` avoids returning known units only within a still-valid context. After compaction, reset and reload required units. Optional `--log /external/path/events.jsonl` records returned IDs/characters, not user facts. Logs must remain outside the immutable package. Tool delivery does not prove comprehension; the tool cannot enforce total host context use or prevent direct file reads.

## Measure the result

Use on-demand evaluation to test actual retrieval; do not inject the entire package. Compare the previous and compiled skill on identical development scenarios before independent held-out evaluation. Track mandatory-boundary errors, actual returned material, repeats, failures, latency and provider usage when available. Unknown tokens/cost remain null. Smaller disk files alone are not evidence of lower context use; source review and application-compilation review are not transfer validation.
