"""Product HTTP composition root. Single-user durable local deployment."""
import argparse
import asyncio
import base64
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from html import escape
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
import tempfile
import time
from urllib.parse import urlsplit
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.formparsers import MultiPartParser, MultiPartException
from pydantic import BaseModel, ConfigDict, ValidationError
from evidence_check.application.product import run_audit
from evidence_check.contracts.errors import EvidenceCheckError, InputError, TaskStepError
from evidence_check.contracts.models import ClaimCandidate, DocumentInput, Reference
from evidence_check.contracts.product import ProductRequest, ProductReport, Observation, SubmissionHeader, ModelAdmissionFacts
from evidence_check.contracts.predicates import enforce
from evidence_check.infrastructure.api import load_policy, load_product_policy, read_uploaded_document
from evidence_check.infrastructure.pdf import parse_pdf
from evidence_check.infrastructure.model import StructuredModel
from evidence_check.infrastructure.runtime import Runtime
from evidence_check.infrastructure.store import TaskStore
from evidence_check.infrastructure.worker import Worker

_LOG=logging.getLogger(__name__)


class Binding(BaseModel):
    model_config=ConfigDict(strict=True,extra='forbid')
    reference_id: int
    file_index: int


class Submission(BaseModel):
    model_config=ConfigDict(strict=True,extra='forbid')
    document_id: str
    references: list[Reference]
    bindings: list[Binding]=[]
    claims: list[ClaimCandidate]=[]
    language_mode: str
    authorized: bool
    single_section: bool
    auto_candidates: bool=True
    model_consent: bool=False


class ObservationInput(BaseModel):
    model_config=ConfigDict(strict=True,extra='forbid')
    claim_start: int
    evidence_ids: list[str]
    support_relation: str
    scope_relation: str
    causal_relation: str
    direction_relation: str
    numeric_relation: str
    rationale: str
    origin: str


class Review(BaseModel):
    model_config=ConfigDict(strict=True,extra='forbid')
    claims: list[ClaimCandidate]
    observations: list[ObservationInput]


@contextmanager
def _stage(diagnostics,name):
    started=time.monotonic()
    diagnostics['active_step']=name
    try:yield
    finally:diagnostics['steps'].append({'step':name,'seconds':time.monotonic()-started})


def _execute(payload,legacy,policy,cancelled=None):
    started=time.monotonic()
    diagnostics={'steps':[],'policy_version':policy.version,'prompt_version':policy.model.prompt_version,
        'input_sha256':sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest(),
        'policy_sha256':sha256((legacy.model_dump_json()+policy.model_dump_json()).encode()).hexdigest()}
    try:
        result=_run_task(payload,legacy,policy,cancelled,diagnostics)
        diagnostics['total_seconds']=time.monotonic()-started
        result['diagnostics']=diagnostics
        return result
    except EvidenceCheckError as error:
        diagnostics['total_seconds']=time.monotonic()-started
        raise TaskStepError(error.code,error.message,diagnostics) from error
    except Exception as error:
        diagnostics['total_seconds']=time.monotonic()-started
        raise TaskStepError('task_internal_error','Task execution failed.',diagnostics) from error


