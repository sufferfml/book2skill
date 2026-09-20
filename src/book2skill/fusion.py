"""Independent book extraction followed by explicit, reviewable framework integration."""

import copy
from itertools import combinations
from pathlib import Path
import uuid

from . import __version__, workflow
from .contracts import VERSION, validate
from .source import passages, verify_sources
from .storage import commit, digest, load, lock, now, require, write_json, atomic_text

GUIDANCE = {
    'fusion-plan': 'Compare independently extracted frameworks against the target purpose. Read every input framework with fusion-context. Account for each framework, including exclusions. Compare premises, units, objectives and boundaries, not word similarity. Record equivalence, refinement, complementarity, conditional alternatives, contradictions or unrelatedness. Preserve disagreement and explicit routing conditions. keep_separate and insufficient_evidence are valid results; do not force integration.',
    'fusion-model': 'Construct a task-oriented model from the reviewed book inputs and integration plan. Reread cited evidence and input records via fusion-context/context during this task. Preserve original constraints. Every output object needs lineage. Unchanged author claims may retain attribution only when copied faithfully. Cross-book conclusions are cross_book_synthesis, never a single author statement. Novel advice is model_extension. Follow routing/keep-separate decisions rather than concatenating chapters.',
    'fusion-review': 'Use a fresh context distinct from all builder contexts. Check source support, concept alignment, dispositions, routing conditions, unresolved conflicts, and every output claim, relationship and framework. Review the integration itself, not only the books separately. supported means a justified attribution/derivation, not empirical effectiveness. Hypotheses remain hypotheses. Explicitly record missing support and unresolved issues. Do not accept a model to satisfy a validator.',
}


def qualified(book_id, original):
    value = f'{book_id}--{original}'
    return value if len(value) <= 63 else f'{book_id}--{digest(original)[:24]}'


def parent_ready(s):
    require(s.get('kind') != 'fusion', 'supply separate single-book runs, not nested fused outputs')
    require(not s['pending'] and s['model'] and s['review'], 'each book needs a completed independent extraction and source review; drafts cannot be imported')
    require(s['outcome'] == 'candidate' and s['decisions'].get('review', {}).get('decision') in ('whole', 'partial'), 'each book needs a passing final suitability review')
    require(all(c['status'] != 'unread' for c in s['coverage'].values()), 'input book has unread material')
    verify_sources(s)
    validate('model', s['model'])
    workflow.validate_model(s, s['model'])
    validate('review', s['review'])
    require(s['review']['model_hash'] == digest(s['model']) and not s['review']['unresolved'], 'input review does not certify this model version')
    items = {x['id']: x for x in s['model']['claims'] + s['model']['relations']}
    reviews = {x['target_id']: x for x in s['review']['items']}
    require(len(reviews) == len(s['review']['items']) and reviews.keys() == items.keys(), 'input review must cover every claim and relationship exactly once')
    for ident, item in items.items():
        r = reviews[ident]
        expected = 'hypothesis' if item['epistemic_origin'] == 'model_extension' else 'supported'
        require(r['verdict'] == expected and set(r['evidence_refs']) == set(item['evidence_refs']), 'input book has unsupported or unreviewed evidence')


