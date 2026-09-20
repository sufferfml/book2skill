# book2skill

[中文说明](README.zh-CN.md) · [MIT license](LICENSE) · [Download v0.0.4](https://github.com/sufferfml/book2skill/releases/tag/v0.0.4)

Reconstruct the reasoning scattered across a book into evidence-grounded frameworks, then compile a skill that applies those frameworks to new problems. For multiple books, extract and review each independently before deciding what to integrate, keep separate, or leave unresolved.

**Experimental, version 0.0.4.** The workflow and local tools run; improved reasoning or transfer to new problems has not been established by a formal held-out evaluation. The host agent reads, reasons, and reviews. Python handles extraction, evidence, state, validation, packaging, and evaluation records; it does not call an LLM.

## Install the skill

Requires Python 3.11+ on macOS or Linux and a host supporting local agent skills. The portable package includes pypdf 6.10.0: no separate dependency install or API key is needed for its local commands. Model access and costs belong to your host agent. Windows is not currently supported by the POSIX locking implementation.

Download `book2skill-0.0.4.zip` and `SHA256SUMS` from the release above. Verify the ZIP against its matching checksum, unzip it, then place the complete `book2skill/` folder in your host's skill directory. For a Codex setup using `~/.agents/skills`:

```sh
# From the directory containing the downloaded ZIP:
unzip book2skill-0.0.4.zip
mkdir -p ~/.agents/skills
# The test prevents replacing an existing installation.
test ! -e ~/.agents/skills/book2skill && cp -R book2skill ~/.agents/skills/book2skill
python3 -S ~/.agents/skills/book2skill/scripts/book2skill.pyz --version
```

Alternatively clone this repository and copy the whole `skill/book2skill/` folder. You can also use it in place without installing. Ask your host to load the explicit `SKILL.md` path if it has not discovered the skill yet. If you already have an installation, back it up outside the discovery directory before replacing it.

## Use it

Give your host agent a book, a purpose, and an output directory:

> Use book2skill to extract frameworks from `<book.epub>` for `<specific task>`. Check suitability first, reconstruct cross-chapter reasoning and boundaries, review source support, and create a candidate skill. Store working material in `<run-directory>` and clearly identify capabilities that have not been evaluated.

For another book:

> Independently extract `<new-book.pdf>`, then compare its assumptions and mechanisms with the reviewed sources behind `<existing-skill>`. Preserve conditional alternatives and the previous skill as a baseline. Integrate only where useful; keeping methods separate is acceptable.

An installed skill alone is not a reviewed source input. Extending it requires its research runs and evidence. Instructions are in English; responses and generated content may use the user's requested language.

## Workflow

1. Inspect EPUB, text-layer PDF, or UTF-8 Markdown/TXT; assess suitability for the intended use.
2. Read in batches with coverage records and resumable checkpoints.
3. Reconstruct claims, relations, frameworks, counterexamples, and limits across chapters.
4. Review source support in a fresh context and distinguish author statements, reconstructions, and model extensions.
5. For multiple books, freeze independently reviewed inputs, compare frameworks, preserve conflicts, and review the integration separately.
6. Preserve a research candidate, then compile a reviewed runtime with a common core, decision modules, bounded retrieval, and a separate audit archive.
7. Evaluate application on new cases before claiming transfer gains.

Start from [the skill](skill/book2skill/SKILL.md). Detailed instructions: [importing](skill/book2skill/references/importing.md), [extraction](skill/book2skill/references/workflow.md), [framework review](skill/book2skill/references/frameworks.md), [integration](skill/book2skill/references/fusion.md), [runtime compilation](skill/book2skill/references/runtime.md), and [evaluation](skill/book2skill/references/evaluation.md).

```sh
python3 -S skill/book2skill/scripts/book2skill.pyz --help
python3 -S skill/book2skill/scripts/book2skill.pyz inspect examples/synthetic-book.md
python3 -S skill/book2skill/scripts/book2skill.pyz template config --out config.json
# Fill the config, including your purpose, host/model identity, and budgets:
python3 -S skill/book2skill/scripts/book2skill.pyz init runs/my-book examples/synthetic-book.md --config config.json
python3 -S skill/book2skill/scripts/book2skill.pyz task runs/my-book decision --phase prescreen --out request.json
```

Follow `task → host semantic work → submit`. The CLI does not autonomously understand a book or orchestrate separate model sessions.

## Limits and publication

- No OCR. Textless PDFs are rejected; partially textless pages warn. Images, tables, formulas, and reading order may need human or visual review.
- Each single-book or integrated model currently has 1–3 core frameworks. Book count is not hard-coded to two, but pairwise comparison and minimum review context limit practical scale.
- Pagination, checkpoints, and explicit budgets help manage context; they do not guarantee unlimited book length or comprehension. If a required complete unit cannot fit, the tool stops rather than silently dropping its limits.
- Reviewer identities and context isolation depend on the host. Structural validation does not authenticate an independent reviewer or establish semantic correctness.
- No built-in Jev service, vector database, or external model API. Actual unknown token counts and costs remain unknown; character counts are not billed tokens.
- Default research/runtime packages may contain source excerpts. `compile-package --evidence locators` omits excerpts; original-text verification then reports unavailable sources. It does not automatically reconnect a user's copy of a book or clear copyright.

This repository distributes the generator, synthetic fixtures, and tests. It does not distribute commercial books, private research runs, or generated business skills. See [third-party and source rights](THIRD_PARTY_NOTICES.md).

## Develop and verify

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
python examples/run_demo.py runs/single-demo
python examples/run_fusion_demo.py runs/fusion-demo
python tools/build_skill.py
python tools/check_release.py
```

Use fresh demo destinations. Demos use authored synthetic records; they are engineering fixtures, not LLM performance results. The builder creates a deterministic portable ZIP, zipapp, JSON schemas, release manifest, and checksums in `dist/`. [Release procedure](docs/RELEASING.md) · [Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md).
