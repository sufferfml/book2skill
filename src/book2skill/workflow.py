"""Host-agent tasks with persisted evidence, review gates and bounded context."""

from pathlib import Path
import uuid

from . import __version__
from .contracts import Invalid, VERSION, validate
from .source import ingest, passages, sample_refs, verify_sources
from .storage import canonical, commit, digest, load, lock, now, require

CONTENT_KEYS = ["config", "sources", "segments", "readings", "decisions", "model", "review", "review_parts"]
GUIDANCE = {
    "decision": "Assess content × purpose from actual passages, not genre. Disclose sampling gaps. Review a proposed stop independently. Do not confuse absent-in-sample with absent-in-book.",
    "reading": "Record discoveries, premises, exceptions, counterexamples, later corrections and cross-chapter questions. Do not replace source with a chapter summary. Exclude only with a concrete reason.",
    "model": "Reconstruct 1–3 frameworks using cross-chapter relations. Each relation needs its own source support. Distinguish author_explicit, author_reconstructed and model_extension. Include mechanism, boundaries, conflicting evidence, situational mapping and revision tests. Do not invent implicit author claims.",
    "review": "Reread the supplied original evidence. Review every claim AND relation; exact locator validity is not semantic support. Check frameworks for unsupported extra generalizations. Return unresolved issues explicitly. Extensions can only be hypotheses. Use a separate review context.",
}


def initialize(root, paths, config):
    validate("config", config)
    require(config["context_reserve"] < config["context_capacity"], "context reserve consumes entire capacity")
    with lock(root):
        require(not (Path(root) / "HEAD.json").exists(), "run exists; use status/resume or a new directory")
        sources, segments, warnings = ingest(paths)
        state = {"schema_version": VERSION, "tool_version": __version__,
                 "run_id": "run-" + uuid.uuid4().hex[:12], "revision": 0,
                 "created_at": now(), "updated_at": now(), "events": [],
                 "config": config, "sources": sources, "segments": segments,
                 "quality_warnings": warnings,
                 "coverage": {s["id"]: {"status": "unread", "reading_id": None} for s in segments},
                 "readings": {}, "decisions": {}, "model": None, "review": None, "review_parts": [],
                 "stage": "ingested", "status": "waiting_input", "outcome": "candidate",
                 "pending": None, "attempts": [], "packages": [], "revisions": [], "access_log": []}
        verify_sources(state)
        commit(root, state, "initialize")
    return status(root)


def basis(state):
    return digest({k: state[k] for k in CONTENT_KEYS + ["books", "input_records", "integration", "lineage"] if k in state})


def usage_summary(state):
    usage = [a["usage"] for a in state["attempts"] if a.get("usage") is not None]
    return {"calls": len(state["attempts"]),
            "known_cost_usd": sum(u["cost_usd"] or 0 for u in usage),
            "unknown_cost_calls": sum(a.get("usage") is None or a["usage"]["cost_usd"] is None or a["usage"]["uncertain"] for a in state["attempts"]),
            "input_tokens": None if len(usage) != len(state["attempts"]) or any(u["input_tokens"] is None for u in usage) else sum(u["input_tokens"] for u in usage),
            "output_tokens": None if len(usage) != len(state["attempts"]) or any(u["output_tokens"] is None for u in usage) else sum(u["output_tokens"] for u in usage)}


def next_step(s):
    if s["pending"]:
        return f"submit or cancel pending task {s['pending']['id']}"
    if s["status"] == "budget_stopped":
        return "inspect usage; explicitly revise budget before issuing another task"
    if s["outcome"] in ("reference_only", "insufficient_evidence"):
        return "retain decision and evidence; revise scope/source only with a documented reason"
    if "prescreen" not in s["decisions"]:
        return "prepare decision --phase prescreen"
    if any(c["status"] == "unread" for c in s["coverage"].values()):
        return "prepare reading for unread segments"
    if s["model"] is None:
        return "prepare model; reread cross-chapter evidence with context"
    if s["review"] is None:
        return "prepare review in a separate context"
    if s["outcome"] == "needs_revision":
        return "revise model using source-backed failure attribution"
    if "review" not in s["decisions"]:
        return "prepare decision --phase review"
    return "package candidate; evaluate in fresh contexts with frozen B0–B3 protocol"