def initialize(root, inputs, config):
    validate('fusion-input', inputs)
    validate('fusion-config', config)
    require(config['context_reserve'] < config['context_capacity'], 'context reserve consumes entire capacity')
    aliases = [b['id'] for b in inputs['books']]
    require(len(aliases) == len(set(aliases)), 'duplicate book IDs')
    books, sources, segments, coverage, registry, fingerprints = [], [], [], {}, {}, set()
    for spec in inputs['books']:
        path = Path(spec['run_path']).resolve()
        s = load(path)
        parent_ready(s)
        fingerprint = digest(sorted(x['text_sha256'] for x in s['sources']))
        require(fingerprint not in fingerprints, 'duplicate source book; distinct aliases are not independent books')
        fingerprints.add(fingerprint)
        bid = spec['id']
        originals = [x['id'] for x in s['sources'] + s['segments'] + s['model']['claims'] + s['model']['relations'] + s['model']['frameworks']]
        require(len(originals) == len(set(originals)), 'ambiguous input object IDs')
        mapping = {ident: qualified(bid, ident) for ident in originals}
        require(len(set(mapping.values())) == len(mapping), 'namespaced ID collision')
        for kind in ('sources', 'segments'):
            for item in s[kind]:
                x = copy.deepcopy(item)
                x.update(id=mapping[item['id']], book_id=bid, original_id=item['id'])
                if kind == 'segments':
                    x['source_id'] = mapping[x['source_id']]
                    coverage[x['id']] = {**s['coverage'][item['id']], 'reading_id': None}
                    segments.append(x)
                else:
                    sources.append(x)
        model = copy.deepcopy(s['model'])
        for kind in ('claims', 'relations', 'frameworks'):
            for x in model[kind]:
                original = x['id']
                x['id'] = mapping[original]
                for key in ('evidence_refs', 'claim_ids', 'relation_ids', 'dependency_ids'):
                    if key in x:
                        x[key] = [mapping[i] for i in x[key]]
                for key in ('from_id', 'to_id'):
                    if key in x:
                        x[key] = mapping[x[key]]
                registry[x['id']] = {'book_id': bid, 'kind': kind, 'original_id': original, 'record': x}
        review = copy.deepcopy(s['review'])
        for x in review['items']:
            x['target_id'] = mapping[x['target_id']]
            x['evidence_refs'] = [mapping[i] for i in x['evidence_refs']]
        books.append({'id': bid, 'run_path': str(path), 'run_id': s['run_id'], 'revision': s['revision'],
                      'basis_hash': workflow.basis(s), 'snapshot_hash': digest(s), 'model_hash': digest(s['model']),
                      'source_hash': fingerprint, 'config': s['config'], 'model': model,
                      'source_review': review, 'suitability': s['decisions']['review']})
    conf = {**config, 'book_version': '; '.join(f"{b['id']}: {b['config']['book_version']}" for b in books)}
    state = {'schema_version': VERSION, 'tool_version': __version__, 'kind': 'fusion',
             'run_id': 'fusion-' + uuid.uuid4().hex[:12], 'revision': 0, 'events': [], 'created_at': now(),
             'config': conf, 'books': books, 'input_records': registry, 'integration': None,
             'lineage': [], 'builder_contexts': [], 'sources': sources, 'segments': segments,
             'coverage': coverage, 'readings': {}, 'decisions': {}, 'model': None, 'review': None,
             'review_parts': [], 'stage': 'fusion_imported', 'status': 'waiting_input', 'outcome': 'candidate',
             'pending': None, 'attempts': [], 'packages': [], 'revisions': [], 'access_log': [],
             'quality_warnings': ['Input review declarations are preserved, not independently authenticated. Integration needs a separate review and transfer evaluation.']}
    verify_sources(state)
    with lock(root):
        require(not (Path(root) / 'HEAD.json').exists(), 'run exists; use a new directory for a changed book collection')
        commit(root, state, 'fusion-initialize')
    return status(root)


def require_fusion(s):
    require(s.get('kind') == 'fusion', 'this command requires a fusion run')


def integration_hash(s):
    return digest({'books': [(b['id'], b['basis_hash']) for b in s['books']],
                   'plan': s['integration'], 'model': s['model'], 'lineage': s['lineage']})


def status(root):
    s = load(root)
    require_fusion(s)
    verify_sources(s)
    next_step = ('submit or cancel pending task' if s['pending'] else
                 'revise plan/model to resolve review issues' if s['outcome'] == 'needs_revision' else
                 'reviewed decision: retain separate books or gather more evidence' if s['outcome'] in ('keep_separate', 'insufficient_evidence') else
                 'prepare fusion-plan' if s['integration'] is None else
                 'prepare fusion-model; resolve any unresolved bridges first' if s['integration']['outcome'] == 'integrate' and s['model'] is None else
                 'prepare fusion-review in a fresh context' if s['review'] is None else
                 'package a candidate and evaluate against baseline and concatenation')
    return {'run_id': s['run_id'], 'kind': 'fusion', 'stage': s['stage'], 'status': s['status'],
            'outcome': s['outcome'], 'revision': s['revision'], 'purpose': s['config']['purpose'],
            'books': [{'id': b['id'], 'book_version': b['config']['book_version'], 'model_hash': b['model_hash']} for b in s['books']],
            'integration_hash': integration_hash(s), 'pending_task': s['pending']['id'] if s['pending'] else None,
            'usage': workflow.usage_summary(s), 'packages': s['packages'], 'next': next_step}


