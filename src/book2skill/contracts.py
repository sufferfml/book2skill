"""Small, strict JSON Schema subset. No provider or installation dependency.

Only the keywords used here are supported; unknown schema keywords are errors.
The exported schemas are also usable with a full Draft 2020-12 validator.
"""

import copy
import re

VERSION = "0.0.1"


class Invalid(ValueError):
    pass


def string(*, enum=None, empty=False):
    result = {"type": "string", "minLength": 0 if empty else 1}
    if enum:
        result["enum"] = enum
    return result


TEXT = string()
ID = {"type": "string", "pattern": r"^[a-z][a-z0-9-]{0,62}$"}
NUMBER = {"type": ["number", "null"], "minimum": 0}
INTEGER = {"type": "integer", "minimum": 0}
BOOL = {"type": "boolean"}


def array(items=TEXT, minimum=0, maximum=None):
    result = {"type": "array", "items": items, "minItems": minimum}
    if maximum is not None:
        result["maxItems"] = maximum
    return result


def obj(properties, optional=()):
    return {"type": "object", "properties": properties,
            "required": [k for k in properties if k not in optional],
            "additionalProperties": False}


def document(properties):
    return obj({"schema_version": {"const": VERSION}, **properties})


ORIGIN = string(enum=["author_explicit", "author_reconstructed", "model_extension"])
REFS = array(ID)
USAGE_FIELDS = {"input_tokens": NUMBER, "output_tokens": NUMBER,
                "cost_usd": NUMBER, "duration_seconds": NUMBER,
                "uncertain": BOOL}
DIMENSIONS = ["mapping", "boundaries", "fidelity", "action", "revision"]
FAMILIES = ["surface_shift", "condition_reversal", "missing_information", "new_evidence"]
FAILURES = ["extraction", "reconstruction", "boundary", "mapping", "execution", "case_defect"]

SCHEMAS = {
    "config": document({
        "purpose": TEXT, "book_version": TEXT, "language": TEXT,
        "model": TEXT, "host": TEXT, "prompt_version": TEXT,
        "context_capacity": {"type": "integer", "minimum": 1024},
        "context_reserve": INTEGER,
        "max_calls": {"type": "integer", "minimum": 1},
        "max_cost_usd": NUMBER,
    }),
    "decision": document({
        "phase": string(enum=["prescreen", "review"]),
        "decision": string(enum=["whole", "partial", "reference_only", "insufficient_evidence"]),
        "rationale": TEXT, "candidate_scope": array(TEXT),
        "sample_refs": array(ID, 1), "evidence_refs": array(ID, 1),
        "missing_information": array(TEXT), "quality_notes": array(TEXT, 1),
        "reviewer": TEXT, "second_review": string(empty=True),
    }),
    "reading": document({
        "id": ID, "segment_ids": array(ID, 1),
        "disposition": string(enum=["read", "excluded"]), "reason": TEXT,
        "discoveries": array(TEXT), "conditions": array(TEXT),
        "counterexamples": array(TEXT), "connections": array(TEXT),
        "questions": array(TEXT),
    }),
    "model": document({
        "claims": array(obj({
            "id": ID, "statement": TEXT, "epistemic_origin": ORIGIN,
            "evidence_refs": REFS, "conditions": array(TEXT), "unknowns": array(TEXT),
        }), 1),
        "relations": array(obj({
            "id": ID, "from_id": ID, "to_id": ID,
            "kind": string(enum=["supports", "depends_on", "limits", "contradicts", "illustrates"]),
            "explanation": TEXT, "epistemic_origin": ORIGIN, "evidence_refs": REFS,
        }), 1),
        "frameworks": array(obj({
            "id": ID, "name": TEXT, "kind": string(enum=["procedure", "causal", "argument", "diagnostic", "normative", "mixed"]),
            "question": TEXT, "mechanism": TEXT, "claim_ids": array(ID, 1),
            "relation_ids": array(ID, 1), "dependency_ids": REFS,
            "applicability": array(TEXT, 1), "boundaries": array(TEXT, 1),
            "observations": array(TEXT, 1), "mapping": array(TEXT, 1),
            "alternatives": array(TEXT, 1), "checks": array(TEXT, 1),
            "revision": array(TEXT, 1), "unknowns": array(TEXT),
        }), 1, 3),
    }),
    "review": document({
        "model_hash": TEXT, "reviewer": TEXT,
        "items": array(obj({
            "target_id": ID,
            "verdict": string(enum=["supported", "unsupported", "uncertain", "hypothesis"]),
            "evidence_refs": REFS, "rationale": TEXT,
        }), 1), "unresolved": array(TEXT),
    }),
    "usage": document({"id": ID, "task": TEXT, "status": string(enum=["succeeded", "failed", "unknown"]),
                        **USAGE_FIELDS}),
    "protocol": document({
        "purpose": TEXT, "mode": string(enum=["exploratory", "formal"]),
        "model": TEXT, "host": TEXT, "tools": array(TEXT), "prompt_version": TEXT,
        "repetitions": {"type": "integer", "minimum": 1},
        "material_char_budget": {"type": "integer", "minimum": 1},
        "min_improvement": {"type": "number", "exclusiveMinimum": 0},
        "max_boundary_errors": INTEGER, "max_calls": {"type": "integer", "minimum": 1},
        "max_cost_usd": NUMBER, "review_policy": TEXT,
        "cases": array(obj({
            "id": ID, "split": string(enum=["dev", "heldout"]),
            "family": string(enum=FAMILIES), "input": TEXT,
            "expected_behaviors": array(TEXT, 1), "evidence_refs": array(TEXT, 1),
            "cross_chapter": BOOL, "distance": TEXT,
        }), 1),
        "conditions": array(obj({
            "id": string(enum=["B0", "B1", "B2", "B3", "B4"]),
            "material_path": string(empty=True), "provenance": TEXT,
        }), 4, 5),
    }),
    "answer": document({
        "job_id": ID, "status": string(enum=["succeeded", "failed"]),
        "answer": string(empty=True), "error": string(empty=True),
        "model": TEXT, "host": TEXT, "context_id": TEXT,
        "fresh_context": BOOL, "actual_material_chars": INTEGER,
        **USAGE_FIELDS,
    }),
    "score": document({
        "review_id": ID, "reviewer": TEXT,
        "reviewer_type": string(enum=["human", "model"]),
        "scores": obj({k: {"type": "integer", "minimum": 0, "maximum": 2} for k in DIMENSIONS}),
        "boundary_error": BOOL, "fabricated_attribution": BOOL,
        "concealed_gap": BOOL, "failure_types": array(string(enum=FAILURES)),
        "rationale": TEXT, "human_checked": BOOL,
    }),
}


