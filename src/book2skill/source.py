"""Ordered document snapshots with exact normalized Unicode-codepoint offsets."""

import hashlib
from collections import Counter
from pathlib import Path
import re

from .contracts import VERSION
from .extractors import MAX_INPUT_BYTES, extract
from .storage import require, text_hash


def heading_chunks(text, base, offset=0, parse_headings=True):
    """Partition without losing whitespace or treating fenced code as headings."""
    headings, fence = [], None
    start, section, chunk_start = 0, base[:], 0
    chunks = []
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line.rstrip("\n"))
        heading = None if fence or not parse_headings else re.match(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if heading:
            if start > chunk_start:
                chunks.append((offset + chunk_start, offset + start, section[:]))
            level = len(heading[1])
            headings = [(n, t) for n, t in headings if n < level]
            headings.append((level, heading[2]))
            section = base + [t for _, t in headings]
            chunk_start = start
        if marker:
            if fence is None:
                fence = (marker[1][0], len(marker[1]))
            elif marker[1][0] == fence[0] and len(marker[1]) >= fence[1] and not marker[2].strip():
                fence = None
        start += len(line)
    if start > chunk_start:
        chunks.append((offset + chunk_start, offset + start, section[:]))
    return chunks


def ingest(paths, max_chars=1800):
    require(max_chars > 0, "segment size must be positive")
    require(paths, "at least one source is required")
    sources, segments, warnings = [], [], []
    for file_index, filename in enumerate(paths, 1):
        path = Path(filename).resolve()
        require(path.stat().st_size <= MAX_INPUT_BYTES, "source exceeds 256 MiB import limit; split the source explicitly")
        raw = path.read_bytes()
        units, metadata, extraction_warnings = extract(path, raw)
        text = "".join(u["text"] for u in units)
        require(text.strip(), f"empty source: {path}")
        require("\x00" not in text, f"NUL bytes in {path.name}; inspect source encoding")
        sid = f"source-{file_index:03d}"
        source = {"schema_version": VERSION, "id": sid, "filename": path.name,
                  "original_path": str(path), "order": file_index,
                  "raw_sha256": hashlib.sha256(raw).hexdigest(),
                  "text_sha256": text_hash(text), "normalization": metadata["parser"],
                  "text": text, "original_location": None, "extraction": metadata,
                  "location_note": {
                      "text": "Markdown headings and normalized character offsets; original pages unknown",
                      "epub": "EPUB spine order and archive href; supplements explicitly marked; no printed page numbers",
                      "pdf": "1-based PDF file page, not printed book page; text extraction is not visual reading or OCR",
                  }[metadata["format"]], "units": []}
        sources.append(source)
        warnings.extend(f"{sid}: {w}" for w in extraction_warnings)
        if "\ufffd" in text:
            warnings.append(f"{sid}: replacement characters detected; inspect encoding/extraction")
        if re.search(r"!\[|<img|<table|\$\$", text, re.I):
            warnings.append(f"{sid}: images/tables/formulas may need manual inspection")
        offset = 0
        for unit in units:
            unit_end = offset + len(unit["text"])
            source["units"].append({**{k: v for k, v in unit.items() if k not in ("text", "location")},
                                    "start_char": offset, "end_char": unit_end,
                                    "original_location": unit["location"]})
            base = [path.name] + ([unit["title"]] if unit["title"] else [])
            for begin, end, structure in heading_chunks(unit["text"], base, offset, metadata["format"] != "pdf"):
                while begin < end:
                    stop = min(begin + max_chars, end)
                    if stop < end:
                        boundary = text.rfind("\n", begin + max_chars // 2, stop)
                        if boundary > begin:
                            stop = boundary + 1
                    segments.append({"schema_version": VERSION, "id": f"segment-{len(segments) + 1:06d}",
                                     "source_id": sid, "structure_path": structure,
                                     "start_char": begin, "end_char": stop,
                                     "sha256": text_hash(text[begin:stop]), "original_location": unit["location"]})
                    begin = stop
            offset = unit_end
    counts = Counter(s["sha256"] for s in segments)
    if any(n > 1 for n in counts.values()):
        warnings.append("duplicate segments detected; confirm intentional repetition and file order")
    warnings.append("Automatic checks cannot establish completeness; host must inspect chapter order, omissions, figures and formulas.")
    return sources, segments, warnings


def inspect(paths):
    sources, segments, warnings = ingest(paths)
    verify_sources({"sources": sources, "segments": segments})
    return {"sources": [{k: v for k, v in s.items() if k != "text"} for s in sources],
            "segment_count": len(segments), "quality_warnings": warnings,
            "policy": "Read-only import preview. Coverage describes extracted text, not complete visual or semantic reading."}


def verify_sources(state):
    source_map = {s["id"]: s for s in state["sources"]}
    for source in source_map.values():
        require(text_hash(source["text"]) == source["text_sha256"], "normalized source hash mismatch")
        cursor = 0
        for segment in (s for s in state["segments"] if s["source_id"] == source["id"]):
            require(segment["start_char"] == cursor, "gap or overlap in source coverage")
            cursor = segment["end_char"]
            require(cursor > segment["start_char"] and cursor <= len(source["text"]), "invalid source offset")
            require(text_hash(source["text"][segment["start_char"]:cursor]) == segment["sha256"], "segment hash mismatch")
        require(cursor == len(source["text"]), "source tail missing")
        if "units" in source:
            cursor, unit_index = 0, 0
            for unit in source["units"]:
                require(unit["start_char"] == cursor and unit["end_char"] > cursor,
                        "gap or overlap in source units")
                cursor = unit["end_char"]
            require(cursor == len(source["text"]), "source unit tail missing")
            for segment in (s for s in state["segments"] if s["source_id"] == source["id"]):
                while source["units"][unit_index]["end_char"] <= segment["start_char"]:
                    unit_index += 1
                unit = source["units"][unit_index]
                require(segment["end_char"] <= unit["end_char"] and
                        segment["original_location"] == unit["original_location"],
                        "segment crosses a source location or has an inconsistent locator")


def passages(state, refs):
    sources = {s["id"]: s for s in state["sources"]}
    segments = {s["id"]: s for s in state["segments"]}
    require(len(refs) == len(set(refs)), "duplicate source references")
    require(set(refs) <= segments.keys(), f"unknown source reference: {set(refs) - segments.keys()}")
    result = []
    for ref in refs:
        s = segments[ref]
        source = sources[s["source_id"]]
        result.append({**s, "text": source["text"][s["start_char"]:s["end_char"]]})
    return result


def sample_refs(state):
    segments = state["segments"]
    candidates = [0, len(segments) // 4, len(segments) // 2, 3 * len(segments) // 4, len(segments) - 1]
    for i, s in enumerate(segments):
        if re.search(r"目录|前言|序言|结论|结语|后记|contents|preface|conclusion", " ".join(s["structure_path"]), re.I):
            candidates.append(i)
    return [segments[i]["id"] for i in sorted(set(candidates))]
