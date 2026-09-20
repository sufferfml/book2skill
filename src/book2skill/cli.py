"""CLI and host-file ModelPort. JSON stdout is stable; errors go to stderr."""

import argparse
import json
from pathlib import Path
import sys

from . import __version__, compilation, evaluation, fusion, packaging, workflow
from .contracts import SCHEMAS, Invalid, schema, template, validate
from .source import inspect
from .storage import atomic_text, history, load, load_json, require, write_json


def parser():
    p = argparse.ArgumentParser(prog="book2skill", description="Recoverable book-framework skill workflow (host-agent semantic execution)")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)
    def cmd(name, help_text, run=False):
        s = sub.add_parser(name, help=help_text)
        if run:
            s.add_argument("run", type=Path)
        s.add_argument("--out", type=Path, help="write JSON result atomically to this path")
        return s
    s = cmd("inspect", "preview EPUB/PDF/UTF-8 text extraction without creating a run")
    s.add_argument("sources", nargs="+", type=Path)
    s = cmd("init", "import ordered EPUB/PDF/UTF-8 text files", True)
    s.add_argument("sources", nargs="+", type=Path)
    s.add_argument("--config", required=True, type=Path)
    s = cmd("fusion-init", "freeze independently reviewed book runs for integration", True)
    s.add_argument("--books", required=True, type=Path)
    s.add_argument("--config", required=True, type=Path)
    s = cmd("fusion-catalog", "page through independently extracted input records", True)
    s.add_argument("--offset", type=int, default=0)
    s.add_argument("--limit", type=int, default=20)
    s = cmd("fusion-context", "load input frameworks with complete constraints and evidence", True)
    s.add_argument("--ids", nargs="+", required=True)
    s.add_argument("--budget", type=int)
    s = cmd('context-page', 'page a complete research closure with honest byte accounting', True)
    s.add_argument('--segments', nargs='+')
    s.add_argument('--frameworks', nargs='+')
    s.add_argument('--ids', nargs='+', help='fusion input IDs; cannot combine with single-book selectors')
    s.add_argument('--max-bytes', type=int, default=24000)
    s.add_argument('--cursor')
    cmd("fusion-source-check", "compare current parent runs against frozen input versions", True)
    for name in ("status", "resume", "history", "pending", "source-check"):
        cmd(name, "inspect persisted run state", True)
    s = cmd("source-index", "page through source structure and coverage", True)
    s.add_argument("--offset", type=int, default=0)
    s.add_argument("--limit", type=int, default=20)
    s = cmd("notes", "read persisted reading records in bounded pages", True)
    s.add_argument("--ids", nargs="+")
    s.add_argument("--offset", type=int, default=0)
    s.add_argument("--limit", type=int, default=5)
    s = cmd("context", "load source passages and complete framework dependencies", True)
    s.add_argument("--segments", nargs="+")
    s.add_argument("--frameworks", nargs="+")
    s.add_argument("--budget", type=int)
    s = cmd("task", "reserve and persist a host-agent semantic task", True)
    s.add_argument("kind", choices=["decision", "reading", "model", "review", "fusion-plan", "fusion-model", "fusion-review"])
    s.add_argument("--segments", nargs="+")
    s.add_argument("--targets", nargs="+", help="claim/relation IDs for a bounded review batch")
    s.add_argument("--phase", choices=["prescreen", "review"])
    s = cmd("submit", "validate and commit a host-agent result", True)
    s.add_argument("task_id")
    s.add_argument("--data", required=True, type=Path)
    s.add_argument("--usage", required=True, type=Path)
    s = cmd("cancel", "record interrupted or failed task", True)
    s.add_argument("task_id")
    s.add_argument("--reason", required=True)
    s.add_argument("--usage", type=Path)
    s = cmd("revise", "invalidate downstream state with a reason", True)
    s.add_argument("target", choices=["model", "reading", "prescreen", "config", "budget", "plan"])
    s.add_argument("--reason", required=True)
    s.add_argument("--config", type=Path)
    s = cmd("package", "create an immutable portable candidate skill", True)
    s.add_argument("destination", type=Path)
    s.add_argument("--name", required=True)
    s.add_argument("--version", required=True)
    s = cmd("validate-package", "check candidate checksums and references")
    s.add_argument("path", type=Path)
    s = cmd('runtime-template', 'catalog a research package for host-authored application compilation')
    s.add_argument('source', type=Path)
    s = cmd('runtime-review-request', 'bind independent compilation review to source and plan')
    s.add_argument('source', type=Path)
    s.add_argument('--plan', type=Path, required=True)
    s = cmd('compile-package', 'create reviewed runtime and separate immutable audit')
    s.add_argument('source', type=Path)
    s.add_argument('destination', type=Path)
    s.add_argument('--plan', type=Path, required=True)
    s.add_argument('--review', type=Path, required=True)
    s.add_argument('--audit', type=Path, required=True)
    s.add_argument('--version', required=True)
    s.add_argument('--evidence', choices=['bundled', 'locators'], default='bundled')
    for name in ("schema", "template"):
        s = cmd(name, "export a data contract or an unfilled input template")
        s.add_argument("kind", choices=sorted(SCHEMAS))
    s = cmd("eval-freeze", "freeze protocol and materials outside the builder workspace", True)
    s.add_argument("--protocol", type=Path, required=True)
    for name in ("eval-next", "eval-status", "eval-report"):
        cmd(name, "operate frozen host-context evaluations", True)
    s = cmd("eval-answer", "import actual execution output", True)
    s.add_argument("--data", type=Path, required=True)
    s = cmd("eval-review", "emit blind scoring packet; evaluator only", True)
    s.add_argument("job_id")
    s = cmd("eval-score", "append an attributable review", True)
    s.add_argument("--data", type=Path, required=True)
    s = cmd("eval-retry", "retain failed attempt and queue retry", True)
    s.add_argument("job_id")
    s.add_argument("--reason", required=True)
    s = cmd("eval-contaminate", "mark heldout feedback used for revision", True)
    s.add_argument("case_ids", nargs="+")
    s.add_argument("--reason", required=True)
    return p


