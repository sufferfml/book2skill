# Local workflow

This is the single-book extraction workflow. For two or more books, complete it independently for each book, then use [Multi-book integration](fusion.md). Passing several files to `init` means ordered parts of one book, not automatic multi-book synthesis.

In the commands below, `B2S` means `python3 <absolute-skill-path>/scripts/book2skill.pyz`; it is not another dependency. Expand it when running commands, or define a shell function with that name. Results default to JSON on stdout; `--out PATH` writes JSON atomically. Replace `task-actual-id` with the ID returned by `task`.

## Create a run

```sh
python3 scripts/book2skill.pyz template config --out config.json
```

Fill in the intended use, book version, language, current model, host, and prompt version. `context_capacity` is the context allowance available for tool material in this round; `context_reserve` reserves space for other instructions, tasks, tool results, and output. Configure both conservatively for the actual host. Legacy capacity fields are enforced with a conservative UTF-8 byte guard, not measured tokens. Reports label the unit explicitly and keep actual token usage unknown. The default template must be completed before it becomes a valid configuration.

`max_calls` limits semantic task reservations, including failed or uncertain calls. `max_cost_usd: null` means the tool sets no monetary cap; it does not mean execution is free. Record unknown host costs as `null`. Monetary limits are checked before issuing a task and cannot forcibly interrupt an in-flight host call.

```sh
B2S inspect book.epub --out extraction-preview.json
B2S init runs/my-book book.epub --config config.json
B2S status runs/my-book
B2S source-index runs/my-book --offset 0 --limit 20
B2S task runs/my-book decision --phase prescreen --out request.json
B2S template decision --out decision.json
B2S template usage --out usage.json
B2S submit runs/my-book task-actual-id --data decision.json --usage usage.json
```

Source files are imported in argument order. EPUB, text-layer PDF, and UTF-8 Markdown/TXT are supported; see [Importing](importing.md) for format details. The full extracted text is saved with normalized newlines and Unicode codepoint offsets `[start_char,end_char)`. EPUB retains spine/href locations; PDF retains file-page numbers. Do not invent unknown printed page numbers. Figure, formula, and encoding checks provide warnings only; the agent must record actual quality checks and their implications. Confirm multi-file order manually; the tool does not infer chapter order between files.

## Read in batches and recover

```sh
B2S task runs/my-book reading --segments segment-000001 segment-000002 --out request.json
B2S template reading --out reading.json
B2S submit runs/my-book task-actual-id --data reading.json --usage usage.json
B2S resume runs/my-book
B2S pending runs/my-book
B2S notes runs/my-book --offset 0 --limit 3
B2S context runs/my-book --segments segment-000002
```

Each reading submission must cover every segment supplied in that task. `excluded` requires a reason and is reserved for content that need not participate in the current framework analysis. Do not disguise unread content as irrelevant. Use separate tasks for different dispositions. Full source text remains available; segment boundaries are not argument boundaries, and adjacent segments can be reread together.

`task` persists a pending request and reserves a call. A validation failure commits no state; correct and resubmit the same result. If another model call is needed, first `cancel` the attempt with its usage, then issue a new task. Submitting an identical result is idempotent. If execution cannot be confirmed, retain the attempt with uncertain usage rather than deleting it.

Checkpoints reside in immutable directories, with `HEAD.json` as the sole authoritative pointer. A directory created before a crash without a completed pointer switch does not count as committed. Do not edit snapshots manually. Use `history` for commit history and `source-check` to detect changes to original files. The run continues to use its frozen snapshot; changed source material requires a new run.

## Reconstruct, review, and package

```sh
B2S task runs/my-book model --out request.json
B2S notes runs/my-book --offset 0 --limit 3
B2S context runs/my-book --segments segment-000003 segment-000010
B2S template model --out model.json
B2S submit runs/my-book task-actual-id --data model.json --usage usage.json
B2S task runs/my-book review --targets claim-a claim-b relation-limit --out review-request.json
B2S template review --out review.json
B2S submit runs/my-book task-actual-id --data review.json --usage usage.json
B2S task runs/my-book decision --phase review --out request.json
B2S submit runs/my-book task-actual-id --data final-decision.json --usage usage.json
B2S package runs/my-book dist/my-book/0.0.1 --name my-book --version 0.0.1
B2S validate-package dist/my-book/0.0.1
```

A model request supplies record counts and coverage; the agent loads saved notes in pages and rereads sources rather than placing the whole book in one input. Rereading does not change coverage and cannot replace reading submissions. Use `--targets` to batch reviews. Review is complete only after every claim and relationship is covered; unresolved issues block packaging.

If even the smallest task exceeds the context budget, split reading/review tasks or narrow the framework scope. Do not fabricate capacity or omit essential boundaries. Use `context-page --frameworks <id> --max-bytes 24000` (or `--segments`) to page a full research closure. Continue with the same selectors and `--cursor`; revisions and task changes invalidate cursors. If one indivisible record or task request is too large, split the semantic task or framework without discarding boundaries. Research models still contain at most three frameworks; compiled application modules can be more granular.

```sh
B2S revise runs/my-book model --reason 'A later passage limits a premise; reconstruct the affected relationships'
B2S revise runs/my-book config --config new-config.json --reason 'The intended use changed; repeat screening and reading'
B2S revise runs/my-book budget --config new-config.json --reason 'Explicitly increase the call allowance'
```

A `model` revision preserves sources and reading records, clears the current model/review/final screening, and marks previous packages stale. A `reading` revision also clears coverage. A `config` or `prescreen` revision restarts from prescreening. Invalidation conservatively clears the affected groups; older versions remain in checkpoints. Budget adjustments preserve semantic results. Packages in separate directories remain unchanged, and their evaluations do not automatically carry over.

## Application delivery

The research export above retains the full audit and supports legacy consumers. For daily installation, continue with [Application compilation](runtime.md). Keep core constraints and complete decision units in the runtime, use explicit conditional routes, and retrieve evidence only for a specific source question. Never manually strip boundaries to satisfy a size target.
