# Importing and quality checks (0.0.3)

`B2S` means `python3 <absolute-skill-path>/scripts/book2skill.pyz`. The runtime does not access the network, install dependencies, or call models automatically.

```sh
B2S inspect '/absolute/path/book.epub' --out preview.json
B2S init runs/book-epub '/absolute/path/book.epub' --config config.json
B2S inspect '/absolute/path/book.pdf' --out preview-pdf.json
B2S init runs/book-pdf '/absolute/path/book.pdf' --config config.json
```

`inspect` creates an extraction preview without creating a run. The preview contains source hashes, chapter/page units, quality warnings, and segment counts, but not full text. `init` uses the same extraction logic and saves an immutable text snapshot. See [Workflow](workflow.md) for configuration. Quote file paths. Multiple files are concatenated in argument order, which the operator must confirm.

| Input | Order and locations | Limitations to check |
|---|---|---|
| Markdown/TXT | UTF-8, preserving headings and normalized character offsets | Image references, tables, and formulas are not automatically understood semantically |
| EPUB | container → OPF → spine; each segment retains archive href, spine index, and the linear attribute | Non-spine HTML is explicitly marked supplemental and appended; this is not the author's main reading order. HTML headings, paragraphs, and table cells are extracted in document order |
| PDF | Page-by-page extraction in file order; each segment carries a 1-based file-page number | File pages are not printed page labels. Check columns, rotated text, complex tables, footnotes, and formulas against the layout; segment order does not establish logical reading order |

EPUB uses a local parser; PDF uses bundled pypdf 6.10.0. Each source retains the original-file SHA-256 and normalized-text SHA-256. Segment offsets refer to extracted text, not PDF byte offsets. Segments do not cross PDF pages or EPUB content units. Limits are 256 MiB per source file, 512 MiB of expanded EPUB content, and 32 MiB per XML/HTML member. Explicitly split source material that exceeds these limits.

## Images and scans

- Inline EPUB images leave an image-not-parsed marker. Alternative text is not evidence of visual inspection. The preview reports image-asset counts and units without readable body text.
- PDF import performs neither OCR nor image reading. Textless pages retain placeholders and page locations and appear in `textless_pages`. They may be blank pages, figures, or scans; do not automatically exclude them.
- Import fails when no readable body text can be extracted from the entire file. Supply OCR text, a text-layer PDF, or a visual transcription first. Unreadable encrypted content, corrupt files, and missing spine chapters fail without committing a partially successful run.
- A successful mixed-PDF import still requires handling unread scanned pages. When external OCR is needed, generate new source material, record the tool, version, omissions, and manual verification scope, then create a new run. Do not inherit previous source-review results.
- Complete coverage means only that every **extracted text segment** has a disposition. Without inspecting essential canvases or figures, do not claim whole-book reading or mark placeholders as understood. Save visual transcriptions in the workspace with the original-file hash, EPUB href/PDF page, and implications. Changes to normalized source text require a new run.

## Existing runs

Markdown/TXT snapshots created with 0.0.1 still support `status/resume/context/source-check`. The software version is 0.0.3; the compatible data-contract version remains 0.0.1. Existing snapshots are not rewritten, and segments from a new-format import are not treated as old evidence. Restart from prescreening after reimporting EPUB/PDF sources. Multi-book integration freezes eligible independently reviewed runs; it does not reinterpret a multi-file import as different books.
