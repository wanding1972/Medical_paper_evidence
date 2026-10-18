import asyncio
import base64
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from cryptography.fernet import Fernet
import httpx
from evidence_check.contracts.errors import EvidenceCheckError
from evidence_check.entrypoints.server import create_product_app, _execute
from evidence_check.infrastructure.api import load_policy, load_product_policy
from evidence_check.infrastructure.runtime import Runtime
from evidence_check.infrastructure.store import TaskStore
from evidence_check.infrastructure.worker import Worker
from support import BACKEND
from test_product import pdf_bytes,product_policy


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)/'data';self.policy=product_policy()
        self.store=TaskStore(self.directory,Fernet.generate_key(),self.policy)

    def test_ciphertext_ownership_and_no_retention_leak(self):
        task_id=self.store.create('owner',{'text':'PRIVATE_PAPER_MARKER'},100)
        self.assertIsNone(self.store.get(task_id,'another',101))
        self.assertNotIn(b'PRIVATE_PAPER_MARKER',self.store.path.read_bytes())
        self.assertEqual(self.store.get(task_id,'owner',101,True)['payload']['text'],'PRIVATE_PAPER_MARKER')
        self.assertIsNone(self.store.get(task_id,'owner',100+self.policy.lifecycle.retention_hours*3600))
        self.assertEqual(self.store.expire(100+self.policy.lifecycle.retention_hours*3600),1)

    def test_recovery_and_deleted_running_job_never_reappears(self):
        task_id=self.store.create('owner',{'x':1},100)
        self.assertEqual(self.store.acquire(101)[0],task_id)
        self.store.recover();self.assertEqual(self.store.acquire(102)[0],task_id)
        self.store.delete(task_id,'owner');self.store.finish(task_id,{'text':'result'})
        self.assertIsNone(self.store.get(task_id,'owner',103))

    def test_exhausted_restart_is_failed(self):
        task_id=self.store.create('owner',{},100)
        for _ in range(self.policy.lifecycle.retry_limit):self.store.acquire(101);self.store.recover()
        task=self.store.get(task_id,'owner',102)
        self.assertEqual(task['status'],self.policy.lifecycle.failed)
        self.assertEqual(task['error'],'restart_retry_exhausted')

    def test_second_worker_is_rejected(self):
        first=Worker(self.store,lambda p:p);second=Worker(self.store,lambda p:p)
        first.start()
        try:
            with self.assertRaises(EvidenceCheckError):second.start()
        finally:first.stop()

    def test_wrong_data_key_is_reported(self):
        runtime=Runtime(self.directory)
        with patch.dict('os.environ',{'EVIDENCE_DATA_KEY':Fernet.generate_key().decode()}),self.assertRaises(EvidenceCheckError):Runtime(self.directory)
        if os.name=='posix':self.assertEqual((self.directory/'access-password').stat().st_mode&0o777,0o600)

    def test_worker_error_is_not_semantic_result(self):
        def fail(payload):raise EvidenceCheckError('test_effect_failed','effect failed')
        now=time.time();task_id=self.store.create('owner',{},now);worker=Worker(self.store,fail);worker.start()
        try:
            for _ in range(100):
                task=self.store.get(task_id,'owner',time.time())
                if task['status']==self.policy.lifecycle.failed:break
                time.sleep(.01)
            self.assertEqual(task['error'],'test_effect_failed');self.assertIsNone(task['result'])
        finally:worker.stop()

    def test_api_upload_review_download_delete_and_access_guards(self):
        app=create_product_app(BACKEND/'config',self.directory/'api')
        async def run():
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://local') as client:
                    self.assertEqual((await client.get('/api/tasks')).status_code,401)
                    self.assertEqual((await client.post('/api/session',json={'password':'wrong'})).status_code,403)
                    h={'X-Evidence-Request':'1'}
                    login=await client.post('/api/session',json={'password':app.state.runtime.password.decode()},headers=h)
                    self.assertEqual(login.status_code,200,login.text)
                    self.assertIn('HttpOnly',login.headers['set-cookie'])
                    context={'document_id':'Synthetic task','references':[{'reference_id':1,'title':'Synthetic source'}],
                        'bindings':[{'reference_id':1,'file_index':0}],'claims':[],'language_mode':'en-en','authorized':True,'single_section':True}
                    response=await client.post('/api/tasks',headers=h,data={'context':json.dumps(context)},files=[
                        ('manuscript',('chapter.md',b'Synthetic treatment reduced risk[1].','text/markdown')),
                        ('evidence',('source.pdf',pdf_bytes(),'application/pdf'))])
                    self.assertEqual(response.status_code,202,response.text);task_id=response.json()['task_id']
                    async def ready(identifier):
                        for _ in range(150):
                            result=await client.get('/api/tasks/'+identifier);data=result.json()
                            if data['status'] in (self.policy.lifecycle.done,self.policy.lifecycle.failed):return data
                            await asyncio.sleep(.02)
                        self.fail('Worker did not finish')
                    task=await ready(task_id)
                    self.assertEqual(task['status'],self.policy.lifecycle.done,task)
                    report=task['result']['report'];item=report['assessments'][0]
                    self.assertTrue(item['evidence']);self.assertNotIn('model_responses',task['result'])
                    downloaded=await client.get(f'/api/tasks/{task_id}/report?format=markdown')
                    self.assertEqual(downloaded.status_code,200);self.assertIn('Evidence Check',downloaded.text)
                    source=await client.get(f'/api/tasks/{task_id}/source/1');self.assertTrue(source.content.startswith(b'%PDF'))
                    from test_product import observation
                    from evidence_check.contracts.product import ClaimAssessment
                    parsed=ClaimAssessment.model_validate_json(json.dumps(item))
                    review={'claims':[{'start':parsed.claim.location.char_start,'end':parsed.claim.location.char_end,'text':parsed.claim.text}],
                        'observations':[observation(parsed).model_dump(mode='json')]}
                    reviewed=await client.post(f'/api/tasks/{task_id}/review',json=review,headers=h)
                    self.assertEqual(reviewed.status_code,202,reviewed.text)
                    rerun=await ready(reviewed.json()['task_id'])
                    self.assertEqual(rerun['result']['report']['assessments'][0]['predicted_label'],'supported')
                    self.assertEqual((await client.get('/api/tasks/'+task_id)).json()['result']['report']['assessments'][0]['predicted_label'],'unverified')
                    blocked=await client.delete('/api/tasks/'+task_id,headers=h|{'Origin':'https://evil.example'})
                    self.assertEqual(blocked.status_code,403)
                    self.assertEqual((await client.delete('/api/tasks/'+task_id,headers=h)).status_code,200)
                    self.assertEqual((await client.get('/api/tasks/'+task_id)).status_code,404)
                    home=await client.get('/');self.assertEqual(home.status_code,200);self.assertIn('Content-Security-Policy',home.headers)
        asyncio.run(run())

    def test_api_rejects_bad_binding_and_invalid_context(self):
        app=create_product_app(BACKEND/'config',self.directory/'api-bad',False)
        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://local') as client:
                h={'X-Evidence-Request':'1'}
                await client.post('/api/session',headers=h,json={'password':app.state.runtime.password.decode()})
                response=await client.post('/api/tasks',headers=h,data={'context':'{"authorized":true}'},files={'manuscript':('x.md',b'x')})
                self.assertEqual(response.status_code,422)
                self.assertNotIn('input',response.text)
        asyncio.run(run())

    def test_multipart_files_do_not_roll_to_plaintext_disk(self):
        from evidence_check.entrypoints.server import _memory_form
        from starlette.requests import Request
        boundary='test-multipart-boundary'
        raw=(f'--{boundary}\r\nContent-Disposition: form-data; name="evidence"; filename="test.pdf"\r\nContent-Type: application/pdf\r\n\r\n'.encode()
             +b'x'*(1024*1024+1)+f'\r\n--{boundary}--\r\n'.encode())
        delivered=False
        async def receive():
            nonlocal delivered
            if delivered:return {'type':'http.request','body':b'','more_body':False}
            delivered=True;return {'type':'http.request','body':raw,'more_body':False}
        request=Request({'type':'http','method':'POST','path':'/','headers':[(b'content-type',f'multipart/form-data; boundary={boundary}'.encode())]},receive)
        async def check():
            async with _memory_form(request,self.policy) as form:
                self.assertFalse(form['evidence'].file._rolled)
        asyncio.run(check())

    def test_failure_diagnostics_are_encrypted_and_not_public_report(self):
        task_id=self.store.create('owner',{},100);self.store.acquire(101)
        self.store.fail(task_id,'model_step_failed',{'steps':[{'step':'audit','seconds':.1}],'model_responses':['PRIVATE_STEP_MARKER']})
        self.assertNotIn(b'PRIVATE_STEP_MARKER',self.store.path.read_bytes())
        data=self.store.get(task_id,'owner',102)
        self.assertIsNone(data['result']);self.assertNotIn('diagnostics',data)
        with self.store.connection() as db:
            raw=db.execute('SELECT diagnostics FROM tasks WHERE id=?',(task_id,)).fetchone()[0]
        self.assertEqual(self.store._decode(raw)['steps'][0]['step'],'audit')

    def test_worker_stop_from_other_thread_releases_lock(self):
        first=Worker(self.store,lambda p:p);first.start()
        asyncio.run(asyncio.to_thread(first.stop))
        second=Worker(self.store,lambda p:p)
        try:second.start()
        finally:second.stop()

    def test_recovery_failure_releases_worker_lock(self):
        first=Worker(self.store,lambda p:p)
        with patch.object(self.store,'recover',side_effect=EvidenceCheckError('storage_failed','test')):
            with self.assertRaises(EvidenceCheckError):first.start()
        second=Worker(self.store,lambda p:p)
        try:second.start()
        finally:second.stop()

    def test_lock_io_failure_has_stable_error(self):
        worker=Worker(self.store,lambda p:p)
        with patch('evidence_check.infrastructure.worker.FileLock') as lock:
            lock.return_value.acquire.side_effect=PermissionError('test')
            with self.assertLogs(level='ERROR'),self.assertRaises(EvidenceCheckError) as caught:worker.start()
        self.assertEqual(caught.exception.code,'worker_lock_failed')