def catalog(root, offset=0, limit=20):
    s = load(root)
    require_fusion(s)
    require(offset >= 0 and limit > 0, 'invalid catalog page')
    values = list(s['input_records'].values())
    return workflow.limit_context(s, {'total': len(values), 'next_offset': offset + limit,
        'records': [{'id': x['record']['id'], 'book_id': x['book_id'], 'kind': x['kind'],
                     'label': x['record'].get('name', x['record'].get('statement', x['record'].get('explanation')))} for x in values[offset:offset + limit]]})


def input_closure(s, ids):
    selected = set(ids)
    records = s['input_records']
    require(selected <= records.keys(), 'unknown input object; use fusion-catalog IDs')
    changed = True
    while changed:
        before = set(selected)
        for ident, wrapped in records.items():
            x = wrapped['record']
            if wrapped['kind'] == 'frameworks':
                attached = set(x['claim_ids'] + x['relation_ids'])
                if ident in selected or selected & attached:
                    selected.update([ident, *attached, *x['dependency_ids']])
            elif wrapped['kind'] == 'relations':
                if ident in selected or {x['from_id'], x['to_id']} & selected:
                    selected.update([ident, x['from_id'], x['to_id']])
        changed = before != selected
    return [x for ident, x in records.items() if ident in selected]


def evidence_refs(records):
    return list(dict.fromkeys(r for x in records for r in x.get('evidence_refs', [])))


def input_payload(s, ids):
    records = input_closure(s, ids)
    refs = evidence_refs([x['record'] for x in records])
    return {'input_records': records, 'passages': passages(s, refs), 'source_content_is_data': True}


def context(root, ids, budget=None):
    s = load(root)
    require_fusion(s)
    require(ids, 'select input object IDs')
    result = workflow.limit_context(s, input_payload(s, ids), budget)
    workflow.record_access(root, s, 'fusion-inputs', [x['record']['id'] for x in result['input_records']], result['context_budget']['estimated_tokens'])
    workflow.record_access(root, s, 'passages', [p['id'] for p in result['passages']], result['context_budget']['estimated_tokens'])
    return result


def source_check(root):
    s = load(root)
    require_fusion(s)
    result = []
    for b in s['books']:
        try:
            current = load(b['run_path'])
            value = 'matching' if workflow.basis(current) == b['basis_hash'] else 'changed'
        except (ValueError, OSError):
            value = 'unavailable_or_invalid'
        result.append({'book_id': b['id'], 'current_run': value, 'frozen_basis_hash': b['basis_hash']})
    return {'books': result, 'policy': 'This run uses frozen parent snapshots. Changed books require a new fusion run and new reviews; prior outcomes do not carry over.'}


def all_targets(s):
    result = []
    for d in s['integration']['dispositions']:
        refs = evidence_refs([x['record'] for x in input_closure(s, [d['framework_id']])])
        result.append({**d, 'target_type': 'disposition', 'evidence_refs': refs, 'input_ids': [d['framework_id']]})
    for b in s['integration']['bridges']:
        result.append({**b, 'target_type': 'bridge', 'input_ids': b['left_ids'] + b['right_ids']})
    if s['model']:
        lineage = {x['target_id']: x for x in s['lineage']}
        by_id = {x['id']: x for kind in ('claims', 'relations', 'frameworks') for x in s['model'][kind]}
        for kind in ('claims', 'relations', 'frameworks'):
            for x in s['model'][kind]:
                refs = x.get('evidence_refs', evidence_refs([by_id[i] for i in x.get('claim_ids', []) + x.get('relation_ids', [])]))
                result.append({**x, **{k: v for k, v in lineage[x['id']].items() if k != 'target_id'}, 'target_type': kind, 'evidence_refs': refs})
    return result