def execute(a):
    c = a.command
    if c == "fusion-init":
        inputs = load_json(a.books)
        validate("fusion-input", inputs)
        # Resolve book paths relative to the input manifest, independent of cwd.
        for book in inputs.get("books", []):
            if isinstance(book, dict) and isinstance(book.get("run_path"), str):
                book["run_path"] = str((a.books.resolve().parent / book["run_path"]).resolve())
        return fusion.initialize(a.run, inputs, load_json(a.config))
    if c == "fusion-catalog":
        return fusion.catalog(a.run, a.offset, a.limit)
    if c == "fusion-context":
        return fusion.context(a.run, a.ids, a.budget)
    if c == 'context-page':
        require(not (a.ids and (a.segments or a.frameworks)), 'do not combine fusion and single-book selectors')
        return workflow.context_page(a.run, a.segments, a.frameworks, a.ids, a.max_bytes, a.cursor)
    if c == "fusion-source-check":
        return fusion.source_check(a.run)
    if c == "inspect":
        return inspect(a.sources)
    if c == "init":
        return workflow.initialize(a.run, a.sources, load_json(a.config))
    if c in ("status", "resume"):
        return workflow.status(a.run)
    if c == "history":
        return history(a.run)
    if c == "pending":
        pending = load(a.run)["pending"]
        require(pending is not None, "no pending task")
        return pending
    if c == "source-check":
        import hashlib
        results = []
        for s in load(a.run)["sources"]:
            p = Path(s["original_path"])
            status = "unavailable" if not p.is_file() else "matching" if hashlib.sha256(p.read_bytes()).hexdigest() == s["raw_sha256"] else "changed"
            results.append({"source_id": s["id"], "original": status})
        return {"sources": results, "policy": "The run uses its immutable normalized snapshot. Import changed sources into a new run; do not inherit prior reviews."}
    if c == "source-index":
        require(a.offset >= 0 and a.limit > 0, "invalid index page")
        s = load(a.run)
        return workflow.limit_context(s, {"total": len(s["segments"]), "next_offset": a.offset + a.limit,
                                          "segments": [{**x, "coverage": s["coverage"][x["id"]]} for x in s["segments"][a.offset:a.offset + a.limit]]})
    if c == "notes":
        return workflow.notes(a.run, a.ids, a.offset, a.limit)
    if c == "context":
        return workflow.context(a.run, a.segments, a.frameworks, a.budget)
    if c == "task":
        return workflow.prepare(a.run, a.kind, a.segments, a.phase, a.targets)
    if c == "submit":
        return workflow.submit(a.run, a.task_id, load_json(a.data), load_json(a.usage))
    if c == "cancel":
        return workflow.cancel(a.run, a.task_id, a.reason, load_json(a.usage) if a.usage else None)
    if c == "revise":
        return workflow.revise(a.run, a.target, a.reason, load_json(a.config) if a.config else None)
    if c == "package":
        return packaging.package(a.run, a.destination, a.name, a.version)
    if c == "validate-package":
        return packaging.validate_package(a.path)
    if c == 'runtime-template':
        return compilation.template(a.source)
    if c == 'runtime-review-request':
        return compilation.review_request(a.source, load_json(a.plan))
    if c == 'compile-package':
        return compilation.compile_package(a.source, a.destination, load_json(a.plan), load_json(a.review), a.version, a.audit, a.evidence)
    if c == "schema":
        return schema(a.kind)
    if c == "template":
        return template(a.kind)
    if c == "eval-freeze":
        return evaluation.freeze(a.run, load_json(a.protocol))
    if c == "eval-next":
        return evaluation.issue(a.run)
    if c == "eval-status":
        return evaluation.evaluation_status(a.run)
    if c == "eval-answer":
        return evaluation.submit_answer(a.run, load_json(a.data))
    if c == "eval-review":
        return evaluation.review_packet(a.run, a.job_id)
    if c == "eval-score":
        return evaluation.submit_score(a.run, load_json(a.data))
    if c == "eval-retry":
        return evaluation.retry(a.run, a.job_id, a.reason)
    if c == "eval-contaminate":
        return evaluation.contaminate(a.run, a.case_ids, a.reason)
    if c == "eval-report":
        return evaluation.assess(a.run)
    raise Invalid(f"unknown command: {c}")


def main(argv=None):
    a = parser().parse_args(argv)
    try:
        result = execute(a)
        if a.out:
            if a.command == 'context-page':
                atomic_text(a.out, json.dumps(result, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n')
            else:
                write_json(a.out, result)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=None if a.command == 'context-page' else 2,
                             separators=(',', ':') if a.command == 'context-page' else None, allow_nan=False))
        return 0
    except (Invalid, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