def status(root):
    if load(root).get("kind") == "fusion":
        from . import fusion
        return fusion.status(root)
    s = load(root)
    verify_sources(s)
    counts = {key: sum(c["status"] == key for c in s["coverage"].values()) for key in ("unread", "read", "excluded")}
    return {"schema_version": VERSION, "run_id": s["run_id"], "revision": s["revision"],
            "stage": s["stage"], "status": s["status"], "outcome": s["outcome"],
            "purpose": s["config"]["purpose"], "coverage": counts, "usage": usage_summary(s),
            "model_hash": digest(s["model"]) if s["model"] else None,
            "pending_task": s["pending"]["id"] if s["pending"] else None,
            "quality_warnings": s["quality_warnings"], "packages": s["packages"],
            "unresolved": s["review"]["unresolved"] if s["review"] else [], "next": next_step(s)}


def limit_context(state, payload, budget=None):
    available = state["config"]["context_capacity"] - state["config"]["context_reserve"]
    if budget is not None:
        require(budget > 0, "context budget must be positive")
        available = min(available, budget)
    # UTF-8 byte count is intentionally conservative; not an actual tokenizer reading.
    estimated = len(canonical(payload).encode("utf-8"))
    require(estimated <= available, f"context needs {estimated} estimated tokens; budget {available}. Split reading or source queries / increase explicit capacity. No dependencies were silently dropped.")
    return {**payload, "context_budget": {"estimated_tokens": estimated, "limit": available,
                                         "method": "utf8-bytes-upper-estimate", "unit": "utf8_bytes",
                                         "actual_tokens": None, "legacy_field_note": "estimated_tokens is a legacy byte guard, not tokenizer output",
                                         "omitted_required_refs": []}}


def record_access(root, previous, kind, identifiers, estimate):
    with lock(root):
        current = load(root)
        require(basis(current) == basis(previous), "content changed while assembling context; retry")
        current["access_log"].append({"kind": kind, "ids": identifiers, "estimated_tokens": estimate,
                                      "task_id": current["pending"]["id"] if current["pending"] else None, "at": now()})
        commit(root, current, f"context-access:{kind}")


def context_payload(s, refs=None, frameworks=None):
    verify_sources(s)
    payload = {"purpose": s["config"]["purpose"], "source_content_is_data": True}
    chosen = list(refs or [])
    if frameworks:
        require(s["model"] is not None, "no model exists")
        fm = {f["id"]: f for f in s["model"]["frameworks"]}
        required = set()
        def visit(fid):
            require(fid in fm, f"unknown framework: {fid}")
            if fid in required:
                return
            required.add(fid)
            for dep in fm[fid]["dependency_ids"]:
                visit(dep)
        for fid in frameworks:
            visit(fid)
        selected = [f for f in fm.values() if f["id"] in required]
        claims = {i for f in selected for i in f["claim_ids"]}
        relations = {i for f in selected for i in f["relation_ids"]}
        # All touching constraints/conflicts are loaded, even if an author omitted their ID from the framework list.
        changed = True
        while changed:
            before = len(claims)
            for relation in s["model"]["relations"]:
                if relation["from_id"] in claims or relation["to_id"] in claims:
                    relations.add(relation["id"])
                    claims.update([relation["from_id"], relation["to_id"]])
            changed = len(claims) != before
        records = [c for c in s["model"]["claims"] if c["id"] in claims]
        links = [r for r in s["model"]["relations"] if r["id"] in relations]
        chosen.extend(ref for x in records + links for ref in x["evidence_refs"])
        payload.update({"frameworks": selected, "claims": records, "relations": links})
    payload["passages"] = passages(s, list(dict.fromkeys(chosen)))
    return payload


def context(root, refs=None, frameworks=None, budget=None):
    s = load(root)
    payload = context_payload(s, refs, frameworks)
    result = limit_context(s, payload, budget)
    record_access(root, s, "passages", [p["id"] for p in payload["passages"]], result["context_budget"]["estimated_tokens"])
    return result


