"""Authored two-book engineering fixture, never evidence of LLM understanding."""
import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from book2skill import fusion, packaging, workflow
from book2skill.contracts import VERSION
from book2skill.storage import load, write_json
from run_demo import build_candidate, config, model_for, usage


def observation_model(state):
    m = model_for(state)
    statements = [
        '先记录相同时间窗口的到达量、完成量和等待时间。',
        '不允许改变现场步骤时，按工作负荷和资源配置分组观察窗口，提出待检验解释。',
        '工作负荷和人员不同会混淆比较，分组后相似也不能证明因果。',
        '非干预观察不能证明调整步骤必然改善结果，不可撤销改造还需要其他证据。',
        '新观察不支持解释时检查分组与前提，保留多个解释，不删除反证。',
    ]
    for c, statement in zip(m['claims'], statements):
        c['statement'] = statement
    for r in m['relations']:
        r['explanation'] = '观察方法需要同时遵守相应的观察前提、比较边界和修订条件。'
    f = m['frameworks'][0]
    f.update(name='不能干预时的条件性观察', question='不能干预现场时可以得出什么判断？',
             mechanism='在不可干预的现场按负荷和资源分组比较窗口，仅提出候选解释，依据新证据调整判断。',
             applicability=['不能主动改变现场步骤，但有窗口记录和负荷/资源信息'],
             boundaries=['观察与分组不构成因果证明'],
             alternatives=['保留多个解释，必要时补充更强证据'])
    return m


def make_inputs(base):
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    build_candidate(base/'book-a', base/'candidate-a')
    conf = config()
    conf['book_version'] = 'synthetic-observation-1'
    build_candidate(base/'book-b', base/'candidate-b', source=ROOT/'examples/synthetic-observation-book.md',
                    configuration=conf, model_builder=observation_model)
    cfg = config()
    del cfg['book_version']
    cfg.update(purpose='Choose reversible intervention or non-intervention observation under explicit constraints.', prompt_version='fusion-engineering-fixture-1', context_capacity=250000)
    inputs = {'schema_version': VERSION, 'books': [{'id': 'book-a', 'run_path': str((base/'book-a').resolve())},
                                                  {'id': 'book-b', 'run_path': str((base/'book-b').resolve())}]}
    return inputs, cfg


def find(s, book, original):
    return next(k for k, x in s['input_records'].items() if x['book_id'] == book and x['original_id'] == original)


def read_inputs(run):
    s = load(run)
    for ident, x in s['input_records'].items():
        if x['kind'] == 'frameworks':
            fusion.context(run, [ident])


def plan_for(s, outcome='integrate'):
    fs = [k for k, x in s['input_records'].items() if x['kind'] == 'frameworks']
    ca, cb = find(s, 'book-a', 'claim-probe'), find(s, 'book-b', 'claim-probe')
    refs = fusion.evidence_refs([s['input_records'][i]['record'] for i in (ca, cb)])
    return {'schema_version': VERSION, 'builder_context': 'authored-fixture-builder', 'outcome': outcome,
            'rationale': '工程样例：可干预试探与不可干预观察需要分开适用条件，不强行合并因果结论。',
            'dispositions': [{'id': f'disposition-{i}', 'framework_id': fid, 'action': 'use' if outcome == 'integrate' else 'reference_only', 'rationale': 'Retain original applicability and limitations.'} for i, fid in enumerate(fs)],
            'bridges': [{'id': 'bridge-methods', 'left_ids': [ca], 'right_ids': [cb],
                         'relationship': 'conditional_alternative', 'resolution': 'conditional' if outcome == 'integrate' else 'keep_separate',
                         'rationale': 'Intervention authority and reversibility determine the available evidence.',
                         'conditions': ['Intervene only when allowed and reversible; otherwise observe without causal claims.'],
                         'differences': ['An intervention and an observational comparison support different inferences.'],
                         'selection_rule': 'Choose A for an allowed reversible probe with comparable windows; choose B when intervention is unavailable.',
                         'evidence_refs': refs}]}


