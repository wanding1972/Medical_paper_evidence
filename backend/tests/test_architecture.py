"""Structural enforcement complements, rather than replaces, manual R1 review."""
import ast
import json
from pathlib import Path
import unittest
from support import BACKEND, ROOT

SOURCE=BACKEND/'src'
PACKAGE=SOURCE/'evidence_check'


def modules():
    return {'.'.join(path.relative_to(SOURCE).with_suffix('').parts):path for path in PACKAGE.rglob('*.py')}


def imports(tree):
    result=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):result.extend(alias.name for alias in node.names)
        if isinstance(node,ast.ImportFrom):
            if node.level:raise AssertionError('Relative imports require an explicit resolver; use absolute public paths')
            result.append(node.module or '')
    return result


def cycles(graph):
    active=set();done=set()
    def visit(node):
        if node in active:raise AssertionError(f'Import cycle: {node}')
        if node in done:return
        active.add(node)
        for dependency in graph[node]:visit(dependency)
        active.remove(node);done.add(node)
    for node in graph:visit(node)


class ArchitectureTests(unittest.TestCase):
    def test_R1_no_embedded_business_policy_or_dynamic_execution(self):
        config=json.loads((BACKEND/'config/audit_rules.json').read_text())
        protected=set(config['labels'])
        protected.update(rule['id'] for rule in config['rules'])
        protected.update(rule[key] for rule in config['rules'] for key in ('message','guidance'))
        for module,path in modules().items():
            tree=ast.parse(path.read_text())
            strings={node.value for node in ast.walk(tree) if isinstance(node,ast.Constant) and isinstance(node.value,str)}
            self.assertFalse(strings & protected,module)
            for node in ast.walk(tree):
                if isinstance(node,ast.Call):
                    called=node.func.id if isinstance(node.func,ast.Name) else getattr(node.func,'attr','')
                    self.assertNotIn(called,{'eval','exec','__import__','import_module','run_module','run_path'},module)

    def test_R2_no_flat_business_modules(self):
        self.assertEqual(list(SOURCE.glob('*.py')),[])
        self.assertEqual([p.name for p in PACKAGE.glob('*.py')],['__init__.py'])
        self.assertEqual((PACKAGE/'__init__.py').read_text(),'')
        for path in PACKAGE.rglob('__init__.py'):self.assertEqual(path.read_text(),'')

    def test_R3_all_imports_acyclic_and_public_boundaries(self):
        found=modules()
        graph={module:set() for module in found}
        for module,path in found.items():
            for dependency in imports(ast.parse(path.read_text())):
                if dependency in found:graph[module].add(dependency)
                if not dependency.startswith('evidence_check.'):continue
                owner=module.split('.')[1:3]
                target=dependency.split('.')[1:3]
                if owner[0]=='domains':
                    self.assertTrue(target[0]=='contracts' or target==owner,(module,dependency))
                elif target[0]=='domains':
                    self.assertTrue(dependency.endswith('.api'),(module,dependency))
                if owner[0]=='application':
                    self.assertNotIn(target[0],{'infrastructure','entrypoints'},(module,dependency))
        cycles(graph)
        declared=json.loads((ROOT/'docs/constraint-ontology.json').read_text())['dependency_dag']
        cycles(declared)

    def test_R4_contracts_and_common_have_no_business_imports(self):
        for module,path in modules().items():
            if module.split('.')[1] not in {'common','contracts'}:continue
            for dependency in imports(ast.parse(path.read_text())):
                if dependency.startswith('evidence_check.'):
                    self.assertIn(dependency.split('.')[1],{'contracts','common'},(module,dependency))

    def test_domains_and_application_are_free_of_io(self):
        blocked={'pathlib','os','sys','socket','requests','httpx','fastapi','docx','sqlite3','sqlalchemy','datetime','time','logging'}
        for module,path in modules().items():
            if module.split('.')[1] not in {'domains','application'}:continue
            tree=ast.parse(path.read_text())
            for dependency in imports(tree):self.assertNotIn(dependency.split('.')[0],blocked,module)
            for node in ast.walk(tree):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):self.assertNotEqual(node.func.id,'open',module)

    def test_uploaded_annotation_material_is_unmodified(self):
        schema=json.loads((ROOT/'evaluation/annotation-schema.json').read_text())
        configured=json.loads((BACKEND/'config/audit_rules.json').read_text())
        self.assertEqual(set(configured['labels']),set(schema['properties']['final_label']['enum']))
        self.assertEqual({r['id'] for r in configured['rules']},set(schema['properties']['rule_ids']['items']['enum']))
        templates=[json.loads(line) for line in (ROOT/'evaluation/annotation-template.jsonl').read_text().splitlines()]
        self.assertTrue(all(item['annotation_status']=='pending' for item in templates))
        self.assertFalse(json.loads((BACKEND/'config/acceptance.json').read_text())['gold_data_available'])