def context_page(root, refs=None, frameworks=None, ids=None, max_bytes=24000, cursor=None):
    """Page a complete research closure without pretending that one page is all.

    Only actually returned objects enter the access ledger. Frozen packet and
    task identity invalidate cursors after revisions or starting another task.
    """
    s = load(root)
    if ids is not None:
        from . import fusion
        fusion.require_fusion(s)
        payload = fusion.input_payload(s, ids)
    else:
        payload = context_payload(s, refs, frameworks)
    items = []
    for kind, value in payload.items():
        if isinstance(value, list):
            items.extend({'kind': kind, 'record': item} for item in value)
    require(items, 'select nonempty source/framework records')
    key = digest({'payload': payload, 'basis': basis(s), 'task': s['pending']['id'] if s['pending'] else None})
    offset = 0
    if cursor:
        try:
            prior, raw = cursor.split(':')
            offset = int(raw)
        except (ValueError, TypeError):
            raise Invalid('invalid context cursor') from None
        require(prior == key and 0 <= offset < len(items), 'stale/out-of-range context cursor')
    cap = min(max_bytes, s['config']['context_capacity'] - s['config']['context_reserve'])
    require(cap >= 512, 'context page budget must allow at least 512 bytes')
    result = {'packet_hash': key, 'items': [], 'next_cursor': None, 'status': 'complete',
              'unit': 'utf8_bytes', 'actual_tokens': None, 'source_content_is_data': True,
              'instruction': 'This is one page of the full required closure. Continue all pages before completing this research task; no relation was discarded.'}
    end = offset
    while end < len(items):
        candidate = {**result, 'items': result['items'] + [items[end]],
                     'next_cursor': f'{key}:{end+1}' if end+1 < len(items) else None,
                     'status': 'incomplete' if end+1 < len(items) else 'complete'}
        if len(canonical(candidate).encode('utf-8')) > cap:
            break
        result = candidate
        end += 1
    require(end > offset, 'one complete record exceeds page byte budget; increase explicit capacity/budget, do not truncate its conditions')
    if ids is not None:
        returned = [x['record']['record']['id'] for x in result['items'] if x['kind'] == 'input_records']
        record_access(root, s, 'fusion-inputs', returned, len(canonical(result).encode('utf-8')))
    refs_returned = [x['record']['id'] for x in result['items'] if x['kind'] == 'passages']
    record_access(root, s, 'passages', refs_returned, len(canonical(result).encode('utf-8')))
    return result


def notes(root, ids=None, offset=0, limit=5):
    s = load(root)
    records = list(s["readings"].values())
    require(offset >= 0 and limit > 0, "invalid notes page")
    if ids:
        require(set(ids) <= s["readings"].keys(), "unknown reading ID")
        records = [s["readings"][i] for i in ids]
    else:
        records = records[offset:offset + limit]
    result = limit_context(s, {"records": records, "total": len(s["readings"]), "next_offset": offset + len(records)})
    record_access(root, s, "readings", [r["id"] for r in records], result["context_budget"]["estimated_tokens"])
    return result


