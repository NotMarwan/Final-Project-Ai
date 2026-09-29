import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('docs_contract',ROOT/'scripts/docs_contract.py')
contract=importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)

class DocumentationGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        def cleanup():
            target=Path(self.temp.name).resolve()
            base=Path(tempfile.gettempdir()).resolve()
            if target.parent!=base or not target.name.startswith('tmp'):
                raise RuntimeError('Unexpected recursive cleanup target')
            self.temp.cleanup()
        self.addCleanup(cleanup)
        self.root=Path(self.temp.name)
        blueprint={
            'schema_version':1,
            'kind':'living-blueprint-index',
            'non_authoritative':True,
            'inputs':[{'path':'docs/blueprint/input.md','produced_by':'fixture','sha256':None}],
            'entries':[{
                'id':'F-01','title':'Fixture feature','kind':'runtime','status':'unverified',
                'source_refs':['backend/api.py:1'],'tests':[],
                'evidence':['docs/blueprint/input.md#1'],
                'limitations':['fixture limitation'],
                'links':{'ui':['U-01']},
            },{
                'id':'U-01','title':'Fixture screen','kind':'ui','status':'unverified',
                'source_refs':[],'tests':[],'evidence':['docs/blueprint/input.md#1'],
                'limitations':['fixture limitation'],'links':{'features':['F-01']},
            }],
        }
        files={
            'app/globals.css':':root { --background: #000000; --foreground: #ffffff; --primary: #0000ff; --radius: 1rem; }',
            'app/layout.tsx':"import './globals.css'",
            'styles/globals.css':"@import '../app/globals.css';",
            'backend/api.py':'# baseline source\n',
            'components.json':json.dumps({'tailwind':{'css':'app/globals.css'},'style':'new-york'}),
            'package.json':json.dumps({'dependencies':{'next':'16.1.6'}}),
            'bench/results/baseline-all-detection/report.json':json.dumps({
                'workload_valid':True,
                'environment':{'revision':'test','source_hashes':{'backend/api.py':contract.digest(b'# baseline source\n')}},
                'summary':{'render_fps':{'p50':30.0},'model_call_counts':{
                    'violence_window':1,'weapon_window':1,'person_onnx':1,'person_yolo':0}},
            }),
            'docs/authority.json':json.dumps({
                'canonical_docs':['docs/CURRENT.md','docs/PLAN.md'],
                'retired_paths':['docs/OLD.md'],
                'agent_entrypoints':['AGENTS.md','CLAUDE.md'],
                'scoped_artifacts':{
                    'policy':'non-authoritative',
                    'roots':['docs/blueprint/','docs/campaign/'],
                    'marker':{'format':'yaml-frontmatter','required':{'authority':'scoped','non_authoritative':True}},
                    'alternate_registries':['docs/campaign/index.json'],
                },
            }),
            'docs/blueprint/input.md':'---\nauthority: scoped\nnon_authoritative: true\n---\n# Fixture input\n\n## 1. Fixture section\n',
            'AGENTS.md':'Read docs/CURRENT.md',
            'CLAUDE.md':'Read AGENTS.md',
            'docs/blueprint/index.json':json.dumps(blueprint),
        }
        for name,text in files.items():
            path=self.root/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(text,encoding='utf-8')
        blueprint['inputs'][0]['sha256']=contract.source_digest(self.root/'docs/blueprint/input.md')
        by_id={entry['id']:entry for entry in blueprint['entries']}
        by_id['F-01']['assessed']={'backend/api.py':contract.source_digest(self.root/'backend/api.py')}
        (self.root/'docs/blueprint/index.json').write_text(json.dumps(blueprint),encoding='utf-8')

    def index(self):
        return json.loads((self.root/'docs/blueprint/index.json').read_text(encoding='utf-8'))

    def write_index(self,data):
        (self.root/'docs/blueprint/index.json').write_text(json.dumps(data),encoding='utf-8')

    def test_source_color_change_changes_generated_reference(self):
        before=contract.generate(self.root)
        path=self.root/'app/globals.css'
        path.write_text(path.read_text().replace('#0000ff','#ff0000'))
        after=contract.generate(self.root)
        self.assertNotEqual(before['docs/DESIGN.md'],after['docs/DESIGN.md'])
        self.assertIn('#ff0000',after['docs/design-tokens.json'])

    def test_second_palette_is_rejected(self):
        (self.root/'styles/globals.css').write_text(':root { --primary: red; }')
        with self.assertRaisesRegex(ValueError,'Duplicate stylesheet'):
            contract.generate(self.root)

    def test_retired_document_cannot_return(self):
        (self.root/'docs/OLD.md').write_text('old frozen release')
        self.assertTrue(any('Retired' in x for x in contract.check_policy(self.root)))

    def test_unregistered_document_is_rejected(self):
        (self.root/'docs/ANOTHER-STATUS.md').write_text('all gates pass')
        self.assertTrue(any('Unregistered' in x for x in contract.check_policy(self.root)))

    def test_canonical_document_mojibake_is_rejected(self):
        (self.root/'docs/CURRENT.md').write_text('Target â‰¥ 30 fps',encoding='utf-8')
        self.assertTrue(any('mojibake' in x for x in contract.check_policy(self.root)))

    def test_backend_change_marks_evidence_stale(self):
        (self.root/'backend/api.py').write_text('# changed runtime\n')
        result=contract.generate(self.root)
        self.assertIn('Baseline source is stale or incomplete',result['docs/CURRENT.md'])

    def test_nested_backend_source_is_fingerprinted_and_marks_missing_evidence_coverage(self):
        nested=self.root/'backend/models/runtime_model.py'
        nested.parent.mkdir(parents=True)
        nested.write_text('# runtime model\n')
        result=contract.generate(self.root)
        manifest=json.loads(result['docs/SOURCE-MANIFEST.json'])
        self.assertIn('backend/models/runtime_model.py',manifest['source_sha256'])
        self.assertEqual(manifest['baseline_backend_unrecorded'],['backend/models/runtime_model.py'])
        self.assertIn('not covered by the registered report',result['docs/CURRENT.md'])

    def test_rejected_runtime_report_cannot_be_registered(self):
        report=self.root/'bench/results/baseline-all-detection/report.json'
        payload=json.loads(report.read_text())
        payload['workload_valid']=False
        report.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError,'rejected or inactive'):
            contract.generate(self.root)

    def test_runtime_report_without_active_models_cannot_be_registered(self):
        report=self.root/'bench/results/baseline-all-detection/report.json'
        payload=json.loads(report.read_text())
        payload['summary']['model_call_counts']['weapon_window']=0
        report.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError,'violence, weapon, and person'):
            contract.generate(self.root)

    def test_entrypoint_drift_is_detected(self):
        (self.root/'CLAUDE.md').write_text('use old plan')
        self.assertTrue(any('entrypoint' in x for x in contract.check_policy(self.root)))

    def test_component_generator_cannot_choose_another_stylesheet(self):
        (self.root/'components.json').write_text(json.dumps({'tailwind':{'css':'styles/other.css'},'style':'new-york'}))
        with self.assertRaisesRegex(ValueError,'different design system'):
            contract.generate(self.root)

    def test_scoped_document_requires_non_authority_marker(self):
        (self.root/'docs/campaign').mkdir(exist_ok=True)
        (self.root/'docs/campaign/note.md').write_text('# scoped catalog without a marker\n')
        self.assertTrue(any('Scoped document missing non-authority marker: docs/campaign/note.md' in x for x in contract.check_policy(self.root)))
        (self.root/'docs/campaign/note.md').write_text('---\nauthority: scoped\nnon_authoritative: true\n---\n# scoped catalog\n')
        self.assertFalse(any('docs/campaign/note.md' in x for x in contract.check_policy(self.root)))

    def test_scoped_document_cannot_be_promoted_to_canonical(self):
        policy=json.loads((self.root/'docs/authority.json').read_text(encoding='utf-8'))
        policy['canonical_docs'].append('docs/blueprint/input.md')
        (self.root/'docs/authority.json').write_text(json.dumps(policy),encoding='utf-8')
        self.assertTrue(any('Scoped artifact promoted to canonical document: docs/blueprint/input.md' in x for x in contract.check_policy(self.root)))

    def test_blueprint_missing_index_is_rejected(self):
        (self.root/'docs/blueprint/index.json').unlink()
        with self.assertRaisesRegex(ValueError,'Missing blueprint index'):
            contract.generate(self.root)

    def test_blueprint_schema_rejects_unknown_status(self):
        data=self.index()
        data['entries'][0]['status']='green'
        self.write_index(data)
        with self.assertRaisesRegex(ValueError,'unknown status'):
            contract.generate(self.root)

    def test_blueprint_schema_rejects_id_kind_mismatch(self):
        data=self.index()
        data['entries'][0]['id']='U-99'
        self.write_index(data)
        with self.assertRaisesRegex(ValueError,'id/kind mismatch'):
            contract.generate(self.root)

    def test_blueprint_missing_source_reference_is_detected(self):
        data=self.index()
        data['entries'][0]['source_refs']=['backend/ghost.py']
        self.write_index(data)
        self.assertTrue(any('F-01 references missing source: backend/ghost.py' in x for x in contract.blueprint_failures(self.root)))

    def test_blueprint_stale_source_fingerprint_is_detected(self):
        (self.root/'backend/api.py').write_text('# changed runtime\n')
        failures=contract.blueprint_failures(self.root)
        self.assertTrue(any('F-01 disagrees with source fingerprint for backend/api.py' in x for x in failures))

    def test_blueprint_link_to_unknown_id_is_detected(self):
        data=self.index()
        data['entries'][0]['links']={'ui':['U-77']}
        self.write_index(data)
        self.assertTrue(any('F-01 links unknown blueprint id: U-77' in x for x in contract.blueprint_failures(self.root)))

    def test_blueprint_stale_evidence_anchor_is_detected(self):
        data=self.index()
        data['entries'][0]['evidence']=['docs/blueprint/input.md#9']
        self.write_index(data)
        self.assertTrue(any('stale evidence anchor' in x for x in contract.blueprint_failures(self.root)))

    def test_canonical_doc_citing_unknown_blueprint_id_is_detected(self):
        (self.root/'docs/PLAN.md').write_text('Pending work for F-77 and F-01.\n')
        failures=contract.blueprint_failures(self.root)
        self.assertTrue(any('docs/PLAN.md cites unknown blueprint id: F-77' in x for x in failures))
        self.assertFalse(any('unknown' in x and 'F-01' in x for x in failures))

    def test_changed_blueprint_input_is_detected(self):
        path=self.root/'docs/blueprint/input.md'
        path.write_text(path.read_text()+'extra\n')
        self.assertTrue(any('Blueprint input fingerprint mismatch: docs/blueprint/input.md' in x for x in contract.blueprint_failures(self.root)))

    def test_generated_blueprint_view_is_scoped_and_navigable(self):
        view=contract.generate(self.root)['docs/blueprint/INDEX.md']
        self.assertIn('authority: scoped',view)
        self.assertIn('non_authoritative: true',view)
        self.assertIn('F-01',view)
        self.assertIn('U-01',view)

if __name__=='__main__':
    unittest.main()