def _run_task(payload,legacy,policy,cancelled,diagnostics):
    deadline=time.monotonic()+legacy.acceptance.task_seconds_max
    def remaining():
        if cancelled is not None and cancelled.is_set():raise EvidenceCheckError('task_interrupted','Task will resume after restart.')
        budget=deadline-time.monotonic()
        if budget<=0:raise EvidenceCheckError('task_timeout','Task exceeded its configured execution budget.')
        return budget
    with _stage(diagnostics,'document'):
        manuscript=payload['manuscript']
        text=read_uploaded_document(base64.b64decode(manuscript['data'],validate=True),manuscript['suffix'],legacy)
        context=Submission.model_validate_json(json.dumps(payload['context']))
        document=DocumentInput(document_id=context.document_id,text=text,references=tuple(context.references),
            claims=tuple(context.claims),language_mode=context.language_mode,authorized=context.authorized,single_section=context.single_section)
        from evidence_check.domains.document.api import parse_document
        parse_document(document,legacy)
    with _stage(diagnostics,'sources'):
        sources=tuple(parse_pdf(base64.b64decode(source['data'],validate=True),source['reference_id'],source['source_file_id'],legacy,policy,remaining)
                      for source in payload['sources'])
    with _stage(diagnostics,'audit'):
        model=StructuredModel(policy,remaining) if context.model_consent else None
        diagnostics['model_name']=model.name if model else None
        diagnostics['model_responses']=model.responses if model else []
        observations=tuple(Observation.model_validate_json(json.dumps(o)) for o in payload.get('observations',[]))
        report=run_audit(ProductRequest(document=document,sources=sources,observations=observations,
            auto_candidates=context.auto_candidates,model_consent=context.model_consent),legacy,policy,model)
        remaining()
    return {'report':report.model_dump(mode='json'),'model_responses':model.responses if model else []}


def _markdown(report):
    lines=['# Evidence Check','',report.audit_scope,'',report.disclaimer,'',f'Input SHA256: {report.input_sha256}',f'Policy SHA256: {report.policy_sha256}','']
    for item in report.assessments:
        lines.extend([f'## {escape(item.predicted_label)} · {escape(item.review_status)}',
            f'Chars [{item.claim.location.char_start}, {item.claim.location.char_end})',
            '    '+item.claim.text.replace('\n','\n    '),''])
        for finding in item.findings:lines.extend([escape(finding.rule_id)+' / '+escape(finding.severity),escape(finding.message),escape(finding.guidance),''])
        for span in item.evidence:lines.extend([f'Reference {span.reference_id}, page {span.page}, paragraph {span.paragraph}',
            '    '+span.text.replace('\n','\n    '),''])
    return '\n'.join(lines)


async def _upload(file,limit):
    data=await file.read(limit+1)
    if len(data)>limit:raise HTTPException(413,'File exceeds configured size limit.')
    return data


@asynccontextmanager
async def _memory_form(request,policy):
    parser=MultiPartParser(request.headers,request.stream(),max_files=policy.limits.file_count,
        max_fields=1,max_part_size=policy.limits.max_context_chars)
    parser.spool_max_size=policy.limits.request_bytes
    try:
        form=await parser.parse()
    except MultiPartException as error:
        raise HTTPException(422,'Invalid multipart submission.') from error
    try:yield form
    finally:await form.close()