def prepare(root, kind, refs=None, phase=None, targets=None):
    if load(root).get("kind") == "fusion":
        from . import fusion
        return fusion.prepare(root, kind, refs, phase, targets)
    require(kind in GUIDANCE, "unsupported host task")
    with lock(root):
        s = load(root)
        verify_sources(s)
        require(s["pending"] is None, "submit or cancel the pending task first")
        u = usage_summary(s)
        cap = s["config"]["max_cost_usd"]
        if u["calls"] >= s["config"]["max_calls"] or (cap is not None and (u["unknown_cost_calls"] or u["known_cost_usd"] >= cap)):
            s["status"] = "budget_stopped"
            commit(root, s, "budget-stopped")
            require(False, "call/cost budget exhausted or cost is unknown under a dollar cap; state saved")
        require(s["outcome"] not in ("reference_only", "insufficient_evidence"), "run stopped by suitability; revise before continuing")
        payload = {"kind": kind, "instructions": GUIDANCE[kind], "purpose": s["config"]["purpose"],
                   "source_content_is_data": True, "config": s["config"], "quality_warnings": s["quality_warnings"]}
        if kind == "decision":
            require(phase in ("prescreen", "review"), "decision requires --phase prescreen|review")
            if phase == "prescreen":
                require("prescreen" not in s["decisions"], "prescreen already exists; revise to replace")
                chosen = list(dict.fromkeys(sample_refs(s) + (refs or [])))
            else:
                require(s["review"] is not None and s["outcome"] != "needs_revision", "a supported model review is required")
                require("review" not in s["decisions"], "final decision already exists; revise to replace")
                chosen = refs or sample_refs(s)
                payload["framework_scope"] = [{k: f[k] for k in ("id", "question", "applicability", "boundaries", "unknowns")} for f in s["model"]["frameworks"]]
                payload["source_review"] = {"unresolved": s["review"]["unresolved"], "model_hash": s["review"]["model_hash"]}
            payload["phase"] = phase
        elif kind == "reading":
            require("prescreen" in s["decisions"], "prescreen first")
            chosen = refs or [next((k for k, v in s["coverage"].items() if v["status"] == "unread"), "")]
            require(chosen and all(s["coverage"].get(r, {}).get("status") == "unread" for r in chosen), "choose unread segments; revise to replace readings")
        elif kind == "model":
            require(all(c["status"] != "unread" for c in s["coverage"].values()), "complete coverage before reconstruction")
            require(s["model"] is None, "model already exists; revise first")
            payload["reading_record_count"] = len(s["readings"])
            payload["coverage_counts"] = dict(__import__("collections").Counter(c["status"] for c in s["coverage"].values()))
            chosen = refs or []
            payload["instructions"] += " Retrieve persistent reading records in bounded pages with notes and source-index. Read primary evidence with context before submitting. All records remain on disk; they are not silently summarized into this request."
        else:
            require(s["model"] is not None and s["review"] is None, "model required and review must not already exist")
            all_items = s["model"]["claims"] + s["model"]["relations"]
            finished = {item["target_id"] for part in s["review_parts"] for item in part["items"]}
            selected = set(targets or [i["id"] for i in all_items if i["id"] not in finished])
            require(selected and selected <= {i["id"] for i in all_items} - finished, "choose unreviewed claim/relation targets")
            items = [i for i in all_items if i["id"] in selected]
            dependencies = {r[key] for r in items if "from_id" in r for key in ("from_id", "to_id")}
            payload["review_targets"] = items
            payload["endpoint_claims"] = [c for c in s["model"]["claims"] if c["id"] in dependencies]
            payload["frameworks"] = [f for f in s["model"]["frameworks"] if selected & set(f["claim_ids"] + f["relation_ids"])]
            payload["model_hash"] = digest(s["model"])
            chosen = list(dict.fromkeys(ref for item in items + payload["endpoint_claims"] for ref in item["evidence_refs"]))
        payload["passages"] = passages(s, chosen)
        payload = limit_context(s, payload)
        task = {"id": "task-" + uuid.uuid4().hex[:12], "kind": kind, "phase": phase,
                "input_hash": basis(s), "payload": payload, "created_at": now()}
        s["pending"] = task
        s["attempts"].append({"id": task["id"], "kind": kind, "status": "pending", "usage": None})
        s["status"] = "running"
        commit(root, s, f"prepare:{task['id']}")
        return task


def unique_records(records):
    require(len({r["id"] for r in records}) == len(records), "duplicate object IDs")


