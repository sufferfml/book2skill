"""Behavioral invariants for the engineering workflow, not a test of LLM understanding."""

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "examples")]
from book2skill import __version__, evaluation, packaging, workflow
from book2skill.contracts import Invalid, VERSION, validate
from book2skill.source import ingest, passages, verify_sources
from book2skill.storage import commit, digest, load, load_json, lock, write_json
from run_demo import build_candidate, config, decision, model_for, protocol_for, usage


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.run = self.base / "run"

    def init(self, conf=None):
        workflow.initialize(self.run, [ROOT / "examples/synthetic-book.md"], conf or config())

    def screen(self):
        task = workflow.prepare(self.run, "decision", phase="prescreen")
        workflow.submit(self.run, task["id"], decision(task), usage(task))
        return task

    def candidate(self):
        path = self.base / "candidate"
        build_candidate(self.run, path)
        return path

    def test_unicode_order_and_full_offsets(self):
        one, two = self.base / "one.txt", self.base / "two.md"
        one.write_bytes("\ufeff甲🙂\r\n乙\r丁".encode())
        two.write_text("# B\n\nsecond\n" + "长🙂" * 3000, encoding="utf-8")
        sources, segments, _ = ingest([one, two], max_chars=100)
        s = {"sources": sources, "segments": segments}
        verify_sources(s)
        self.assertEqual(sources[0]["text"], "甲🙂\n乙\n丁")
        self.assertEqual(sources[1]["order"], 2)
        recovered = "".join(p["text"] for p in passages(s, [x["id"] for x in segments]))
        self.assertEqual(recovered, "".join(x["text"] for x in sources))
        self.assertIsNone(segments[0]["original_location"])
        nested = self.base / "fenced.md"
        nested.write_text("# Actual\n````markdown\n```\n# Not a chapter\n```\n````\n## Next\nend", encoding="utf-8")
        _, fenced_segments, _ = ingest([nested])
        self.assertEqual([s["structure_path"][-1] for s in fenced_segments], ["Actual", "Next"])

    def test_snapshot_survives_interrupted_head_switch(self):
        self.init()
        before = load(self.run)
        modified = copy.deepcopy(before)
        modified["outcome"] = "needs_revision"
        import book2skill.storage as storage
        original = storage.os.replace
        def crash(src, dst):
            if Path(dst).name == "HEAD.json":
                raise OSError("simulated interruption")
            return original(src, dst)
        with patch.object(storage.os, "replace", crash), self.assertRaises(OSError):
            commit(self.run, modified, "interrupted")
        self.assertEqual(load(self.run), before)
        task = workflow.prepare(self.run, "decision", phase="prescreen")
        self.assertEqual(load(self.run)["pending"]["id"], task["id"])

    def test_lock_prevents_concurrent_writer(self):
        self.init()
        code = "from pathlib import Path; from book2skill.storage import lock; import sys\nwith lock(Path(sys.argv[1])): print('unsafe')\n"
        with lock(self.run):
            import os
            result = subprocess.run([sys.executable, "-c", code, str(self.run)], env={**os.environ, "PYTHONPATH": str(ROOT / "src")}, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("unsafe", result.stdout)
        with lock(self.run):
            pass

    def test_task_recovery_idempotency_and_changed_retry(self):
        self.init()
        task = workflow.prepare(self.run, "decision", phase="prescreen")
        self.assertEqual(load(self.run)["pending"], task)
        data = decision(task)
        workflow.submit(self.run, task["id"], data, usage(task))
        rev = load(self.run)["revision"]
        workflow.submit(self.run, task["id"], data, usage(task))
        self.assertEqual(load(self.run)["revision"], rev)
        data["rationale"] = "changed"
        with self.assertRaises(Invalid):
            workflow.submit(self.run, task["id"], data, usage(task))

    def test_decline_requires_review_and_preserves_valid_stop(self):
        for outcome in ("reference_only", "insufficient_evidence"):
            self.run = self.base / outcome
            self.init()
            task = workflow.prepare(self.run, "decision", phase="prescreen")
            data = decision(task, outcome=outcome)
            data["second_review"] = ""
            with self.assertRaises(Invalid):
                workflow.submit(self.run, task["id"], data, usage(task))
            data["second_review"] = "reviewed sample; additional full text required"
            workflow.submit(self.run, task["id"], data, usage(task))
            self.assertEqual(workflow.status(self.run)["outcome"], outcome)
            with self.assertRaises(Invalid):
                workflow.prepare(self.run, "reading")

    def test_prescreen_sample_cannot_silently_shrink(self):
        self.init()
        task = workflow.prepare(self.run, "decision", phase="prescreen")
        data = decision(task)
        data["sample_refs"] = data["sample_refs"][:1]
        data["evidence_refs"] = data["sample_refs"]
        with self.assertRaises(Invalid):
            workflow.submit(self.run, task["id"], data, usage(task))

    def test_unread_material_blocks_model_and_package(self):
        self.init()
        self.screen()
        with self.assertRaises(Invalid):
            workflow.prepare(self.run, "model")
        with self.assertRaises(Invalid):
            packaging.package(self.run, self.base / "bad", "bad", VERSION)

    def test_call_budget_saved_and_explicitly_resumable(self):
        conf = config()
        conf["max_calls"] = 1
        self.init(conf)
        self.screen()
        with self.assertRaises(Invalid):
            workflow.prepare(self.run, "reading")
        self.assertEqual(workflow.status(self.run)["status"], "budget_stopped")
        conf["max_calls"] = 3
        workflow.revise(self.run, "budget", "explicit increase", conf)
        workflow.prepare(self.run, "reading")
        self.assertEqual(workflow.status(self.run)["usage"]["calls"], 2)

    def test_unknown_cost_stops_dollar_capped_run(self):
        conf = config()
        conf["max_cost_usd"] = 2
        self.init(conf)
        self.screen()
        with self.assertRaises(Invalid):
            workflow.prepare(self.run, "reading")
        self.assertEqual(workflow.status(self.run)["usage"]["unknown_cost_calls"], 1)

    def test_cancel_retains_uncertain_attempt(self):
        self.init()
        task = workflow.prepare(self.run, "decision", phase="prescreen")
        workflow.cancel(self.run, task["id"], "host disconnected")
        s = load(self.run)
        self.assertEqual(s["attempts"][0]["status"], "unknown")
        self.assertIsNone(s["pending"])
        self.assertEqual(workflow.status(self.run)["usage"]["calls"], 1)

    def test_foreign_refs_and_fabricated_relation_rejected(self):
        self.candidate()
        workflow.revise(self.run, "model", "test reference checks")
        task = workflow.prepare(self.run, "model")
        data = model_for(load(self.run))
        data["relations"][0]["evidence_refs"] = ["segment-999999"]
        with self.assertRaises(Invalid):
            workflow.submit(self.run, task["id"], data, usage(task))
        data = model_for(load(self.run))
        data["relations"][0]["to_id"] = "claim-missing"
        with self.assertRaises(Invalid):
            workflow.submit(self.run, task["id"], data, usage(task))
        self.assertIsNone(load(self.run)["model"])

    def test_reconstruction_requires_source_reread_in_current_task(self):
        self.candidate()
        workflow.revise(self.run, "model", "fresh reconstruction")
        task = workflow.prepare(self.run, "model")
        data = model_for(load(self.run))
        with self.assertRaisesRegex(Invalid, "reread"):
            workflow.submit(self.run, task["id"], data, usage(task))
        refs = list(dict.fromkeys(r for i in data["claims"] + data["relations"] for r in i["evidence_refs"]))
        workflow.context(self.run, refs)
        workflow.submit(self.run, task["id"], data, usage(task))
        self.assertTrue(load(self.run)["access_log"])

    def test_package_recovers_completed_rename_without_duplicate_or_overwrite(self):
        candidate = self.candidate()
        s = load(self.run)
        s["packages"] = []
        s["stage"] = "reviewed"
        commit(self.run, s, "simulate missing final package checkpoint")
        before = (candidate / "manifest.json").read_bytes()
        result = packaging.package(self.run, candidate, "tidal-supply-demo", VERSION)
        self.assertTrue(result["reused"])
        self.assertEqual(len(load(self.run)["packages"]), 1)
        rev = load(self.run)["revision"]
        packaging.package(self.run, candidate, "tidal-supply-demo", VERSION)
        self.assertEqual(load(self.run)["revision"], rev)
        self.assertEqual((candidate / "manifest.json").read_bytes(), before)
        with self.assertRaises(Invalid):
            packaging.package(self.run, candidate, "tidal-supply-demo", "0.0.2")

    def test_failed_semantic_review_blocks_packaging(self):
        self.candidate()
        workflow.revise(self.run, "model", "review failure")
        task = workflow.prepare(self.run, "model")
        model = model_for(load(self.run))
        workflow.context(self.run, list(dict.fromkeys(r for i in model["claims"] + model["relations"] for r in i["evidence_refs"])))
        workflow.submit(self.run, task["id"], model, usage(task))
        task = workflow.prepare(self.run, "review")
        items = [{"target_id": i["id"], "verdict": "hypothesis" if i["epistemic_origin"] == "model_extension" else "supported", "evidence_refs": i["evidence_refs"], "rationale": "fixture"} for i in model["claims"] + model["relations"]]
        items[0]["verdict"] = "unsupported"
        data = {"schema_version": VERSION, "model_hash": digest(model), "reviewer": "fixture", "items": items, "unresolved": []}
        workflow.submit(self.run, task["id"], data, usage(task))
        self.assertEqual(workflow.status(self.run)["outcome"], "needs_revision")
        with self.assertRaises(Invalid):
            packaging.package(self.run, self.base / "bad", "bad", VERSION)

    def test_extension_cannot_be_certified_as_author_statement(self):
        self.candidate()
        s = load(self.run)
        self.assertEqual(next(i for i in s["review"]["items"] if i["target_id"] == "claim-transfer")["verdict"], "hypothesis")
        workflow.revise(self.run, "model", "source-origin check")
        task = workflow.prepare(self.run, "model")
        model = model_for(load(self.run))
        workflow.context(self.run, list(dict.fromkeys(r for i in model["claims"] + model["relations"] for r in i["evidence_refs"])))
        workflow.submit(self.run, task["id"], model, usage(task))
        task = workflow.prepare(self.run, "review", targets=["claim-transfer"])
        review = {"schema_version": VERSION, "model_hash": digest(model), "reviewer": "test", "items": [{"target_id": "claim-transfer", "verdict": "supported", "evidence_refs": [], "rationale": "bad attribution"}], "unresolved": []}
        with self.assertRaises(Invalid):
            workflow.submit(self.run, task["id"], review, usage(task))

    def test_context_keeps_later_constraints_and_fails_instead_of_truncating(self):
        self.candidate()
        result = workflow.context(self.run, frameworks=["framework-probe"])
        self.assertIn("claim-tide", {c["id"] for c in result["claims"]})
        self.assertIn("claim-irreversible", {c["id"] for c in result["claims"]})
        self.assertEqual(len(result["passages"]), 5)
        with self.assertRaises(Invalid):
            workflow.context(self.run, frameworks=["framework-probe"], budget=100)

    def test_portable_candidate_and_hash_verification(self):
        package = self.candidate()
        other = self.base / "copied"
        shutil.copytree(package, other)
        shutil.rmtree(self.run)
        self.assertTrue(packaging.validate_package(other)["valid"])
        all_text = "".join(p.read_text(encoding="utf-8") for p in other.rglob("*") if p.is_file())
        self.assertNotIn(str(self.base), all_text)
        with (other / "frameworks/framework-probe.md").open("a") as f:
            f.write("tampered")
        with self.assertRaises(Invalid):
            packaging.validate_package(other)

    def test_revision_invalidates_downstream_without_destroying_old_version(self):
        package = self.candidate()
        before = (package / "manifest.json").read_bytes()
        workflow.revise(self.run, "model", "new counterexample")
        state = load(self.run)
        self.assertIsNone(state["model"])
        self.assertIsNone(state["review"])
        self.assertTrue(state["packages"][0]["stale"])
        self.assertNotIn("review", state["decisions"])
        self.assertTrue(state["readings"])
        self.assertEqual((package / "manifest.json").read_bytes(), before)
        self.assertGreater(len(list((self.run / "checkpoints").iterdir())), 2)

    def test_source_snapshot_survives_external_edit_but_hash_tampering_fails(self):
        source = self.base / "book.md"
        source.write_text("# 1\n原文", encoding="utf-8")
        workflow.initialize(self.run, [source], config())
        source.write_text("changed", encoding="utf-8")
        self.assertIn("原文", workflow.context(self.run, ["segment-000001"])["passages"][0]["text"])
        head = load_json(self.run / "HEAD.json")
        p = self.run / "checkpoints" / head["snapshot"] / "state.json"
        p.write_text(p.read_text().replace("原文", "伪造"), encoding="utf-8")
        with self.assertRaises(Invalid):
            workflow.status(self.run)

    def test_long_book_uses_bounded_notes_not_one_enormous_model_request(self):
        source = self.base / "long.md"
        source.write_text("# synthetic\n" + "".join(f"## Chapter {i}\n" + "文字" * 1000 + "\n" for i in range(40)), encoding="utf-8")
        workflow.initialize(self.run, [source], config())
        # Set up a large persisted reading layer as an explicit engineering fixture.
        s = load(self.run)
        for index, segment in enumerate(s["segments"]):
            rid = f"reading-{index}"
            s["readings"][rid] = {"schema_version": VERSION, "id": rid, "segment_ids": [segment["id"]], "disposition": "read", "reason": "fixture", "discoveries": ["细节" * 1000], "conditions": [], "counterexamples": [], "connections": [], "questions": []}
            s["coverage"][segment["id"]] = {"status": "read", "reading_id": rid}
        s["decisions"]["prescreen"] = {"fixture": True}
        commit(self.run, s, "engineering fixture")
        task = workflow.prepare(self.run, "model")
        self.assertNotIn("readings", task["payload"])
        self.assertGreater(task["payload"]["reading_record_count"], 40)
        self.assertEqual(len(workflow.notes(self.run, limit=1)["records"]), 1)

    def test_json_rejects_duplicates_nonfinite_and_wrong_types(self):
        p = self.base / "bad.json"
        for text in ('{"a":1,"a":2}', '{"a":NaN}'):
            p.write_text(text)
            with self.assertRaises(Invalid):
                load_json(p)
        c = config()
        c["max_calls"] = True
        with self.assertRaises(Invalid):
            validate("config", c)

    def test_zipapp_operates_outside_repository_without_site_packages(self):
        path = self.base / "book2skill.pyz"
        shutil.copyfile(ROOT / "skill/book2skill/scripts/book2skill.pyz", path)
        result = subprocess.run([sys.executable, "-I", "-S", str(path), "--version"], cwd=self.base, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), __version__)
        config_file = self.base / "config.json"
        write_json(config_file, config())
        source = self.base / "source.md"
        source.write_text("# test\n\nComplete synthetic input.", encoding="utf-8")
        result = subprocess.run([sys.executable, "-I", "-S", str(path), "init", str(self.run), str(source), "--config", str(config_file)], cwd=self.base, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["stage"], "ingested")
        result = subprocess.run([sys.executable, "-I", "-S", str(path), "task", str(self.run), "decision", "--phase", "prescreen"], cwd=self.base, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["kind"], "decision")