def create_product_app(config_dir: Path,data_dir: Path,start_worker=True):
    legacy=load_policy(config_dir);policy=load_product_policy(config_dir)
    rule_ids={r.id for r in legacy.audit.rules}
    if any(t.rule_id not in rule_ids for t in policy.rule_triggers):raise InputError('product_policy_invalid','Unknown audit rule binding.')
    if any(row.label not in legacy.audit.labels for row in policy.decisions):raise InputError('product_policy_invalid','Unknown decision label.')
    runtime=Runtime(data_dir);store=TaskStore(data_dir,runtime.key,policy)
    worker=Worker(store,lambda payload:_execute(payload,legacy,policy,worker.stop_event))

    @asynccontextmanager
    async def lifespan(app):
        if start_worker:worker.start()
        try:yield
        finally:
            if start_worker:await asyncio.to_thread(worker.stop)

    app=FastAPI(title=policy.title,lifespan=lifespan)
    app.state.store=store;app.state.worker=worker;app.state.runtime=runtime

    @app.middleware('http')
    async def guard(request,call_next):
        if request.method in ('POST','DELETE','PUT','PATCH'):
            origin=request.headers.get('origin')
            if request.headers.get('x-evidence-request')!='1' or (origin and urlsplit(origin).netloc!=request.headers.get('host')):
                return JSONResponse({'error':{'code':'origin_rejected'}},status_code=403)
        if request.url.path.startswith('/api/') and request.url.path not in ('/api/config','/api/session'):
            if not runtime.authenticate(request.cookies.get(policy.auth.cookie_name,''),time.time()):
                return JSONResponse({'error':{'code':'authentication_required'}},status_code=401)
        size=0;chunks=[]
        async for chunk in request.stream():
            size+=len(chunk)
            if size>policy.limits.request_bytes:return JSONResponse({'error':{'code':'request_too_large'}},status_code=413)
            chunks.append(chunk)
        request._body=b''.join(chunks)
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        return response

    @app.exception_handler(EvidenceCheckError)
    async def known_error(request,error):
        _LOG.warning('request_failed code=%s',error.code)
        return JSONResponse({'error':{'code':error.code,'message':error.message}},status_code=422)

    @app.exception_handler(RequestValidationError)
    async def invalid_error(request,error):
        return JSONResponse({'error':{'code':'invalid_input','message':'Request does not match the input contract.'}},status_code=422)

    def task(task_id,with_payload=False):
        data=store.get(task_id,runtime.owner,time.time(),with_payload)
        if data is None:raise HTTPException(404,'Task does not exist or has expired.')
        return data

    @app.get('/api/config')
    def config():
        names=(policy.model.endpoint_env,policy.model.key_env,policy.model.name_env)
        return {'title':policy.title,'subtitle':policy.subtitle,'disclaimer':policy.disclaimer,'audit_scope':policy.audit_scope,
            'candidate_notice':policy.candidate_notice,'languages':legacy.acceptance.language_modes,
            'unknown_relation':policy.unknown_relation,
            'relations':policy.relations,'origins':policy.origins,'states':policy.lifecycle,'ui':policy.ui,
            'limits':policy.limits,'retention_hours':policy.lifecycle.retention_hours,
            'model_available':policy.model.enabled and all(bool(os.environ.get(name)) for name in names),'feedback_states':policy.feedback_states}

    @app.get('/api/session')
    def session(request: Request):return {'authenticated':runtime.authenticate(request.cookies.get(policy.auth.cookie_name,''),time.time())}

    @app.post('/api/session')
    async def login(request: Request):
        try:
            data=await request.json()
            if not isinstance(data,dict) or set(data)!={'password'} or not isinstance(data['password'],str):raise ValueError()
        except ValueError:raise HTTPException(422,'Invalid session request.')
        token=runtime.login(data['password'],time.time(),policy.auth.session_hours)
        if token is None:
            await asyncio.sleep(policy.auth.failed_login_delay_seconds)
            raise HTTPException(401,'Invalid access password.')
        response=JSONResponse({'authenticated':True})
        response.set_cookie(policy.auth.cookie_name,token,httponly=True,samesite='strict',secure=request.url.scheme=='https',max_age=policy.auth.session_hours*3600)
        return response

    @app.delete('/api/session')
    def logout():
        response=JSONResponse({'authenticated':False});response.delete_cookie(policy.auth.cookie_name);return response

    @app.get('/api/tasks')
    def list_tasks():return store.list(runtime.owner,time.time())

    @app.post('/api/tasks',status_code=202)
    async def create_task(request: Request):
        async with _memory_form(request,policy) as form:
            try:
                raw=form.get('context','')
                if not isinstance(raw,str) or len(raw)>policy.limits.max_context_chars:raise ValueError()
                context=Submission.model_validate_json(raw)
            except (ValueError,ValidationError):raise HTTPException(422,'Invalid submission context.')
            header=SubmissionHeader(authorized=context.authorized,single_section=context.single_section)
            header_gates=tuple(g for g in legacy.limits.document_gates if all(c.field in type(header).model_fields for c in g.when))
            enforce(header_gates,header)
            enforce(policy.model_gates,ModelAdmissionFacts(requested=context.model_consent,enabled=policy.model.enabled,consent=context.model_consent))
            manuscript=form.get('manuscript');evidence=form.getlist('evidence')
            if manuscript is None or not hasattr(manuscript,'read') or any(not hasattr(f,'read') for f in evidence):raise HTTPException(422,'Manuscript file is required.')
            suffix=Path(manuscript.filename or '').suffix.lower()
            if suffix not in legacy.limits.formats.markdown+legacy.limits.formats.docx:raise HTTPException(422,'Unsupported manuscript format.')
            known={r.reference_id for r in context.references};indices=[b.file_index for b in context.bindings]
            refs=[b.reference_id for b in context.bindings]
            if set(indices)!=set(range(len(evidence))) or len(indices)!=len(set(indices)) or len(refs)!=len(set(refs)) or not set(refs)<=known:
                raise HTTPException(422,'Each PDF must bind once to a distinct listed reference.')
            raw_document=await _upload(manuscript,policy.limits.file_bytes);total=len(raw_document);sources=[]
            for binding in context.bindings:
                file=evidence[binding.file_index]
                if Path(file.filename or '').suffix.lower()!='.pdf':raise HTTPException(422,'Evidence files must be PDF.')
                data=await _upload(file,policy.limits.file_bytes);total+=len(data)
                if total>policy.limits.total_upload_bytes:raise HTTPException(413,'Total upload size exceeded.')
                sources.append({'reference_id':binding.reference_id,'source_file_id':f'{binding.reference_id}-{binding.file_index}',
                    'data':base64.b64encode(data).decode()})
            payload={'context':context.model_dump(mode='json'),'manuscript':{'suffix':suffix,'data':base64.b64encode(raw_document).decode()},'sources':sources}
            task_id=store.create(runtime.owner,payload,time.time())
            return {'task_id':task_id}

    @app.get('/api/tasks/{task_id}')
    def get_task(task_id: str):
        data=task(task_id)
        if data['result']:data['result']={'report':data['result']['report']}
        return data

    @app.delete('/api/tasks/{task_id}')
    def delete_task(task_id: str):
        task(task_id);store.delete(task_id,runtime.owner);_LOG.info('task_deleted');return {'deleted':True}

    @app.get('/api/tasks/{task_id}/report')
    def download(task_id: str,format: str='json'):
        data=task(task_id)
        if data['result'] is None:raise HTTPException(409,'Report is not ready.')
        if format not in policy.format_options:raise HTTPException(422,'Unsupported report format.')
        report=ProductReport.model_validate_json(json.dumps(data['result']['report']))
        content={'json':lambda:report.model_dump_json(indent=2),'markdown':lambda:_markdown(report)}[format]()
        return Response(content,media_type='application/octet-stream',headers={'Content-Disposition':f'attachment; filename="evidence-report.{"json" if format=="json" else "md"}"'})

    @app.get('/api/tasks/{task_id}/source/{reference_id}')
    def source(task_id: str,reference_id: int):
        data=task(task_id,True)
        found=next((s for s in data['payload']['sources'] if s['reference_id']==reference_id),None)
        if found is None:raise HTTPException(404,'No source file.')
        return Response(base64.b64decode(found['data']),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="reference-{reference_id}.pdf"'})

    @app.post('/api/tasks/{task_id}/review',status_code=202)
    def review(task_id: str,body: Review):
        data=task(task_id,True)
        if data['result'] is None:raise HTTPException(409,'Report is not ready.')
        if any(o.origin!=policy.origins.human for o in body.observations):raise HTTPException(422,'Review observations must have human provenance.')
        payload=data['payload'];payload['context']['claims']=[c.model_dump(mode='json') for c in body.claims]
        payload['context']['auto_candidates']=False;payload['context']['model_consent']=False
        payload['observations']=[o.model_dump(mode='json') for o in body.observations]
        payload['parent_task_id']=task_id
        return {'task_id':store.create(runtime.owner,payload,time.time())}

    app.mount('/',StaticFiles(directory=Path(__file__).parent/'assets',html=True),name='ui')
    return app


def main():
    import uvicorn
    parser=argparse.ArgumentParser(description='Evidence Check single-user product server')
    parser.add_argument('--config-dir',type=Path,default=Path('backend/config'))
    parser.add_argument('--data-dir',type=Path,default=Path('.evidence-data'))
    parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    app=create_product_app(args.config_dir,args.data_dir)
    print('Local access password file:',args.data_dir/'access-password',flush=True)
    uvicorn.run(app,host=args.host,port=args.port,access_log=False)


if __name__=='__main__':main()