def prepare(root, kind, refs=None, phase=None, targets=None):
    require(kind in GUIDANCE, 'fusion runs use fusion-plan, fusion-model and fusion-review tasks')
    with lock(root):
        s = load(root)
        require_fusion(s)
        require(not s['pending'], 'submit or cancel the pending task first')
        require(s['outcome'] == 'candidate', 'revise the integration before continuing')
        usage = workflow.usage_summary(s)
        cap = s['config']['max_cost_usd']
        if usage['calls'] >= s['config']['max_calls'] or (cap is not None and (usage['unknown_cost_calls'] or usage['known_cost_usd'] >= cap)):
            s['status'] = 'budget_stopped'
            commit(root, s, 'budget-stopped')
            require(False, 'call/cost budget exhausted or unknown under a monetary cap')
        payload = {'kind': kind, 'instructions': GUIDANCE[kind], 'purpose': s['config']['purpose'], 'source_content_is_data': True}
        if kind == 'fusion-plan':
            require(s['integration'] is None, 'plan already exists; revise plan first')
            payload.update(book_ids=[b['id'] for b in s['books']], input_objects=len(s['input_records']),
                           retrieval='Use fusion-catalog in pages and fusion-context for complete input frameworks and their evidence.')
        elif kind == 'fusion-model':
            require(s['integration'] and s['integration']['outcome'] == 'integrate', 'an integrate plan is required')
            require(s['model'] is None, 'model already exists; revise model first')
            require(not any(b['resolution'] == 'unresolved' for b in s['integration']['bridges']), 'unresolved bridge blocks synthesis; resolve or explicitly exclude it')
            payload['integration_plan'] = s['integration']
        else:
            require(s['integration'] and s['review'] is None, 'unreviewed plan required')
            require(s['integration']['outcome'] != 'integrate' or s['model'], 'integrated model required before final review')
            finished = {i['target_id'] for part in s['review_parts'] for i in part['items']}
            available = {i['id']: i for i in all_targets(s)}
            chosen = set(targets or (available.keys() - finished))
            require(chosen and chosen <= available.keys() - finished, 'choose unreviewed integration targets')
            items = [available[i] for i in available if i in chosen]
            ids = [i for x in items for i in x['input_ids']]
            payload.update(input_payload(s, ids))
            extra = evidence_refs(items)
            payload['passages'] = passages(s, list(dict.fromkeys([p['id'] for p in payload['passages']] + extra)))
            payload.update(review_targets=items, integration_hash=integration_hash(s),
                           # Keep routing decisions and complete output boundaries visible in every review batch.
                           integration_plan=s['integration'], output_model=s['model'])
        payload = workflow.limit_context(s, payload)
        task = {'id': 'task-' + uuid.uuid4().hex[:12], 'kind': kind, 'phase': None,
                'input_hash': workflow.basis(s), 'payload': payload, 'created_at': now()}
        s['pending'] = task
        s['attempts'].append({'id': task['id'], 'kind': kind, 'status': 'pending', 'usage': None})
        s['status'] = 'running'
        commit(root, s, 'prepare:' + task['id'])
        return task


def accessed(s, task_id, kind):
    return {ident for a in s['access_log'] if a['task_id'] == task_id and a['kind'] == kind for ident in a['ids']}