def model_for_fusion(s):
    ca, cb = [find(s, bid, 'claim-probe') for bid in ('book-a', 'book-b')]
    a, b = [copy.deepcopy(s['input_records'][i]['record']) for i in (ca, cb)]
    a['id'], b['id'] = 'claim-intervene', 'claim-observe'
    refs = list(dict.fromkeys(a['evidence_refs'] + b['evidence_refs']))
    joint = {'id': 'claim-select', 'statement': 'Select the method by intervention authority and reversibility; do not give observation the evidential strength of an intervention.',
             'epistemic_origin': 'cross_book_synthesis', 'evidence_refs': refs,
             'conditions': ['Check intervention authority and comparability first.'], 'unknowns': ['Real-world effectiveness untested.']}
    relation = {'id': 'relation-methods', 'from_id': a['id'], 'to_id': b['id'], 'kind': 'limits',
                'explanation': 'When intervention is unavailable, route to observation and retain its weaker attribution boundary.',
                'epistemic_origin': 'cross_book_synthesis', 'evidence_refs': refs}
    f = copy.deepcopy(s['books'][0]['model']['frameworks'][0])
    f.update(id='framework-method-selection', name='Select a method without overstating evidence',
             question='Which method is permitted and what can its evidence support?',
             mechanism=joint['statement'], claim_ids=[a['id'], b['id'], joint['id']], relation_ids=[relation['id']], dependency_ids=[],
             applicability=['A concrete question with known or explicitly missing intervention constraints'],
             boundaries=['Observational differences do not prove causation; unknown authority blocks recommending intervention'],
             mapping=['Map the situation to intervention authority, reversibility and window comparability'],
             alternatives=['Reversible probe, grouped observation, or gather missing information'])
    lineage = [{'target_id': a['id'], 'input_ids': [ca], 'bridge_ids': []},
               {'target_id': b['id'], 'input_ids': [cb], 'bridge_ids': []}]
    for ident in (joint['id'], relation['id'], f['id']):
        lineage.append({'target_id': ident, 'input_ids': [ca, cb], 'bridge_ids': ['bridge-methods']})
    return {'schema_version': VERSION, 'builder_context': 'authored-fixture-builder',
            'model': {'schema_version': VERSION, 'claims': [a, b, joint], 'relations': [relation], 'frameworks': [f]}, 'lineage': lineage}


def review_for(task, verdict=None):
    return {'schema_version': VERSION, 'integration_hash': task['payload']['integration_hash'],
            'reviewer': 'scripted-engineering-fixture-not-a-real-review', 'context_id': 'declared-review-context-fixture', 'fresh_context': True,
            'items': [{'target_id': x['id'], 'verdict': verdict or ('hypothesis' if x.get('epistemic_origin') == 'model_extension' else 'supported'),
                       'evidence_refs': x['evidence_refs'], 'rationale': 'Authored fixture to exercise validation only.'} for x in task['payload']['review_targets']], 'unresolved': []}


def construct(run):
    task = workflow.prepare(run, 'fusion-plan')
    read_inputs(run)
    workflow.submit(run, task['id'], plan_for(load(run)), usage(task))
    task = workflow.prepare(run, 'fusion-model')
    read_inputs(run)
    workflow.submit(run, task['id'], model_for_fusion(load(run)), usage(task))


def review(run):
    for item in fusion.all_targets(load(run)):
        task = workflow.prepare(run, 'fusion-review', targets=[item['id']])
        workflow.submit(run, task['id'], review_for(task), usage(task))


def run_demo(base):
    base = Path(base).resolve()
    inputs, cfg = make_inputs(base)
    write_json(base/'books.json', inputs)
    write_json(base/'fusion-config.json', cfg)
    run = base/'fusion'
    fusion.initialize(run, inputs, cfg)
    construct(run)
    review(run)
    result = packaging.package(run, base/'fused-candidate', 'method-selection-demo', '0.0.1')
    write_json(base/'report.json', {'engineering_fixture_only': True, 'semantic_validation': 'not performed',
                                  'source_check': fusion.source_check(run), 'status': workflow.status(run), 'package': result})
    return {'candidate': result['path'], 'report': str(base/'report.json'), 'semantic_validation': 'not performed'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    print(json.dumps(run_demo(parser.parse_args().destination), ensure_ascii=False, indent=2))
