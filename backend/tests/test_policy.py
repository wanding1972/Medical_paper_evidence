import json
from pathlib import Path
import shutil
import tempfile
import unittest
from pydantic import ValidationError
from evidence_check.application.api import audit_document
from evidence_check.contracts.errors import InputError, PolicyError
from evidence_check.infrastructure.api import load_policy
from support import BACKEND, document, policy


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config=Path(self.temp.name)/'config'
        shutil.copytree(BACKEND/'config',self.config)

    def mutate(self,file,change):
        path=self.config/file
        data=json.loads(path.read_text())
        change(data)
        path.write_text(json.dumps(data))

    def test_policy_is_deeply_immutable(self):
        loaded=policy()
        with self.assertRaises(ValidationError): loaded.audit.rules[0].label='anything'
        self.assertIsInstance(loaded.audit.rules,tuple)
        self.assertIsInstance(loaded.limits.document_gates,tuple)

    def test_rule_mapping_disable_and_message_are_data(self):
        def change(data):
            data['rules'][1]['severity']='info'
            data['rules'][1]['message']='Changed in config'
            data['rules'][2]['enabled']=False
        self.mutate('audit_rules.json',change)
        report=audit_document(document('Synthetic[1,9].'),load_policy(self.config))
        self.assertEqual(len(report.findings),1)
        self.assertEqual(report.findings[0].severity,'info')
        self.assertEqual(report.findings[0].message,'Changed in config')

    def test_input_threshold_changes_behavior(self):
        def change(data):
            next(g for g in data['document_gates'] if g['code']=='document_too_long')['when'][0]['value']=2
        self.mutate('limits.json',change)
        with self.assertRaises(InputError):
            audit_document(document('中文字'),load_policy(self.config))
        self.assertTrue(audit_document(document('中文字'),policy()))

    def test_invalid_configuration_is_stable_failure(self):
        cases=[
            ('audit_rules.json',lambda d:d['rules'][0]['when'][0].update(field='invented_fact')),
            ('audit_rules.json',lambda d:d['rules'][0]['when'][0].update(op='eval')),
            ('audit_rules.json',lambda d:d['rules'][0].update(severity='invented')),
            ('audit_rules.json',lambda d:d['rules'][3].update(enabled=True)),
            ('audit_rules.json',lambda d:d['rules'].append(d['rules'][0])),
            ('limits.json',lambda d:d.update(version='other')),
            ('limits.json',lambda d:d['security'].update(external_llm_enabled=True)),
            ('limits.json',lambda d:d['document_gates'][0]['when'][0].update(op='gt',value=1)),
            ('parsing.json',lambda d:d.update(sentence_pattern='[')),
            ('retrieval.json',lambda d:d.update(implemented=True)),
        ]
        for index,(file,change) in enumerate(cases):
            with self.subTest(index=index):
                shutil.rmtree(self.config)
                shutil.copytree(BACKEND/'config',self.config)
                self.mutate(file,change)
                with self.assertLogs('evidence_check.infrastructure.api',level='ERROR'),self.assertRaises(PolicyError) as caught:
                    load_policy(self.config)
                self.assertEqual(caught.exception.code,'policy_invalid')

    def test_missing_or_corrupt_policy_file(self):
        (self.config/'audit_rules.json').write_text('{')
        with self.assertLogs(level='ERROR'),self.assertRaises(PolicyError): load_policy(self.config)
        (self.config/'audit_rules.json').unlink()
        with self.assertLogs(level='ERROR'),self.assertRaises(PolicyError): load_policy(self.config)