class EvaluationTests(unittest.TestCase):
    setUp = WorkflowTests.setUp
    candidate = WorkflowTests.candidate

    def frozen(self):
        candidate = self.candidate()
        p = protocol_for(self.base / "materials", candidate)
        ev = self.base / "evaluation"
        evaluation.freeze(ev, p)
        return ev, p

    def answer(self, task, status="succeeded", context_id=None):
        return {"schema_version": VERSION, "job_id": task["job_id"], "status": status,
                "answer": "engineering response" if status == "succeeded" else "", "error": "failure" if status == "failed" else "",
                "model": task["model"], "host": task["host"], "context_id": context_id or "ctx-" + task["job_id"], "fresh_context": True,
                "actual_material_chars": sum(len(x["text"]) for x in task["material"]),
                "input_tokens": None, "output_tokens": None, "cost_usd": 0, "duration_seconds": 0, "uncertain": False}

    def score(self, packet, reviewer="simulated-model"):
        return {"schema_version": VERSION, "review_id": packet["review_id"], "reviewer": reviewer, "reviewer_type": "model",
                "scores": {d: 1 for d in ("mapping", "boundaries", "fidelity", "action", "revision")},
                "boundary_error": False, "fabricated_attribution": False, "concealed_gap": False,
                "failure_types": [], "rationale": "engineering fixture only", "human_checked": False}

    def test_freeze_copies_material_and_rejects_overwrite(self):
        ev, p = self.frozen()
        before = load(ev)["material_hashes"]
        Path(p["conditions"][1]["material_path"]).write_text("modified", encoding="utf-8")
        self.assertEqual(load(ev)["material_hashes"], before)
        with self.assertRaises(Invalid):
            evaluation.freeze(ev, p)

    def test_executor_and_blind_judge_packets_have_no_condition_or_expected_leak(self):
        ev, _ = self.frozen()
        t = evaluation.issue(ev)
        self.assertNotIn("expected_behaviors", t)
        self.assertNotIn("condition", t)
        self.assertNotIn("family", t)
        self.assertEqual(t, evaluation.issue(ev))
        evaluation.submit_answer(ev, self.answer(t))
        packet = evaluation.review_packet(ev, t["job_id"])
        self.assertIn("expected_behaviors", packet)
        self.assertNotIn("condition", packet)
        self.assertNotIn("job_id", packet)
        self.assertIn("source_evidence", packet)

    def test_reused_context_and_config_mismatch_rejected(self):
        ev, _ = self.frozen()
        t = evaluation.issue(ev)
        answer = self.answer(t, context_id="shared")
        answer["model"] = "other"
        with self.assertRaises(Invalid):
            evaluation.submit_answer(ev, answer)
        answer["model"] = t["model"]
        evaluation.submit_answer(ev, answer)
        t2 = evaluation.issue(ev)
        with self.assertRaises(Invalid):
            evaluation.submit_answer(ev, self.answer(t2, context_id="shared"))

    def test_failure_retry_preserves_error_and_budget(self):
        ev, _ = self.frozen()
        t = evaluation.issue(ev)
        evaluation.submit_answer(ev, self.answer(t, "failed"))
        evaluation.retry(ev, t["job_id"], "transient")
        j = next(x for x in load(ev)["jobs"] if x["id"] == t["job_id"])
        self.assertEqual(j["attempts"][0]["error"], "failure")
        self.assertEqual(evaluation.evaluation_status(ev)["usage"]["calls"], 1)
        self.assertEqual(j["status"], "pending")

    def test_incomplete_or_exploratory_results_never_pass(self):
        ev, _ = self.frozen()
        report = evaluation.report(ev)
        self.assertEqual(report["outcome"], "insufficient_evidence")
        self.assertTrue(any("16 jobs" in x for x in report["reasons"]))
        for _ in range(16):
            t = evaluation.issue(ev)
            evaluation.submit_answer(ev, self.answer(t))
            evaluation.submit_score(ev, self.score(evaluation.review_packet(ev, t["job_id"])))
        report = evaluation.report(ev)
        self.assertEqual(report["outcome"], "insufficient_evidence")
        self.assertTrue(any("exploratory" in x for x in report["reasons"]))
        self.assertEqual(report["execution_usage"]["calls"], 16)

    def test_model_cannot_declare_human_review_and_critical_errors_need_adjudication(self):
        ev, _ = self.frozen()
        t = evaluation.issue(ev)
        evaluation.submit_answer(ev, self.answer(t))
        sc = self.score(evaluation.review_packet(ev, t["job_id"]))
        sc["human_checked"] = True
        with self.assertRaises(Invalid):
            evaluation.submit_score(ev, sc)
        sc["human_checked"] = False
        sc["fabricated_attribution"] = True
        evaluation.submit_score(ev, sc)
        self.assertTrue(any("human adjudication" in x for x in evaluation.report(ev)["reasons"]))

    def test_contaminated_cases_cannot_support_unseen_claim(self):
        ev, _ = self.frozen()
        evaluation.contaminate(ev, ["case-0"], "used to edit framework")
        self.assertTrue(any("exposed" in x for x in evaluation.report(ev)["reasons"]))

    def test_formal_gate_rejects_small_or_insufficient_budget_protocol(self):
        ev, p = self.frozen()
        p["mode"] = "formal"
        with self.assertRaises(Invalid):
            evaluation.freeze(self.base / "formal", p)
        p["mode"] = "exploratory"
        p["max_calls"] = 1
        with self.assertRaises(Invalid):
            evaluation.freeze(self.base / "no-budget", p)

    def test_formal_report_requires_consistent_gain_and_no_critical_failure(self):
        candidate = self.candidate()
        p = protocol_for(self.base / "materials", candidate)
        originals = p["cases"]
        p["cases"] = []
        for index in range(28):
            case = copy.deepcopy(originals[index % 4])
            case.update({"id": f"formal-case-{index}", "input": f"engineering-only scenario {index}", "split": "dev" if index < 8 else "heldout"})
            p["cases"].append(case)
        p.update({"mode": "formal", "repetitions": 2, "max_calls": 180})
        p["conditions"][2]["provenance"] = "test-only upstream identity " + "a" * 40
        ev = self.base / "formal"
        evaluation.freeze(ev, p)
        state = load(ev)
        # Deliberately fabricated in-memory responses test report arithmetic, never model capability.
        for j in state["jobs"]:
            j["status"] = "succeeded"
            j["answer"] = {"answer": "report-engine fixture"}
            sc = self.score({"review_id": j["review_id"]})
            sc["scores"] = {k: 2 if j["condition"] == "B3" else 1 for k in sc["scores"]}
            j["scores"] = [sc]
        commit(ev, state, "report-engine-only-fixture")
        self.assertEqual(evaluation.report(ev)["outcome"], "validated_scoped")
        state = load(ev)
        for j in state["jobs"]:
            if j["condition"] == "B3" and j["repeat"] == 2:
                j["scores"][0]["scores"] = {k: 0 for k in j["scores"][0]["scores"]}
        commit(ev, state, "inconsistent second repeat")
        self.assertEqual(evaluation.report(ev)["outcome"], "insufficient_evidence")
        state = load(ev)
        for j in state["jobs"]:
            if j["condition"] == "B3":
                j["scores"][0]["scores"] = {k: 2 for k in j["scores"][0]["scores"]}
        j = next(x for x in state["jobs"] if x["condition"] == "B3")
        j["scores"][0]["fabricated_attribution"] = True
        commit(ev, state, "critical author attribution error")
        self.assertEqual(evaluation.assess(ev)["outcome"], "insufficient_evidence")
        self.assertEqual(load(ev)["stage"], "assessed")

    def test_duplicate_input_cannot_cross_development_and_heldout(self):
        ev, p = self.frozen()
        duplicate = copy.deepcopy(p["cases"][0])
        duplicate.update({"id": "duplicate-dev", "split": "dev"})
        p["cases"].append(duplicate)
        with self.assertRaisesRegex(Invalid, "duplicate case inputs"):
            evaluation.freeze(self.base / "leaked", p)


if __name__ == "__main__":
    unittest.main()