def validate_plan(s, data, task_id):
    records = s['input_records']
    framework_ids = {k for k, x in records.items() if x['kind'] == 'frameworks'}
    dispositions = data['dispositions']
    workflow.unique_records(dispositions + data['bridges'])
    require(not ({x['id'] for x in dispositions + data['bridges']} & records.keys()), 'integration object IDs must not shadow input IDs')
    require(len(dispositions) == len(framework_ids) and {d['framework_id'] for d in dispositions} == framework_ids, 'account for every input framework exactly once')
    require(framework_ids <= accessed(s, task_id, 'fusion-inputs'), 'read all input frameworks with fusion-context during planning')
    used_books = {records[d['framework_id']]['book_id'] for d in dispositions if d['action'] == 'use'}
    actions = {d['framework_id']: d['action'] for d in dispositions}
    for fid, action in actions.items():
        if action == 'use':
            require(all(actions[dep] == 'use' for dep in records[fid]['record']['dependency_ids']), 'a used framework cannot silently drop its dependencies')
    pairs = set()
    for b in data['bridges']:
        left, right = set(b['left_ids']), set(b['right_ids'])
        require(left | right <= records.keys(), 'unknown bridge input')
        lbs, rbs = {records[i]['book_id'] for i in left}, {records[i]['book_id'] for i in right}
        require(len(lbs) == len(rbs) == 1 and lbs != rbs, 'bridge must compare two distinct books')
        pairs.add(frozenset(lbs | rbs))
        require(left | right <= accessed(s, task_id, 'fusion-inputs'), 'reread bridge inputs with fusion-context')
        allowed = set(evidence_refs([x['record'] for x in input_closure(s, left | right)]))
        require(set(b['evidence_refs']) <= allowed, 'bridge evidence is not linked to its input records')
        ps = passages(s, b['evidence_refs'])
        require({p['book_id'] for p in ps} == lbs | rbs, 'bridge evidence must include both books')
        require(all(s['coverage'][p['id']]['status'] == 'read' for p in ps), 'bridge cites excluded material')
        require(b['relationship'] not in ('contradicts', 'unrelated') or b['resolution'] != 'combine', 'contradictory/unrelated frameworks cannot be forcibly combined')
        if b['resolution'] == 'conditional':
            require(b['conditions'] and b['differences'], 'conditional routing needs explicit conditions and differences')
    if data['outcome'] == 'integrate':
        require(len(used_books) >= 2, 'integration needs useful contributions from at least two books; choose keep_separate otherwise')
        require({frozenset(p) for p in combinations(used_books, 2)} <= pairs, 'compare each pair of contributing books explicitly')
    else:
        require(not used_books, 'non-integration outcomes must retain inputs as reference_only or exclude')


def validate_model(s, data, task_id):
    model, lineage = data['model'], data['lineage']
    workflow.validate_model(s, model)
    outputs = {x['id']: x for kind in ('claims', 'relations', 'frameworks') for x in model[kind]}
    require(not (outputs.keys() & (s['input_records'].keys() | {x['id'] for x in s['integration']['dispositions'] + s['integration']['bridges']})), 'output IDs must be distinct from input and plan IDs')
    require(len(lineage) == len(outputs) and {x['target_id'] for x in lineage} == outputs.keys(), 'every output claim, relationship and framework needs unique lineage')
    lm = {x['target_id']: x for x in lineage}
    records = s['input_records']
    bridges = {b['id']: b for b in s['integration']['bridges']}
    usable = set()
    for d in s['integration']['dispositions']:
        if d['action'] == 'use':
            f = records[d['framework_id']]['record']
            usable.update([f['id'], *f['claim_ids'], *f['relation_ids']])
    contributing = set()
    for ident, item in outputs.items():
        l = lm[ident]
        require(set(l['input_ids']) <= usable, 'lineage uses an excluded/reference-only or unknown input')
        require(set(l['input_ids']) <= accessed(s, task_id, 'fusion-inputs'), 'reread lineage inputs during synthesis')
        require(set(l['bridge_ids']) <= bridges.keys(), 'unknown lineage bridge')
        bids = {records[i]['book_id'] for i in l['input_ids']}
        if 'epistemic_origin' in item:
            contributing.update(bids)
        if len(bids) > 1:
            require(l['bridge_ids'], 'cross-book output needs a justified bridge')
            linked_pairs = []
            for bridge_id in l['bridge_ids']:
                b = bridges[bridge_id]
                require(b['resolution'] in ('combine', 'conditional'), 'keep-separate/excluded/unresolved bridge cannot support a combined output')
                participants = set(b['left_ids'] + b['right_ids'])
                linked_pairs.append({records[i]['book_id'] for i in participants})
                require(bids & linked_pairs[-1] == linked_pairs[-1], 'lineage bridge refers to unrelated books')
            require(set().union(*linked_pairs) == bids, 'bridges must cover all contributing books')
        origin = item.get('epistemic_origin')
        if origin in ('author_explicit', 'author_reconstructed'):
            require(len(l['input_ids']) == 1 and not l['bridge_ids'], 'author attribution cannot conceal synthesis')
            original = records[l['input_ids'][0]]['record']
            expected_keys = set(item) - {'id', 'from_id', 'to_id'}
            require(expected_keys <= original.keys() and all(item[k] == original[k] for k in expected_keys), 'author records must be preserved verbatim; classify revisions as synthesis or model_extension')
            if 'from_id' in item:
                for key in ('from_id', 'to_id'):
                    require(lm[item[key]]['input_ids'] == [original[key]], 'inherited relation endpoint attribution changed')
        if origin == 'cross_book_synthesis':
            require(len(bids) > 1, 'cross_book_synthesis requires multiple books')
        if 'evidence_refs' in item:
            allowed = set(evidence_refs([x['record'] for x in input_closure(s, l['input_ids'])]))
            require(set(item['evidence_refs']) <= allowed, 'output evidence is not supported by declared lineage')
            if origin == 'cross_book_synthesis':
                require({p['book_id'] for p in passages(s, item['evidence_refs'])} == bids, 'cross-book synthesis needs source evidence from each contributing book')
    require(len(contributing) >= 2, 'output does not actually use multiple books')
    refs = set(evidence_refs(model['claims'] + model['relations']))
    require(refs <= accessed(s, task_id, 'passages'), 'reread all output evidence during synthesis')
    # No orphan outputs can be used to make the book count appear larger.
    require({i for f in model['frameworks'] for i in f['claim_ids']} == {c['id'] for c in model['claims']}, 'all claims must participate in output frameworks')
    require({i for f in model['frameworks'] for i in f['relation_ids']} == {r['id'] for r in model['relations']}, 'all relations must participate in output frameworks')