# Fusion is a separate run type; single-book contracts remain backward compatible.
_fusion_config = copy.deepcopy(SCHEMAS["config"])
del _fusion_config["properties"]["book_version"]
_fusion_config["required"].remove("book_version")
_fusion_model = copy.deepcopy(SCHEMAS["model"])
for _kind in ("claims", "relations"):
    _fusion_model["properties"][_kind]["items"]["properties"]["epistemic_origin"]["enum"].append("cross_book_synthesis")
SCHEMAS.update({
    "fusion-config": _fusion_config,
    "fusion-input": document({"books": array(obj({
        "id": {"type": "string", "pattern": r"^[a-z][a-z0-9-]{0,23}$"}, "run_path": TEXT,
    }), 2)}),
    "fusion-plan": document({
        "builder_context": TEXT,
        "outcome": string(enum=["integrate", "keep_separate", "insufficient_evidence"]),
        "rationale": TEXT,
        "dispositions": array(obj({"id": ID, "framework_id": ID,
            "action": string(enum=["use", "reference_only", "exclude"]), "rationale": TEXT}), 1),
        "bridges": array(obj({"id": ID, "left_ids": array(ID, 1), "right_ids": array(ID, 1),
            "relationship": string(enum=["equivalent", "refines", "complements", "conditional_alternative", "contradicts", "unrelated"]),
            "resolution": string(enum=["combine", "conditional", "keep_separate", "exclude", "unresolved"]),
            "rationale": TEXT, "conditions": array(TEXT), "differences": array(TEXT),
            "selection_rule": TEXT, "evidence_refs": array(ID, 2)})),
    }),
    "fusion-model": document({"builder_context": TEXT, "model": _fusion_model,
        "lineage": array(obj({"target_id": ID, "input_ids": array(ID, 1), "bridge_ids": REFS}), 1)}),
    "fusion-review": document({"integration_hash": TEXT, "reviewer": TEXT,
        "context_id": TEXT, "fresh_context": BOOL,
        "items": copy.deepcopy(SCHEMAS["review"]["properties"]["items"]), "unresolved": array(TEXT)}),
})
# Optional fields preserve existing evaluation protocols.
SCHEMAS["protocol"]["properties"]["comparison_kind"] = string(enum=["book", "fusion", "optimization"])
SCHEMAS['protocol']['properties']['conditions']['minItems'] = 2
SCHEMAS['protocol']['properties']['max_quality_drop'] = {'type': 'number', 'minimum': 0}
SCHEMAS['protocol']['properties']['min_read_reduction'] = {'type': 'number', 'minimum': 0, 'maximum': 1}
_case = SCHEMAS["protocol"]["properties"]["cases"]["items"]["properties"]
_case["cross_book"] = BOOL
_case["baseline_regression"] = BOOL

