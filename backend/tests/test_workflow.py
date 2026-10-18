import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from docx import Document
import httpx
from evidence_check.application.api import audit_document
from evidence_check.contracts.errors import DocumentReadError, InputError
from evidence_check.entrypoints.web import create_app
from evidence_check.infrastructure.api import read_document, render_markdown
from support import BACKEND, document, policy


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.policy=policy()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_markdown_docx_equivalent_and_originals_unchanged(self):
        text='Synthetic[1].\nAnother[2].'
        markdown=self.root/'chapter.md';markdown.write_text(text)
        docx_path=self.root/'chapter.docx'
        word=Document()
        for paragraph in text.split('\n'):word.add_paragraph(paragraph)
        word.save(docx_path)
        before={path:path.read_bytes() for path in (markdown,docx_path)}
        for path in (markdown,docx_path):
            normalized=read_document(path,self.policy)
            self.assertEqual(normalized,text)
            report=audit_document(document(normalized),self.policy)
            self.assertEqual([f.rule_id for f in report.findings],['unresolved_reference','source_unavailable'])
            self.assertEqual(path.read_bytes(),before[path])

    def test_io_errors_and_unsupported_format(self):
        with self.assertLogs(level='ERROR'),self.assertRaises(DocumentReadError):
            read_document(self.root/'missing.md',self.policy)
        broken=self.root/'broken.docx';broken.write_text('not zip')
        with self.assertLogs(level='ERROR'),self.assertRaises(DocumentReadError):read_document(broken,self.policy)
        invalid=self.root/'bad.md';invalid.write_bytes(b'\xff')
        with self.assertLogs(level='ERROR'),self.assertRaises(DocumentReadError):read_document(invalid,self.policy)
        other=self.root/'file.pdf';other.write_bytes(b'%PDF')
        with self.assertRaises(InputError) as caught:read_document(other,self.policy)
        self.assertEqual(caught.exception.code,'unsupported_format')

    def test_archive_expansion_limit(self):
        from zipfile import ZipFile, ZIP_DEFLATED
        path=self.root/'large.docx'
        with ZipFile(path,'w',ZIP_DEFLATED) as archive:archive.writestr('oversize','x'*8388609)
        with self.assertRaises(InputError) as caught:read_document(path,self.policy)
        self.assertEqual(caught.exception.code,'archive_too_large')

    def test_markdown_report_escapes_user_html(self):
        text='<script>alert(1)</script> Synthetic[1].'
        rendered=render_markdown(audit_document(document(text),self.policy))
        self.assertNotIn('<script>',rendered)
        for expected in ['source\\_unavailable','Paragraph 0','References: 1','需复核']:
            self.assertIn(expected,rendered)

    def run_cli(self,context,input_text='Synthetic[1,9].',output_format='json'):
        manuscript=self.root/'chapter.md';manuscript.write_text(input_text)
        context_path=self.root/'context.json';context_path.write_text(json.dumps(context))
        return subprocess.run([sys.executable,'-m','evidence_check.entrypoints.cli',
            '--input',str(manuscript),'--context',str(context_path),'--config-dir',str(BACKEND/'config'),
            '--format',output_format],capture_output=True,text=True,cwd=BACKEND,
            env={**os.environ,'PYTHONPATH':str(BACKEND/'src')},check=False)

    def test_cli_success_error_and_markdown(self):
        context=document().model_dump(mode='json');context.pop('text')
        result=self.run_cli(context)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(len(json.loads(result.stdout)['findings']),2)
        markdown=self.run_cli(context,output_format='markdown')
        self.assertEqual(markdown.returncode,0,markdown.stderr)
        self.assertIn('Evidence Check',markdown.stdout)
        for bad in [context|{'authorized':False},context|{'authorized':'yes'},context|{'text':'forbidden'}]:
            result=self.run_cli(bad)
            self.assertEqual(result.returncode,1)
            self.assertEqual(result.stdout,'')
            self.assertIn('error',json.loads(result.stderr.splitlines()[-1]))

    def test_api_functional_and_error_requests(self):
        app=create_app(BACKEND/'config')
        async def requests():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                self.assertEqual((await client.get('/health')).json(),{'status':'ok'})
                body=document('Synthetic[1,9].').model_dump(mode='json')
                response=await client.post('/audits',json=body)
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(len(response.json()['findings']),2)
                for changes in [{'authorized':False},{'authorized':'yes'},{'unexpected':'secret'},
                                {'text':'Patient name: PRIVATE_NAME'},{'references':[{'reference_id':'1','title':'X'}]}]:
                    response=await client.post('/audits',json=body|changes)
                    self.assertEqual(response.status_code,422,response.text)
                    self.assertNotIn('PRIVATE_NAME',response.text)
                    self.assertNotIn('secret',response.text)
        asyncio.run(requests())
