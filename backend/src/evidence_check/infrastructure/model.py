"""Optional HTTPS structured model effects; document instructions are untrusted."""
import json
import logging
import os
from urllib.parse import urlsplit
import httpx
from pydantic import ValidationError
from evidence_check.contracts.errors import EvidenceCheckError
from evidence_check.contracts.product import CandidateBatch, ObservationBatch
from evidence_check.contracts.product_policy import ProductPolicy

_LOG=logging.getLogger(__name__)


def _strict_schema(value):
    if isinstance(value,list):return [_strict_schema(item) for item in value]
    if not isinstance(value,dict):return value
    result={key:_strict_schema(item) for key,item in value.items() if key!='default'}
    if result.get('type')=='object':
        result['additionalProperties']=False
        result['required']=list(result.get('properties',{}))
    return result


class StructuredModel:
    def __init__(self,policy: ProductPolicy,remaining=None):
        self.policy=policy
        self.url=os.environ.get(policy.model.endpoint_env,'')
        self.key=os.environ.get(policy.model.key_env,'')
        self.name=os.environ.get(policy.model.name_env,'')
        parsed=urlsplit(self.url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise EvidenceCheckError('model_configuration','Model endpoint must be a configured HTTPS URL.')
        if not self.key or not self.name:raise EvidenceCheckError('model_configuration','Model key and model name are required.')
        self.responses=[]
        self.remaining=remaining

    def _request(self,system,payload,schema):
        try:
            timeout=min(self.policy.model.timeout_seconds,self.remaining()) if self.remaining else self.policy.model.timeout_seconds
            response=httpx.post(self.url,headers={'Authorization':'Bearer '+self.key},json={
                'model':self.name,'temperature':self.policy.model.temperature,'max_tokens':self.policy.model.max_response_tokens,
                'messages':[{'role':'system','content':system},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}],
                'response_format':{'type':'json_schema','json_schema':{'name':schema.__name__,'schema':_strict_schema(schema.model_json_schema()),'strict':True}}},
                timeout=timeout,follow_redirects=False)
            response.raise_for_status()
            raw=response.json()['choices'][0]['message']['content']
            self.responses.append(raw)
            result=schema.model_validate_json(raw)
            return result
        except (httpx.HTTPError,ValueError,KeyError,IndexError,TypeError,ValidationError) as error:
            _LOG.error('model_step_failed')
            raise EvidenceCheckError('model_step_failed','Model request or structured response validation failed.') from error

    def extract(self,document):
        return self._request(self.policy.model.extract_system,document.model_dump(mode='json'),CandidateBatch)

    def compare(self,claim,evidence):
        return self._request(self.policy.model.compare_system,{'claim':claim.model_dump(mode='json'),
            'evidence':[span.model_dump(mode='json') for span in evidence],
            'relations':self.policy.relations.model_dump(mode='json'),'origin':self.policy.origins.model},ObservationBatch)