# Application compilation is separately versioned; old research runs stay valid.
SCHEMAS['runtime-plan'] = document({
    'source_manifest_hash': TEXT, 'builder_context': TEXT, 'description': TEXT,
    'core': obj({'text': TEXT, 'source_ids': array(ID, 1)}),
    'modules': array(obj({'id': ID, 'title': TEXT, 'when': TEXT, 'text': TEXT,
        'source_ids': array(ID, 1), 'requires': array(ID),
        'conditional': array(obj({'module_id': ID, 'condition': TEXT}))}), 1),
    'archive_only': array(obj({'source_id': ID, 'reason': TEXT})),
    'spans': array(obj({'passage_id': ID, 'source_sha256': TEXT,
        'start': INTEGER, 'end': INTEGER, 'reason': TEXT})),
})
SCHEMAS['runtime-review'] = document({
    'source_manifest_hash': TEXT, 'plan_hash': TEXT, 'reviewer': TEXT,
    'context_id': TEXT, 'fresh_context': BOOL,
    'items': array(obj({'target_id': TEXT, 'verdict': string(enum=['preserved', 'revise']), 'rationale': TEXT}), 1),
    'unresolved': array(TEXT),
})
SCHEMAS['protocol']['properties']['delivery'] = string(enum=['inline', 'on_demand'])
SCHEMAS['runtime-plan']['properties']['catalog'] = array(obj({'id': ID, 'kind': TEXT}))
SCHEMAS['answer']['properties']['access_log'] = array(obj({
    'path': TEXT, 'returned_chars': INTEGER, 'sha256': TEXT,
}))


def check(schema, value, path="$"):
    known = {"$schema", "title", "type", "const", "enum", "properties", "required",
             "additionalProperties", "items", "minItems", "maxItems", "minLength",
             "pattern", "minimum", "maximum", "exclusiveMinimum"}
    if set(schema) - known:
        raise Invalid(f"unsupported schema keyword at {path}")
    types = schema.get("type", [])
    if isinstance(types, str):
        types = [types]
    matches = {"string": isinstance(value, str), "array": isinstance(value, list),
               "object": isinstance(value, dict), "boolean": type(value) is bool,
               "integer": type(value) is int, "number": type(value) in (int, float),
               "null": value is None}
    if types and not any(matches[t] for t in types):
        raise Invalid(f"{path}: expected {types}")
    if "const" in schema and value != schema["const"]:
        raise Invalid(f"{path}: expected constant {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise Invalid(f"{path}: expected one of {schema['enum']}")
    if isinstance(value, dict):
        missing = set(schema.get("required", [])) - value.keys()
        extra = value.keys() - schema.get("properties", {}).keys()
        if missing or (extra and schema.get("additionalProperties") is False):
            raise Invalid(f"{path}: missing={sorted(missing)}, unexpected={sorted(extra)}")
        for key, item in value.items():
            if key in schema.get("properties", {}):
                check(schema["properties"][key], item, f"{path}.{key}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", float("inf")):
            raise Invalid(f"{path}: invalid item count {len(value)}")
        for index, item in enumerate(value):
            check(schema["items"], item, f"{path}[{index}]")
    if isinstance(value, str):
        if len(value.strip()) < schema.get("minLength", 0):
            raise Invalid(f"{path}: empty text")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            raise Invalid(f"{path}: invalid identifier")
    if type(value) in (int, float):
        import math
        if not math.isfinite(value):
            raise Invalid(f"{path}: non-finite number")
        if value < schema.get("minimum", -float("inf")) or value > schema.get("maximum", float("inf")):
            raise Invalid(f"{path}: out of range")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise Invalid(f"{path}: must exceed {schema['exclusiveMinimum']}")


def validate(kind, value):
    if kind not in SCHEMAS:
        raise Invalid(f"unknown contract: {kind}")
    check(SCHEMAS[kind], value)
    return value


def schema(kind):
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": kind,
            **copy.deepcopy(SCHEMAS[kind])}


def template(kind):
    def make(s):
        if "const" in s:
            return s["const"]
        if "enum" in s:
            return s["enum"][0]
        t = s["type"]
        if isinstance(t, list):
            return None
        if t == "object":
            return {k: make(v) for k, v in s["properties"].items()}
        if t == "array":
            return [make(s["items"]) for _ in range(s.get("minItems", 0))]
        if t == "boolean":
            return False
        if t in ("integer", "number"):
            return s.get("minimum", s.get("exclusiveMinimum", 0) + 1)
        return ""
    return make(SCHEMAS[kind])
