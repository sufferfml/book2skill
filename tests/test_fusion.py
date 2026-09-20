"""Multi-book engineering contracts, not claims about semantic effectiveness."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'examples')]
from book2skill import cli, evaluation, fusion, packaging, workflow
from book2skill.contracts import Invalid
from book2skill.storage import commit, digest, load, load_json, write_json
from run_demo import build_candidate, config, protocol_for, usage
from run_fusion_demo import (construct, make_inputs, model_for_fusion, plan_for,
                             read_inputs, review, review_for)


class FusionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        cls.inputs, cls.config = make_inputs(Path(cls.fixture.name))

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.run = self.base / 'fusion'
        fusion.initialize(self.run, self.inputs, self.config)

    def plan(self, outcome='integrate'):
        t = workflow.prepare(self.run, 'fusion-plan')
        read_inputs(self.run)
        data = plan_for(load(self.run), outcome)
        return t, data

    def modeled(self):
        construct(self.run)

    def candidate(self):
        self.modeled()
        review(self.run)
        dest = self.base / 'candidate'
        packaging.package(self.run, dest, 'test-fusion', '0.0.1')
        return dest

    def test_portable_package_preserves_both_books_and_lineage(self):
        dest = self.candidate()
        manifest = load_json(dest / 'manifest.json')
        self.assertEqual(manifest['kind'], 'fusion')
        self.assertEqual(len(manifest['books']), 2)
        provenance = load_json(dest / 'references/integration.json')
        self.assertTrue(provenance['lineage'])
        self.assertNotIn('run_path', provenance['books'][0])
        self.assertIn('routing.md', (dest / 'SKILL.md').read_text())
        self.assertIn('conditional_alternative', (dest / 'routing.md').read_text())
        records = load(self.run)['input_records']
        self.assertIn('book-a--claim-probe', records)
        self.assertIn('book-b--claim-probe', records)
        moved = self.base / 'moved'
        shutil.move(dest, moved)
        packaging.validate_package(moved)
        (moved / 'routing.md').write_text('tampered')
        with self.assertRaises(Invalid):
            packaging.validate_package(moved)

    def test_duplicate_alias_or_same_book_cannot_fake_multiple_books(self):
        for change in ('alias', 'source'):
            inputs = copy.deepcopy(self.inputs)
            inputs['books'][1]['id' if change == 'alias' else 'run_path'] = inputs['books'][0]['id' if change == 'alias' else 'run_path']
            with self.subTest(change=change), self.assertRaisesRegex(Invalid, 'duplicate'):
                fusion.initialize(self.base / change, inputs, self.config)

    def test_unreviewed_or_stale_parent_rejected(self):
        parent = self.base / 'parent'
        shutil.copytree(self.inputs['books'][0]['run_path'], parent)
        inputs = copy.deepcopy(self.inputs)
        inputs['books'][0]['run_path'] = str(parent)
        state = load(parent)
        state['review']['model_hash'] = '0' * 64
        commit(parent, state, 'fixture-stale-review')
        with self.assertRaisesRegex(Invalid, 'review does not certify'):
            fusion.initialize(self.base / 'stale', inputs, self.config)
        workflow.revise(parent, 'model', 'fixture revision')
        with self.assertRaisesRegex(Invalid, 'drafts cannot'):
            fusion.initialize(self.base / 'draft', inputs, self.config)

    def test_planning_requires_current_reads_and_every_framework(self):
        t = workflow.prepare(self.run, 'fusion-plan')
        data = plan_for(load(self.run))
        with self.assertRaisesRegex(Invalid, 'read all input'):
            workflow.submit(self.run, t['id'], data, usage(t))
        read_inputs(self.run)
        data['dispositions'].pop()
        with self.assertRaisesRegex(Invalid, 'every input framework'):
            workflow.submit(self.run, t['id'], data, usage(t))

    def test_bridge_validation_preserves_conflicts_and_evidence(self):
        t, original = self.plan()
        for mutation, error in (
            ({'relationship': 'contradicts', 'resolution': 'combine'}, 'forcibly'),
            ({'relationship': 'unrelated', 'resolution': 'combine'}, 'forcibly'),
            ({'conditions': []}, 'explicit conditions'),
            ({'right_ids': original['bridges'][0]['left_ids']}, 'distinct books'),
            ({'evidence_refs': fusion.evidence_refs([x['record'] for x in load(self.run)['input_records'].values() if x['book_id'] == 'book-a'])[:2]}, 'both books'),
        ):
            data = copy.deepcopy(original)
            data['bridges'][0].update(mutation)
            with self.subTest(mutation=mutation), self.assertRaisesRegex(Invalid, error):
                workflow.submit(self.run, t['id'], data, usage(t))
        data = copy.deepcopy(original)
        data['bridges'] = []
        with self.assertRaisesRegex(Invalid, 'each pair'):
            workflow.submit(self.run, t['id'], data, usage(t))

    def test_unresolved_comparison_blocks_synthesis(self):
        t, data = self.plan()
        data['bridges'][0]['resolution'] = 'unresolved'
        workflow.submit(self.run, t['id'], data, usage(t))
        with self.assertRaisesRegex(Invalid, 'unresolved bridge'):
            workflow.prepare(self.run, 'fusion-model')

    def test_model_requires_new_reads_lineage_and_faithful_attribution(self):
        t, plan = self.plan()
        workflow.submit(self.run, t['id'], plan, usage(t))
        t = workflow.prepare(self.run, 'fusion-model')
        original = model_for_fusion(load(self.run))
        with self.assertRaisesRegex(Invalid, 'reread lineage'):
            workflow.submit(self.run, t['id'], original, usage(t))
        read_inputs(self.run)
        for mutation, error in (
            (lambda d: d['lineage'].pop(), 'unique lineage'),
            (lambda d: d['model']['claims'][0].update(statement='Overstated author advice'), 'preserved verbatim'),
            (lambda d: d['lineage'][2].update(bridge_ids=[]), 'justified bridge'),
            (lambda d: d['model']['claims'][2].update(evidence_refs=d['model']['claims'][0]['evidence_refs']), 'each contributing book'),
            (lambda d: d['model']['frameworks'][0]['claim_ids'].remove('claim-select'), 'all claims'),
        ):
            data = copy.deepcopy(original)
            mutation(data)
            with self.subTest(error=error), self.assertRaisesRegex(Invalid, error):
                workflow.submit(self.run, t['id'], data, usage(t))

    def test_keep_separate_bridge_cannot_justify_combined_output(self):
        t, data = self.plan()
        data['bridges'][0]['resolution'] = 'keep_separate'
        workflow.submit(self.run, t['id'], data, usage(t))
        t = workflow.prepare(self.run, 'fusion-model')
        read_inputs(self.run)
        with self.assertRaisesRegex(Invalid, 'keep-separate'):
            workflow.submit(self.run, t['id'], model_for_fusion(load(self.run)), usage(t))

    def test_model_extensions_cannot_be_certified_as_source_support(self):
        t, data = self.plan()
        workflow.submit(self.run, t['id'], data, usage(t))
        t = workflow.prepare(self.run, 'fusion-model')
        read_inputs(self.run)
        data = model_for_fusion(load(self.run))
        data['model']['claims'][2]['epistemic_origin'] = 'model_extension'
        workflow.submit(self.run, t['id'], data, usage(t))
        t = workflow.prepare(self.run, 'fusion-review', targets=['claim-select'])
        with self.assertRaisesRegex(Invalid, 'remain hypotheses'):
            workflow.submit(self.run, t['id'], review_for(t, 'supported'), usage(t))
        workflow.submit(self.run, t['id'], review_for(t), usage(t))

    def test_three_books_require_pairwise_comparison_and_allow_exclusion(self):
        source = self.base / 'third.md'
        source.write_text((ROOT / 'examples/synthetic-book.md').read_text() + '\n第三个工程样本，仅用于验证多来源标识与排除流程。\n')
        third = self.base / 'book-c'
        build_candidate(third, self.base / 'candidate-c', source=source, configuration={**config(), 'book_version': 'third-fixture'})
        inputs = copy.deepcopy(self.inputs)
        inputs['books'].append({'id': 'book-c', 'run_path': str(third)})
        self.run = self.base / 'three-books'
        fusion.initialize(self.run, inputs, self.config)
        t, data = self.plan()
        with self.assertRaisesRegex(Invalid, 'each pair'):
            workflow.submit(self.run, t['id'], data, usage(t))
        data['dispositions'][2].update(action='reference_only', rationale='No additional capability for this purpose.')
        workflow.submit(self.run, t['id'], data, usage(t))
        t = workflow.prepare(self.run, 'fusion-model')
        read_inputs(self.run)
        model = model_for_fusion(load(self.run))
        bad = copy.deepcopy(model)
        bad['lineage'][0]['input_ids'] = ['book-c--claim-probe']
        with self.assertRaisesRegex(Invalid, 'excluded/reference-only'):
            workflow.submit(self.run, t['id'], bad, usage(t))
        workflow.submit(self.run, t['id'], model, usage(t))
        review(self.run)
        result = packaging.package(self.run, self.base / 'three-book-candidate', 'three-book-choice', '0.0.1')
        self.assertEqual(len(result['manifest']['books']), 3)
        self.assertEqual(load(self.run)['integration']['dispositions'][2]['action'], 'reference_only')

    def test_zipapp_fusion_outside_checkout_without_site_packages(self):
        runtime = self.base / 'book2skill.pyz'
        shutil.copy2(ROOT / 'skill/book2skill/scripts/book2skill.pyz', runtime)
        write_json(self.base / 'books.json', self.inputs)
        write_json(self.base / 'config.json', self.config)
        command = [sys.executable, '-S', str(runtime)]
        result = subprocess.run(command + ['fusion-init', 'portable', '--books', 'books.json', '--config', 'config.json'],
                                cwd=self.base, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['kind'], 'fusion')
        result = subprocess.run(command + ['task', 'portable', 'fusion-plan'], cwd=self.base, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['kind'], 'fusion-plan')

    def test_fresh_review_exact_targets_and_evidence(self):
        self.modeled()
        t = workflow.prepare(self.run, 'fusion-review')
        original = review_for(t)
        for mutation, error in (
            (lambda d: d.update(context_id='authored-fixture-builder'), 'non-builder'),
            (lambda d: d.update(fresh_context=False), 'fresh'),
            (lambda d: d.update(integration_hash='0' * 64), 'stale'),
            (lambda d: d['items'].pop(), 'all and only'),
            (lambda d: d['items'][0].update(evidence_refs=[]), 'all target evidence'),
        ):
            data = copy.deepcopy(original)
            mutation(data)
            with self.subTest(error=error), self.assertRaisesRegex(Invalid, error):
                workflow.submit(self.run, t['id'], data, usage(t))

    def test_failed_review_blocks_package_until_revision(self):
        self.modeled()
        t = workflow.prepare(self.run, 'fusion-review')
        workflow.submit(self.run, t['id'], review_for(t, 'unsupported'), usage(t))
        self.assertEqual(workflow.status(self.run)['outcome'], 'needs_revision')
        with self.assertRaisesRegex(Invalid, 'review failures'):
            packaging.package(self.run, self.base / 'bad', 'bad-fusion', '0.0.1')
        workflow.revise(self.run, 'model', 'correct unsupported integration')
        state = load(self.run)
        self.assertIsNone(state['model'])
        self.assertIsNone(state['review'])
        self.assertIsNotNone(state['integration'])

    def test_revision_invalidates_packages_but_preserves_frozen_files(self):
        dest = self.candidate()
        before = (dest / 'manifest.json').read_bytes()
        workflow.revise(self.run, 'plan', 'new integration policy')
        state = load(self.run)
        self.assertIsNone(state['integration'])
        self.assertEqual(state['lineage'], [])
        self.assertTrue(state['packages'][0]['stale'])
        self.assertEqual(before, (dest / 'manifest.json').read_bytes())

    def test_reviewed_nonintegration_is_successful_and_does_not_package(self):
        for outcome in ('keep_separate', 'insufficient_evidence'):
            workflow.revise(self.run, 'plan', 'exercise valid stop')
            t, data = self.plan(outcome)
            workflow.submit(self.run, t['id'], data, usage(t))
            review(self.run)
            status = workflow.status(self.run)
            self.assertEqual(status['outcome'], outcome)
            self.assertEqual(status['status'], 'completed')
            with self.assertRaisesRegex(Invalid, 'only a reviewed integration'):
                packaging.package(self.run, self.base / outcome, 'no-fusion', '0.0.1')

    def test_resume_idempotency_and_budget_gate(self):
        t, data = self.plan()
        self.assertEqual(load(self.run)['pending'], t)
        workflow.submit(self.run, t['id'], data, usage(t))
        revision = load(self.run)['revision']
        workflow.submit(self.run, t['id'], data, usage(t))
        self.assertEqual(load(self.run)['revision'], revision)
        cfg = {**self.config, 'max_cost_usd': 1}
        workflow.revise(self.run, 'budget', 'test unknown monetary costs', cfg)
        with self.assertRaisesRegex(Invalid, 'budget exhausted or unknown'):
            workflow.prepare(self.run, 'fusion-model')
        self.assertEqual(workflow.status(self.run)['status'], 'budget_stopped')

    def test_context_keeps_constraints_and_rejects_silent_truncation(self):
        ident = 'book-a--claim-probe'
        before = load(self.run)['revision']
        with self.assertRaisesRegex(Invalid, 'context'):
            fusion.context(self.run, [ident], budget=50)
        self.assertEqual(load(self.run)['revision'], before)
        packet = fusion.context(self.run, [ident])
        ids = {x['record']['id'] for x in packet['input_records']}
        self.assertIn('book-a--claim-irreversible', ids)
        self.assertIn('book-a--relation-tide', ids)

    def test_changed_parent_detected_without_mutating_frozen_run(self):
        parent = self.base / 'parent'
        shutil.copytree(self.inputs['books'][0]['run_path'], parent)
        inputs = copy.deepcopy(self.inputs)
        inputs['books'][0]['run_path'] = str(parent)
        other = self.base / 'other'
        fusion.initialize(other, inputs, self.config)
        before = digest(load(other))
        workflow.revise(parent, 'model', 'updated interpretation')
        self.assertEqual(fusion.source_check(other)['books'][0]['current_run'], 'changed')
        self.assertEqual(before, digest(load(other)))
        construct(other)
        review(other)
        packaging.package(other, self.base / 'frozen-candidate', 'frozen', '0.0.1')

    def test_cli_relative_manifest_and_malformed_input(self):
        inputs = copy.deepcopy(self.inputs)
        import os
        for book in inputs['books']:
            book['run_path'] = os.path.relpath(book['run_path'], self.base)
        write_json(self.base / 'books.json', inputs)
        write_json(self.base / 'config.json', self.config)
        args = cli.parser().parse_args(['fusion-init', str(self.base / 'cli-run'), '--books', str(self.base / 'books.json'), '--config', str(self.base / 'config.json')])
        cli.execute(args)
        self.assertEqual(len(load(self.base / 'cli-run')['books']), 2)
        write_json(self.base / 'books.json', [])
        with self.assertRaises(Invalid):
            cli.execute(args)

    def formal_protocol(self):
        candidate = self.candidate()
        p = protocol_for(self.base / 'materials', candidate)
        originals = p['cases']
        p['cases'] = []
        for index in range(28):
            case = copy.deepcopy(originals[index % 4])
            case.update(id=f'case-{index}', input=f'engineering fusion scenario {index}',
                        split='dev' if index < 8 else 'heldout', cross_book=index >= 13,
                        baseline_regression=8 <= index < 13)
            p['cases'].append(case)
        p.update(mode='formal', comparison_kind='fusion', repetitions=2, max_calls=180)
        p['conditions'][2]['provenance'] = 'Two frozen independent books without an integration policy; fixture only'
        return p

    def test_fusion_evaluation_requires_cross_book_and_regression_cases(self):
        p = self.formal_protocol()
        for field, error in (('cross_book', 'cross-book'), ('baseline_regression', 'baseline regression')):
            bad = copy.deepcopy(p)
            for case in bad['cases']:
                case[field] = False
            with self.subTest(field=field), self.assertRaisesRegex(Invalid, error):
                evaluation.freeze(self.base / field, bad)
        # Fusion B2 is an independent-material baseline, so upstream commit syntax does not apply.
        result = evaluation.freeze(self.base / 'evaluation', p)
        self.assertEqual(result['jobs'], 160)
        self.assertTrue(any('B2/B3' in w for w in result['warnings']))

    def test_regression_cannot_hide_behind_higher_average(self):
        p = self.formal_protocol()
        # Matching lengths only exercises arithmetic; these are not actual baseline materials.
        b3_chars = sum(len(x['text']) for x in evaluation.material(p['conditions'][3]['material_path']))
        Path(p['conditions'][2]['material_path']).write_text('x' * b3_chars)
        ev = self.base / 'evaluation'
        evaluation.freeze(ev, p)
        state = load(ev)
        for job in state['jobs']:
            job['status'] = 'succeeded'
            job['answer'] = {'answer': 'report-engine fixture only'}
            job['scores'] = [{'reviewer': 'fixture', 'reviewer_type': 'model', 'human_checked': False,
                'scores': {d: 2 if job['condition'] == 'B3' else 1 for d in ('mapping', 'boundaries', 'fidelity', 'action', 'revision')},
                'boundary_error': False, 'fabricated_attribution': False, 'concealed_gap': False,
                'failure_types': [], 'rationale': 'Synthetic scoring arithmetic only'}]
        commit(ev, state, 'report-engine-only-fixture')
        self.assertEqual(evaluation.report(ev)['outcome'], 'validated_scoped')
        state = load(ev)
        job = next(j for j in state['jobs'] if j['condition'] == 'B3' and j['case_id'] == 'case-8')
        job['scores'][0]['scores']['boundaries'] = 0
        commit(ev, state, 'fixture-regression-with-positive-average')
        report = evaluation.report(ev)
        self.assertEqual(report['outcome'], 'insufficient_evidence')
        self.assertTrue(any('baseline regression on case-8' in r for r in report['reasons']))


if __name__ == '__main__':
    unittest.main()
