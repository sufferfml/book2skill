"""Scripted engineering demo. All semantic records are authored fixtures, not LLM evidence."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from book2skill import evaluation, packaging, workflow
from book2skill.contracts import VERSION
from book2skill.storage import digest, load, write_json


def config():
    return {"schema_version": VERSION, "purpose": "诊断虚构补给站的积压，设计可撤销的小规模验证", "book_version": "synthetic-1",
            "language": "zh-CN", "model": "scripted-fixture-no-model", "host": "python-engineering-demo",
            "prompt_version": "book2skill-0.0.1", "context_capacity": 64000, "context_reserve": 8000,
            "max_calls": 80, "max_cost_usd": None}


def usage(task):
    return {"schema_version": VERSION, "id": task["id"], "task": task["kind"], "status": "succeeded",
            "input_tokens": None, "output_tokens": None, "cost_usd": None, "duration_seconds": None, "uncertain": True}


def decision(task, phase="prescreen", outcome="whole"):
    refs = [p["id"] for p in task["payload"]["passages"]]
    return {"schema_version": VERSION, "phase": phase, "decision": outcome,
            "rationale": "人工样例明确给出诊断前提，并在后章限制局部试探；只用于测试工程流程。",
            "candidate_scope": ["虚构补给站的可撤销局部试探"], "sample_refs": refs, "evidence_refs": refs,
            "missing_information": ["不包含永久改造的评估方法"], "quality_notes": ["工程样例为完整 UTF-8 文本；顺序明确，无外部图表。"],
            "reviewer": "scripted-fixture", "second_review": "人工工程样例复核；并非独立模型结论" if outcome in ("reference_only", "insufficient_evidence") else ""}


def model_for(state):
    def ref(heading):
        return next(s["id"] for s in state["segments"] if heading in s["structure_path"][-1])
    first, probe, tide, irreversible, revise = [ref(x) for x in ("第一章", "第二章", "第三章", "第四章", "第五章")]
    descriptions = [
        ("claim-observe", "区分到达增加与处理能力下降，观察相同时间窗口的到达量、完成量、等待时间。", first),
        ("claim-probe", "到达相对稳定且可撤销时，单窗口只改变一道步骤以检验局部解释。", probe),
        ("claim-tide", "到达节律变化会使前后比较混入潮汐影响，需要匹配窗口或保留证据不足结论。", tide),
        ("claim-irreversible", "不可撤销变化不适用该试探方法；不能从短期结果推出永久改造价值。", irreversible),
        ("claim-revise", "结果不符预期时回查条件，条件成立仍无改善则降低原解释的可信度。", revise),
    ]
    claims = [{"id": cid, "statement": text, "epistemic_origin": "author_explicit", "evidence_refs": [r], "conditions": [], "unknowns": []} for cid, text, r in descriptions]
    relations = [
        {"id": "relation-observe", "from_id": "claim-probe", "to_id": "claim-observe", "kind": "depends_on", "explanation": "试探需要先区分流入变化与处理能力，采用相同窗口的观察。", "epistemic_origin": "author_reconstructed", "evidence_refs": [first, probe]},
        {"id": "relation-tide", "from_id": "claim-tide", "to_id": "claim-probe", "kind": "limits", "explanation": "第三章的潮汐扰动限制第二章前后比较的归因。", "epistemic_origin": "author_reconstructed", "evidence_refs": [probe, tide]},
        {"id": "relation-irreversible", "from_id": "claim-irreversible", "to_id": "claim-probe", "kind": "limits", "explanation": "第四章明确限制第二章可撤销试探的推广范围。", "epistemic_origin": "author_reconstructed", "evidence_refs": [probe, irreversible]},
        {"id": "relation-feedback", "from_id": "claim-revise", "to_id": "claim-probe", "kind": "limits", "explanation": "第五章要求检查失败并修正解释，不能无依据扩大试探。", "epistemic_origin": "author_reconstructed", "evidence_refs": [probe, revise]},
    ]
    framework = {"id": "framework-probe", "name": "有条件的局部试探", "kind": "diagnostic",
                 "question": "积压来自到达变化还是处理能力下降，局部改动是否支持该解释？",
                 "mechanism": "先分开流入和完成能力；仅在到达节律可比且可撤销时改变一道步骤，观察是否符合预测；相反证据触发条件复查和解释修订。",
                 "claim_ids": [c["id"] for c in claims], "relation_ids": [r["id"] for r in relations], "dependency_ids": [],
                 "applicability": ["到达节律相对稳定、时间窗口可比、调整可以撤销"],
                 "boundaries": ["潮汐窗口混淆归因；不可撤销改造不适用"],
                 "observations": ["同窗口到达量、完成量、等待时间；变化是否可撤销"],
                 "mapping": ["把待办任务映射为到达，把完成量映射为处理能力指标，先核对这种映射是否满足原条件"],
                 "alternatives": ["比较到达增加与局部能力受限两种解释"],
                 "checks": ["预先声明改变一个步骤后的可观察预测，在可比窗口观察"],
                 "revision": ["先回查条件，条件成立而未改善时降低原解释可信度"],
                 "unknowns": ["永久改造与备用能力的价值评估不在本框架中"]}
    # The generic task mapping is explicitly a model extension, not attributed to the fictional author.
    claims.append({"id": "claim-transfer", "statement": framework["mapping"][0], "epistemic_origin": "model_extension", "evidence_refs": [], "conditions": ["目标任务有可比流入与完成指标"], "unknowns": ["跨领域映射尚未验证"]})
    framework["claim_ids"].append("claim-transfer")
    return {"schema_version": VERSION, "claims": claims, "relations": relations, "frameworks": [framework]}


def build_candidate(run, destination, *, source=None, configuration=None, model_builder=None):
    workflow.initialize(run, [source or ROOT / "examples/synthetic-book.md"], configuration or config())
    task = workflow.prepare(run, "decision", phase="prescreen")
    workflow.submit(run, task["id"], decision(task), usage(task))
    for index, seg in enumerate(load(run)["segments"]):
        task = workflow.prepare(run, "reading", [seg["id"]])
        record = {"schema_version": VERSION, "id": f"reading-{index:03d}", "segment_ids": [seg["id"]], "disposition": "read",
                  "reason": "人工构造工程样例，逐单元登记", "discoveries": [seg["structure_path"][-1]],
                  "conditions": ["核对时间窗口与撤销条件"], "counterexamples": [], "connections": ["后文限制第二章试探"], "questions": []}
        workflow.submit(run, task["id"], record, usage(task))
    task = workflow.prepare(run, "model")
    model = (model_builder or model_for)(load(run))
    refs = list(dict.fromkeys(r for item in model["claims"] + model["relations"] for r in item["evidence_refs"]))
    workflow.context(run, refs)
    workflow.submit(run, task["id"], model, usage(task))
    # Exercise incremental evidence review and checkpoint assembly.
    for item in model["claims"] + model["relations"]:
        task = workflow.prepare(run, "review", targets=[item["id"]])
        review = {"schema_version": VERSION, "model_hash": digest(model), "reviewer": "scripted-fixture-not-independent-review",
                  "items": [{"target_id": item["id"], "verdict": "hypothesis" if item["epistemic_origin"] == "model_extension" else "supported",
                             "evidence_refs": item["evidence_refs"], "rationale": "人工填写工程记录，仅用于验证来源核查门槛与流程，不是语义能力证据。"}], "unresolved": []}
        workflow.submit(run, task["id"], review, usage(task))
    task = workflow.prepare(run, "decision", phase="review")
    workflow.submit(run, task["id"], decision(task, "review"), usage(task))
    return packaging.package(run, destination, "tidal-supply-demo", VERSION)


def protocol_for(base, candidate):
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    # Use similarly sized content solely to exercise mechanical comparison plumbing.
    # B2 is deliberately labelled an emulated material, never an actual upstream run.
    text = "工程测试材料；不是实际摘要或上游生成结果。\n" * 400
    (base / "summary.txt").write_text(text, encoding="utf-8")
    (base / "upstream-placeholder.txt").write_text(text, encoding="utf-8")
    cases = []
    inputs = ["把补给站换成文稿审核队列，哪些条件需先确认？", "渡轮集中到达时，能把短期改善归因于调步骤吗？", "只知道队伍变长，下一步需要哪些事实？", "同窗口试探后完成量未变，怎么修订原解释？"]
    for i, family in enumerate(("surface_shift", "condition_reversal", "missing_information", "new_evidence")):
        cases.append({"id": f"case-{i}", "split": "heldout", "family": family, "input": inputs[i],
                      "expected_behaviors": ["说明决定性前提、信息缺口或修订条件；工程样例预期，不代表正式评分协议"],
                      "evidence_refs": ["synthetic-book.md chapters 1–5"], "cross_chapter": True, "distance": "synthetic-probe"})
    return {"schema_version": VERSION, "purpose": "工程评估流程演示，不能得出语义能力结论", "mode": "exploratory",
            "model": "scripted-fixture-no-model", "host": "python-engineering-demo", "tools": [], "prompt_version": "fixture-1",
            "repetitions": 1, "material_char_budget": 100000, "min_improvement": .5, "max_boundary_errors": 0,
            "max_calls": 40, "max_cost_usd": None, "review_policy": "Scripted engineering scores are not human or model capability evidence.",
            "cases": cases, "conditions": [
                {"id": "B0", "material_path": "", "provenance": "engineering empty input"},
                {"id": "B1", "material_path": str(base / "summary.txt"), "provenance": "scripted placeholder, not an actual summary"},
                {"id": "B2", "material_path": str(base / "upstream-placeholder.txt"), "provenance": "emulated fixture; no upstream model run"},
                {"id": "B3", "material_path": str(candidate), "provenance": "authored synthetic candidate"}]}


def run_demo(destination):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    run, candidate = destination / "run", destination / "candidate"
    build_candidate(run, candidate)
    ev = destination / "evaluation-private"
    evaluation.freeze(ev, protocol_for(destination / "materials", candidate))
    # Frozen evaluator protocol and packets can be exercised without manufacturing model answers.
    first = evaluation.issue(ev)
    write_json(destination / "first-executor-request.json", first)
    report = evaluation.report(ev)
    write_json(destination / "report.json", {"demo_type": "scripted-engineering-only", "workflow": workflow.status(run), "evaluation": report})
    return {"candidate": str(candidate), "report": str(destination / "report.json"),
            "semantic_validation": "not performed", "evaluation": "protocol frozen; first job emitted; no real model outputs submitted"}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("destination", type=Path)
    print(json.dumps(run_demo(p.parse_args().destination), ensure_ascii=False, indent=2))