def submit(root, task_id, data, usage):
    validate('usage', usage)
    with lock(root):
        s = load(root)
        require_fusion(s)
        prior = next((a for a in s['attempts'] if a['id'] == task_id and a['status'] == 'succeeded'), None)
        if prior:
            require(prior['result_hash'] == digest(data) and prior['usage'] == usage, 'task already accepted with another result')
            return status(root)
        t = s['pending']
        require(t and t['id'] == task_id and t['input_hash'] == workflow.basis(s), 'pending task or dependencies do not match')
        require(usage['id'] == task_id and usage['task'] == t['kind'] and usage['status'] == 'succeeded', 'usage must identify the succeeded task')
        validate(t['kind'], data)
        if t['kind'] == 'fusion-plan':
            validate_plan(s, data, task_id)
            s['integration'] = data
            s['builder_contexts'].append(data['builder_context'])
            s['stage'] = 'fusion_planned'
        elif t['kind'] == 'fusion-model':
            validate_model(s, data, task_id)
            s['model'], s['lineage'] = data['model'], data['lineage']
            s['builder_contexts'].append(data['builder_context'])
            s['stage'] = 'fusion_modeled'
        else:
            require(data['integration_hash'] == integration_hash(s), 'review targets a stale integration')
            require(data['fresh_context'] and data['context_id'] not in s['builder_contexts'], 'integration review must declare a fresh, non-builder context')
            targets = {x['id']: x for x in t['payload']['review_targets']}
            reviewed = {x['target_id']: x for x in data['items']}
            require(len(reviewed) == len(data['items']) and reviewed.keys() == targets.keys(), 'review all and only prepared targets')
            for ident, item in targets.items():
                r = reviewed[ident]
                require(set(r['evidence_refs']) == set(item['evidence_refs']), 'review must account for all target evidence')
                if item.get('epistemic_origin') == 'model_extension':
                    require(r['verdict'] != 'supported', 'model extensions remain hypotheses')
                else:
                    require(r['verdict'] != 'hypothesis', 'revise provenance before downgrading this target')
            s['review_parts'].append(data)
            merged = [x for part in s['review_parts'] for x in part['items']]
            if len(merged) == len(all_targets(s)):
                s['review'] = {'schema_version': VERSION, 'integration_hash': integration_hash(s),
                    'model_hash': digest(s['model']), 'reviewer': '; '.join(dict.fromkeys(p['reviewer'] for p in s['review_parts'])),
                    'items': merged, 'unresolved': [u for p in s['review_parts'] for u in p['unresolved']]}
                bad = s['review']['unresolved'] or any(x['verdict'] in ('unsupported', 'uncertain') for x in merged)
                s['outcome'] = 'needs_revision' if bad else ('candidate' if s['integration']['outcome'] == 'integrate' else s['integration']['outcome'])
                s['stage'] = 'fusion_reviewed'
                if not bad and s['model']:
                    s['decisions']['review'] = {'decision': 'partial', 'candidate_scope': [f['question'] for f in s['model']['frameworks']], 'missing_information': [u for f in s['model']['frameworks'] for u in f['unknowns']]}
        attempt = next(a for a in s['attempts'] if a['id'] == task_id)
        attempt.update(status='succeeded', usage=usage, result_hash=digest(data))
        s['pending'] = None
        s['status'] = 'completed' if s['outcome'] in ('keep_separate', 'insufficient_evidence') else 'waiting_input'
        commit(root, s, 'submit:' + task_id)
    return status(root)