def validate_model(s, data):
    records = data["claims"] + data["relations"] + data["frameworks"]
    unique_records(records)
    claims = {c["id"]: c for c in data["claims"]}
    links = {r["id"]: r for r in data["relations"]}
    frameworks = {f["id"]: f for f in data["frameworks"]}
    for obj in data["claims"] + data["relations"]:
        refs = obj["evidence_refs"]
        passages(s, refs)
        require(all(s["coverage"][r]["status"] == "read" for r in refs), "evidence must refer to read, non-excluded segments")
        require(obj["epistemic_origin"] == "model_extension" or refs, "author claims/relations require source evidence")
    for r in links.values():
        require(r["from_id"] in claims and r["to_id"] in claims, "relation endpoint missing")
        require(r["from_id"] != r["to_id"], "self relation is not a cross-claim argument")
    cross = False
    segments = {x["id"]: x for x in s["segments"]}
    for f in frameworks.values():
        require(set(f["claim_ids"]) <= claims.keys(), "framework claim missing")
        require(set(f["relation_ids"]) <= links.keys(), "framework relation missing")
        require(set(f["dependency_ids"]) <= frameworks.keys(), "framework dependency missing")
        for rid in f["relation_ids"]:
            r = links[rid]
            require({r["from_id"], r["to_id"]} <= set(f["claim_ids"]), "framework must include its relation endpoints")
            sections = {(segments[x]["source_id"], tuple(segments[x]["structure_path"])) for x in r["evidence_refs"]}
            cross = cross or (len(sections) >= 2 and r["epistemic_origin"] != "model_extension")
    def visit(fid, stack):
        require(fid not in stack, "cyclic framework dependency")
        for other in frameworks[fid]["dependency_ids"]:
            visit(other, stack | {fid})
    for fid in frameworks:
        visit(fid, set())
    require(cross, "second-level candidate requires an author-grounded relation across structural units; do not fabricate one to pass")


def submit(root, task_id, data, usage):
    if load(root).get("kind") == "fusion":
        from . import fusion
        return fusion.submit(root, task_id, data, usage)
    validate("usage", usage)
    with lock(root):
        s = load(root)
        # Retrying an identical accepted response never consumes a second call.
        prior = next((a for a in s["attempts"] if a["id"] == task_id and a["status"] == "succeeded"), None)
        if prior:
            require(prior["result_hash"] == digest(data) and prior["usage"] == usage, "task already committed with a different result")
            return status(root)
        t = s["pending"]
        require(t is not None and t["id"] == task_id, "task is not the current pending request")
        require(t["input_hash"] == basis(s), "task dependencies changed; cancel and prepare again")
        require(usage["id"] == task_id and usage["status"] == "succeeded", "usage must identify the succeeded task")
        kind = t["kind"]
        validate(kind, data)
        if kind == "decision":
            require(data["phase"] == t["phase"], "wrong decision phase")
            supplied = {p["id"] for p in t["payload"]["passages"]}
            require(set(data["sample_refs"]) <= supplied and set(data["evidence_refs"]) <= set(data["sample_refs"]), "decision evidence must be in its declared, supplied sample")
            if data["phase"] == "prescreen":
                require(set(sample_refs(s)) <= set(data["sample_refs"]), "prescreen must cover the prepared representative sample")
            if data["decision"] in ("reference_only", "insufficient_evidence"):
                require(bool(data["second_review"].strip()), "stopping decisions need an explicit second review, not a genre shortcut")
                s["outcome"] = data["decision"]
                s["status"] = "completed"
            else:
                require(data["candidate_scope"], "candidate scope required")
                s["outcome"] = "candidate"
            s["decisions"][data["phase"]] = data
            s["stage"] = "screened" if data["phase"] == "prescreen" else "reviewed"
        elif kind == "reading":
            require(data["id"] not in s["readings"], "reading ID already exists")
            require(set(data["segment_ids"]) == {p["id"] for p in t["payload"]["passages"]}, "reading must account for every supplied segment")
            require(len(data["segment_ids"]) == len(set(data["segment_ids"])), "duplicate coverage IDs")
            s["readings"][data["id"]] = data
            for ref in data["segment_ids"]:
                s["coverage"][ref] = {"status": data["disposition"], "reading_id": data["id"]}
            s["stage"] = "reading"
        elif kind == "model":
            validate_model(s, data)
            required_refs = {r for obj in data["claims"] + data["relations"] for r in obj["evidence_refs"]}
            accessed = {p["id"] for p in t["payload"]["passages"]}
            accessed.update(ref for access in s["access_log"] if access["task_id"] == task_id and access["kind"] == "passages" for ref in access["ids"])
            require(required_refs <= accessed, "reconstruction must reread all cited source segments via context during this task; reading-note coverage alone is insufficient")
            s["model"] = data
            s["stage"] = "modeled"
        elif kind == "review":
            require(data["model_hash"] == digest(s["model"]), "review is for a different model version")
            items = t["payload"]["review_targets"]
            require(len({i["target_id"] for i in data["items"]}) == len(data["items"]), "duplicate review target")
            reviewed = {i["target_id"]: i for i in data["items"]}
            require(set(reviewed) == {i["id"] for i in items}, "review all and only prepared targets")
            for item in items:
                result = reviewed[item["id"]]
                require(set(result["evidence_refs"]) == set(item["evidence_refs"]), "review must account for all linked evidence")
                if item["epistemic_origin"] == "model_extension":
                    require(result["verdict"] != "supported", "a model extension cannot be marked author-supported")
                else:
                    require(result["verdict"] != "hypothesis", "downgrade origin explicitly before treating an author claim as a hypothesis")
            s["review_parts"].append(data)
            merged = [i for part in s["review_parts"] for i in part["items"]]
            if len(merged) == len(s["model"]["claims"]) + len(s["model"]["relations"]):
                s["review"] = {"schema_version": VERSION, "model_hash": data["model_hash"],
                               "reviewer": "; ".join(dict.fromkeys(p["reviewer"] for p in s["review_parts"])),
                               "items": merged, "unresolved": [u for part in s["review_parts"] for u in part["unresolved"]]}
                s["stage"] = "reviewed"
                if s["review"]["unresolved"] or any(i["verdict"] in ("unsupported", "uncertain") for i in merged):
                    s["outcome"] = "needs_revision"
        attempt = next(a for a in s["attempts"] if a["id"] == task_id)
        attempt.update({"status": "succeeded", "usage": usage, "result_hash": digest(data)})
        s["pending"] = None
        if s["status"] != "completed":
            s["status"] = "waiting_input"
        commit(root, s, f"submit:{task_id}")
    return status(root)


