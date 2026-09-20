"""Runtime compilation/transport invariants. Fixtures make no semantic claims."""
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
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'examples')]
from book2skill import compilation, evaluation, packaging, workflow
from book2skill.contracts import DIMENSIONS, FAMILIES, Invalid
from book2skill.runtime_reader import encode, query
from book2skill.storage import digest, load, text_hash
from run_demo import build_candidate, protocol_for

class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base/'source'
        self.run = self.base/'run'
        build_candidate(self.run,self.source)
        m,e,r = compilation.source_catalog(self.source)
        self.evidence=e
        self.plan = dict(schema_version='0.0.1',source_manifest_hash=digest(m),builder_context='fixture-builder',
            description='Synthetic runtime transport fixture',core=dict(text='Always check conditions.',source_ids=['source-scope']),
            modules=[dict(id='decision',title='Decision',when='Choose action',text='A' * 700,
                source_ids=[k for k in r if k!='source-scope'],requires=['bounds'],conditional=[]),
                dict(id='bounds',title='Bounds',when='Limits',text='B' * 700,source_ids=['source-scope'],requires=[],conditional=[])],
            archive_only=[],spans=[])
        self.review=self.make_review()
        self.package=self.base/'runtime'
        self.audit=self.base/'audit'
    def make_review(self):
        packet=compilation.review_request(self.source,self.plan)
        return dict(schema_version='0.0.1',source_manifest_hash=packet['source_manifest_hash'],plan_hash=packet['plan_hash'],
            reviewer='synthetic-test-fixture',context_id='fixture-reviewer',fresh_context=True,
            items=[dict(target_id=t,verdict='preserved',rationale='Synthetic transport fixture, not a semantic review.') for t in packet['targets']],unresolved=[])
    def compile(self,mode='bundled'):
        return compilation.compile_package(self.source,self.package,self.plan,self.review,'0.0.2',self.audit,mode)
    def test_review_binding_coverage_and_dependency_gate(self):
        bad=copy.deepcopy(self.plan);bad['modules'][0]['text']+='changed'
        with self.assertRaisesRegex(Invalid,'stale'):
            compilation.compile_package(self.source,self.package,bad,self.review,'0.0.2',self.audit)
        bad=copy.deepcopy(self.plan);bad['modules'][0]['source_ids']=[]
        with self.assertRaises(Invalid): compilation.validate_plan(self.source,bad)
        bad=copy.deepcopy(self.plan);bad['modules'][1]['requires']=['decision']
        with self.assertRaisesRegex(ValueError,'cyclic'): compilation.validate_plan(self.source,bad)
        self.review['items'].pop()
        with self.assertRaisesRegex(Invalid,'every'): self.compile()
    def test_authoring_template_catalog_can_be_retained(self):
        draft=compilation.template(self.source)
        draft.update(self.plan)
        compilation.validate_plan(self.source,draft)
        draft['catalog'].pop()
        with self.assertRaisesRegex(Invalid,'catalog'): compilation.validate_plan(self.source,draft)
    def test_source_review_ids_cannot_collide_with_runtime_targets(self):
        original=compilation.source_catalog(self.source)
        records={**original[2], 'runtime-core': {'id':'runtime-core', 'statement':'Synthetic extra source'}}
        self.plan['modules'][0]['source_ids'].append('runtime-core')
        with patch.object(compilation,'source_catalog',return_value=(original[0],original[1],records)):
            packet=compilation.review_request(self.source,self.plan)
            self.assertEqual(len(packet['targets']),len(set(packet['targets'])))
            self.assertIn('core',packet['targets']);self.assertIn('source/runtime-core',packet['targets'])
    def test_move_and_run_without_repo_or_audit(self):
        self.compile()
        moved=self.base/'moved';shutil.move(self.package,moved)
        shutil.rmtree(self.audit)
        packaging.validate_package(moved)
        proc=subprocess.run([sys.executable,'-S',str(moved/'scripts/read_context.py'),'apply','decision'],cwd='/',text=True,capture_output=True)
        self.assertEqual(proc.returncode,0,proc.stderr)
        packet=json.loads(proc.stdout)
        self.assertEqual({x['id'] for x in packet['items']},{'core','decision','bounds'})
        self.assertFalse((moved/'references/integration.json').exists())
    def test_whole_output_budget_pagination_and_snapshot_cursor(self):
        self.compile()
        cursor=None;seen=[]
        for _ in range(10):
            p=query(self.package,'apply',['decision'],max_chars=1600,cursor=cursor)
            self.assertLessEqual(len(encode(p)),1600)
            self.assertNotEqual(p['status'],'budget_exceeded')
            seen.extend(x['id'] for x in p['items'])
            if not p['next_cursor']:break
            cursor=p['next_cursor']
        self.assertEqual(set(seen),{'core','decision','bounds'})
        self.assertEqual(len(seen),len(set(seen)))
        with self.assertRaisesRegex(ValueError,'different'):
            query(self.package,'apply',['bounds'],cursor=cursor)
        p=query(self.package,'apply',['decision'],max_chars=512)
        self.assertEqual(p['status'],'budget_exceeded');self.assertEqual(p['items'],[])
    def test_seen_requires_exact_snapshot_and_tamper_detected(self):
        self.compile()
        p=query(self.package,'apply',['decision'])
        with self.assertRaises(ValueError): query(self.package,'apply',['decision'],seen=['core'])
        p=query(self.package,'apply',['decision'],seen=['core'],acknowledge=p['snapshot'])
        self.assertNotIn('core',[x['id'] for x in p['items']])
        (self.package/'runtime/modules/bounds.md').write_text('tampered')
        with self.assertRaisesRegex(ValueError,'checksum'): query(self.package,'apply',['decision'])
    def test_locator_only_and_source_expansion(self):
        self.compile(mode='locators')
        pid=self.evidence['passages'][0]['id']
        p=query(self.package,'evidence',[pid]);self.assertIn(pid,p['unavailable_ids'])
        self.assertFalse((self.package/'references/excerpts').exists())
    def test_exact_spans_and_full_segment(self):
        p=self.evidence['passages'][0]
        self.plan['spans']=[dict(passage_id=p['id'],source_sha256=text_hash(p['text']),start=0,end=10,reason='Engineering fixture selection')]
        self.review=self.make_review();self.compile()
        selected=query(self.package,'evidence',[p['id']]);full=query(self.package,'evidence',[p['id']],full=True)
        self.assertEqual(selected['items'][0]['text'],p['text'][:10])
        self.assertEqual(full['items'][0]['text'],p['text'])
    def test_audit_recovery_and_no_overwrite(self):
        self.compile();shutil.rmtree(self.package)
        self.compile()
        with self.assertRaisesRegex(Invalid,'immutable'): self.compile()
        shutil.rmtree(self.package)
        (self.audit/'plan.json').write_text('{}')
        with self.assertRaisesRegex(Invalid,'changed'): self.compile()
    def test_on_demand_freeze_does_not_inject_all_files(self):
        self.compile()
        protocol=protocol_for(self.base/'materials',self.package);protocol['delivery']='on_demand'
        ev=self.base/'eval';evaluation.freeze(ev,protocol)
        state=load(ev);job=next(j for j in state['jobs'] if j['condition']=='B3')
        p=evaluation.public_payload(state,job)
        self.assertEqual([x['path'] for x in p['material']],['SKILL.md'])
        self.assertTrue((Path(p['material_root'])/'scripts/read_context.py').exists())
        self.assertNotIn('expected_behaviors',p)
        (Path(p['material_root'])/'runtime/core.md').write_text('changed')
        with self.assertRaisesRegex(Invalid,'changed'): evaluation.public_payload(state,job)
    def test_on_demand_initial_entry_must_fit_and_be_accounted(self):
        self.compile()
        protocol=protocol_for(self.base/'materials',self.package);protocol['delivery']='on_demand'
        protocol['material_char_budget']=1
        with self.assertRaisesRegex(Invalid,'entry exceeds'): evaluation.freeze(self.base/'tiny',protocol)
        protocol['material_char_budget']=100000
        ev=self.base/'eval';evaluation.freeze(ev,protocol)
        # Issue actual jobs until a nonempty entry is supplied, retaining B0.
        for _ in range(16):
            task=evaluation.issue(ev)
            answer=dict(schema_version='0.0.1',job_id=task['job_id'],status='succeeded',answer='Fixture',error='',
                model=task['model'],host=task['host'],context_id='ctx-'+task['job_id'],fresh_context=True,
                actual_material_chars=0,input_tokens=None,output_tokens=None,cost_usd=None,duration_seconds=None,
                uncertain=True,access_log=[])
            if task['material']:
                with self.assertRaisesRegex(Invalid,'full injected entry'): evaluation.submit_answer(ev,answer)
                entry=task['material'][0]
                answer['access_log']=[dict(path=entry['path'],sha256=text_hash(entry['text']),returned_chars=len(entry['text']))]*2
                answer['actual_material_chars']=2*len(entry['text'])
                evaluation.submit_answer(ev,answer)
                break
            evaluation.submit_answer(ev,answer)
        else:self.fail('no nonempty entry issued')
    def test_context_pages_keep_all_research_dependencies(self):
        s=load(self.run);ids=[x['id'] for x in s['model']['frameworks']]
        expected=workflow.context_payload(s,frameworks=ids)
        cursor=None;actual=[]
        for _ in range(100):
            p=workflow.context_page(self.run,frameworks=ids,max_bytes=3000,cursor=cursor)
            self.assertLessEqual(len(encode(p).encode()),3000)
            actual.extend(p['items']);cursor=p['next_cursor']
            if not cursor:break
        expected_count=sum(len(v) for v in expected.values() if isinstance(v,list))
        self.assertEqual(len(actual),expected_count)
        self.assertEqual(p['status'],'complete')
        out=self.base/'page.json'
        proc=subprocess.run([sys.executable,'-m','book2skill','context-page',str(self.run),'--frameworks',*ids,
                             '--max-bytes','3000','--out',str(out)],capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertLessEqual(len(out.read_bytes().rstrip(b'\n')),3000)
    def test_optimization_protocol_freezes_noninferiority_and_read_target(self):
        self.compile()
        p=protocol_for(self.base/'materials',self.package)
        p.update(comparison_kind='optimization',delivery='on_demand',max_quality_drop=0,min_read_reduction=.5)
        p['conditions']=[c for c in p['conditions'] if c['id'] in ('B1','B3')]
        ev=self.base/'optimization'
        evaluation.freeze(ev,p)
        report=evaluation.report(ev)
        self.assertEqual(report['outcome'],'insufficient_evidence')
        self.assertIn('optimization_metrics',report)
        p.pop('max_quality_drop')
        with self.assertRaisesRegex(Invalid,'tolerance'):evaluation.freeze(self.base/'invalid-opt',p)

    def optimization_trial(self,kind):
        self.compile()
        p=protocol_for(self.base/'materials',self.package)
        p.update(comparison_kind='optimization',delivery='on_demand',max_quality_drop=0,min_read_reduction=.5,repetitions=2,max_calls=40)
        p['conditions']=[c for c in p['conditions'] if c['id'] in ('B1','B3')]
        if kind=='zero':
            folder=self.base/'empty-entry';folder.mkdir()
            (folder/'a.txt').write_text('A'*10000);(folder/'b.txt').write_text('B'*10000)
            p['conditions'][0]['material_path']=str(folder)
        ev=self.base/'optimization';evaluation.freeze(ev,p)
        initial=load(ev);jobs={j['id']:j for j in initial['jobs']}
        cases={c['id']:c for c in p['cases']}
        for _ in jobs:
            task=evaluation.issue(ev);j=jobs[task['job_id']]
            files=initial['materials'][j['condition']];entry=evaluation.entry_material(files)
            rows=[dict(path=entry['path'],sha256=text_hash(entry['text']),returned_chars=len(entry['text']))] if entry else []
            if not entry and j['case_id']=='case-0':
                rows=[dict(path=files[0]['path'],sha256=text_hash(files[0]['text']),returned_chars=len(files[0]['text']))]
            answer=dict(schema_version='0.0.1',job_id=j['id'],status='succeeded',answer='Synthetic arithmetic fixture',error='',
                model=p['model'],host=p['host'],context_id=j['id'],fresh_context=True,actual_material_chars=sum(x['returned_chars'] for x in rows),
                input_tokens=None,output_tokens=None,cost_usd=None,duration_seconds=None,uncertain=True,access_log=rows)
            if kind=='retry' and j['condition']=='B3':
                failed={**answer,'status':'failed','answer':'','error':'synthetic retry','context_id':j['id']+'-failed',
                        'access_log':rows*30,'actual_material_chars':answer['actual_material_chars']*30}
                evaluation.submit_answer(ev,failed);evaluation.retry(ev,j['id'],'fixture')
                self.assertEqual(evaluation.issue(ev)['job_id'],j['id'])
            evaluation.submit_answer(ev,answer)
            scores={d:1 for d in DIMENSIONS}
            if kind=='cancellation' and j['condition']=='B3':
                direction=1 if j['repeat']==1 else -1
                family=cases[j['case_id']]['family']
                if family==FAMILIES[0]:scores[DIMENSIONS[0]]=1-direction
                if family==FAMILIES[1]:scores[DIMENSIONS[0]]=1+direction
            evaluation.submit_score(ev,dict(schema_version='0.0.1',review_id=j['review_id'],reviewer='synthetic-test',reviewer_type='model',
                scores=scores,boundary_error=False,fabricated_attribution=False,concealed_gap=False,failure_types=[],
                rationale='Arithmetic fixture, not model quality evidence',human_checked=False))
        return evaluation.report(ev)
    def test_zero_baselines_are_not_discarded(self):
        report=self.optimization_trial('zero')
        self.assertTrue(any('increased from zero' in r for r in report['reasons']))
        self.assertEqual(report['optimization_metrics']['round-1']['paired_cases'],4)
    def test_failed_attempt_reading_counts_against_efficiency(self):
        report=self.optimization_trial('retry')
        self.assertLess(report['optimization_metrics']['round-1']['median_read_reduction'],0)
    def test_quality_cannot_cancel_between_rounds(self):
        report=self.optimization_trial('cancellation')
        self.assertTrue(any('round 1: optimization quality regression' in r for r in report['reasons']))
        self.assertTrue(any('round 2: optimization quality regression' in r for r in report['reasons']))

if __name__=='__main__': unittest.main()
