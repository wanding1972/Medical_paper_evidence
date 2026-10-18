"""Pure cited-only BM25 retrieval with original page span verification."""
from collections import Counter
from hashlib import sha256
import math
import re
from evidence_check.contracts.errors import InputError
from evidence_check.contracts.models import ClaimRecord
from evidence_check.contracts.product import SourceDocument, EvidenceSpan
from evidence_check.contracts.product_policy import ProductPolicy


def _tokens(text: str, policy: ProductPolicy) -> tuple[str, ...]:
    tokens=list(re.findall(policy.retrieval.token_pattern,text.lower()))
    for synonym in policy.retrieval.synonyms:
        if synonym.term in text.lower():
            tokens.extend(synonym.alternatives)
    return tuple(tokens)


def validate_sources(sources: tuple[SourceDocument, ...]) -> None:
    if len({s.reference_id for s in sources}) != len(sources):
        raise InputError('duplicate_source','Each reference can bind only one uploaded fulltext.')
    for source in sources:
        if len({p.page for p in source.pages}) != len(source.pages):raise InputError('invalid_source','Duplicate source page.')
        for page in source.pages:
            if page.page <= 0:raise InputError('invalid_source','Page index must be positive.')
            for part in page.paragraphs:
                if not 0 <= part.start < part.end <= len(page.text):raise InputError('invalid_source','Invalid page span.')


def retrieve(claim: ClaimRecord, sources: tuple[SourceDocument, ...], policy: ProductPolicy) -> tuple[EvidenceSpan, ...]:
    paragraphs=[]
    for source in sources:
        if source.reference_id not in claim.citation_ids or source.error_code is not None:continue
        for page in source.pages:
            for part in page.paragraphs:
                text=page.text[part.start:part.end]
                if part.excluded or len(text.strip()) < policy.retrieval.min_paragraph_chars:continue
                paragraphs.append((source,page,part,text,Counter(_tokens(text,policy))))
    if not paragraphs:return ()
    query=set(_tokens(claim.text,policy));n=len(paragraphs)
    document_frequency=Counter(token for row in paragraphs for token in row[4])
    average=sum(sum(row[4].values()) for row in paragraphs)/n
    scored=[]
    for source,page,part,text,counts in paragraphs:
        size=sum(counts.values());score=0.0
        for token in query:
            frequency=counts[token]
            if not frequency:continue
            df=document_frequency[token]
            idf=math.log(1+(n-df+0.5)/(df+0.5))
            k1=policy.retrieval.k1;b=policy.retrieval.b
            score+=idf*frequency*(k1+1)/(frequency+k1*(1-b+b*size/(average or 1)))
        if score <= policy.retrieval.minimum_score:continue
        identity=f'{source.sha256}:{source.source_file_id}:{page.page}:{part.start}:{part.end}'
        scored.append(EvidenceSpan(span_id=sha256(identity.encode()).hexdigest(),reference_id=source.reference_id,
            source_file_id=source.source_file_id,page=page.page,paragraph=part.paragraph,
            start=part.start,end=part.end,text=text,score=score))
    return tuple(sorted(scored,key=lambda s:(-s.score,s.reference_id,s.page,s.start))[:policy.retrieval.top_k])