def cancel(root, task_id, reason, usage=None):
    if usage:
        validate("usage", usage)
        require(usage["id"] == task_id and usage["status"] != "succeeded", "cancellation usage must describe a failed/unknown attempt")
    with lock(root):
        s = load(root)
        require(s["pending"] and s["pending"]["id"] == task_id, "no matching pending task")
        attempt = next(a for a in s["attempts"] if a["id"] == task_id)
        attempt.update({"status": "failed" if usage else "unknown", "reason": reason, "usage": usage})
        s["pending"] = None
        s["status"] = "failed"
        commit(root, s, f"cancel:{task_id}")
    return status(root)


def revise(root, target, reason, config=None):
    if load(root).get("kind") == "fusion":
        from . import fusion
        return fusion.revise(root, target, reason, config)
    require(reason.strip(), "revision reason required")
    with lock(root):
        s = load(root)
        require(not s["pending"], "cancel pending task before revising")
        require(target in ("model", "reading", "prescreen", "config", "budget"), "unknown revision target")
        old_basis = basis(s)
        if target in ("config", "budget"):
            validate("config", config)
            require(config["context_reserve"] < config["context_capacity"], "invalid context capacity")
            if target == "budget":
                nonbudget = set(config) - {"context_capacity", "context_reserve", "max_calls", "max_cost_usd"}
                require(all(config[k] == s["config"][k] for k in nonbudget), "budget revision cannot change semantic configuration")
            s["config"] = config
        if target != "budget":
            if target in ("reading", "prescreen", "config"):
                s["readings"] = {}
                s["coverage"] = {k: {"status": "unread", "reading_id": None} for k in s["coverage"]}
            if target in ("prescreen", "config"):
                s["decisions"] = {}
            s["decisions"].pop("review", None)
            s["model"] = None
            s["review"] = None
            s["review_parts"] = []
            for package in s["packages"]:
                package["stale"] = True
            s["outcome"] = "candidate"
            s["stage"] = "reading" if "prescreen" in s["decisions"] else "ingested"
        s["revisions"].append({"target": target, "reason": reason, "previous_basis": old_basis, "at": now()})
        s["status"] = "waiting_input"
        commit(root, s, f"revise:{target}")
    return status(root)