def revise(root, target, reason, config=None):
    require(reason.strip(), 'revision reason required')
    require(target in ('plan', 'model', 'config', 'budget'), 'fusion revision target must be plan/model/config/budget')
    with lock(root):
        s = load(root)
        require_fusion(s)
        require(not s['pending'], 'cancel pending task before revising')
        previous = workflow.basis(s)
        if target in ('config', 'budget'):
            validate('fusion-config', config)
            require(config['context_reserve'] < config['context_capacity'], 'invalid context allowance')
            if target == 'budget':
                require(all(config[k] == s['config'][k] for k in config if k not in ('context_capacity', 'context_reserve', 'max_calls', 'max_cost_usd')), 'budget revision cannot change semantic configuration')
            s['config'] = {**config, 'book_version': s['config']['book_version']}
        if target != 'budget':
            if target in ('plan', 'config'):
                s['integration'] = None
            s.update(model=None, lineage=[], review=None, review_parts=[], decisions={}, outcome='candidate')
            for package in s['packages']:
                package['stale'] = True
            s['stage'] = 'fusion_planned' if s['integration'] else 'fusion_imported'
        s['revisions'].append({'target': target, 'reason': reason, 'previous_basis': previous, 'at': now()})
        s['status'] = 'waiting_input'
        commit(root, s, 'revise:' + target)
    return status(root)


def require_ready(s):
    require(s['integration'] and s['integration']['outcome'] == 'integrate', 'only a reviewed integration can produce a fused package')
    require(s['review'] and s['review']['integration_hash'] == integration_hash(s) and not s['review']['unresolved'], 'complete current integration review required')
    require(s['outcome'] == 'candidate', 'resolve integration review failures before packaging')


def package_refs(s):
    refs = evidence_refs(s['model']['claims'] + s['model']['relations'] + s['integration']['bridges'])
    refs += evidence_refs([x['record'] for x in s['input_records'].values()])
    return list(dict.fromkeys(refs))


def package_extras(s, stage):
    books = [{k: v for k, v in b.items() if k != 'run_path'} for b in s['books']]
    write_json(stage / 'references/integration.json', {'schema_version': VERSION, 'books': books,
        'input_records': s['input_records'], 'plan': s['integration'], 'lineage': s['lineage'], 'review': s['review']})
    lines = ['# Framework selection and integration boundaries', '',
             'Read this routing policy before applying the fused skill. Source agreement is not proof of real-world effectiveness.', '']
    for b in s['integration']['bridges']:
        lines += [f"## {b['id']}: {b['relationship']} / {b['resolution']}", '', b['rationale'], '',
                  'Selection: ' + b['selection_rule'], '', *['- Condition: ' + c for c in b['conditions']],
                  *['- Difference: ' + d for d in b['differences']], '']
    lines += ['See [integration provenance](references/integration.json) for original perspectives, exclusions, and output lineage.',
              'Cross-book synthesis is an integration judgment, not a statement jointly authored by the source authors.']
    atomic_text(stage / 'routing.md', '\n'.join(lines) + '\n')
    return '\nBefore choosing a framework, read [routing and conflicts](routing.md). Preserve distinct alternatives and conditional decisions. The [integration provenance](references/integration.json) is an audit archive; consult selected records only for a specific provenance question, not by default.\n'
