"""PDF effects adapter: fulltext only, exact page text, no OCR or external IO."""
from hashlib import sha256
import logging
import re
import pymupdf
from evidence_check.contracts.errors import InputError
from evidence_check.contracts.policy import Policy
from evidence_check.contracts.predicates import matches
from evidence_check.contracts.product import ParagraphFacts, SourceDocument, SourcePage, SourceParagraph
from evidence_check.contracts.product_policy import ProductPolicy

_LOG=logging.getLogger(__name__)


def parse_pdf(data: bytes, reference_id: int, source_file_id: str, legacy: Policy, policy: ProductPolicy, check=None) -> SourceDocument:
    digest=sha256(data).hexdigest()
    try:
        with pymupdf.open(stream=data,filetype='pdf') as pdf:
            if pdf.is_encrypted:return SourceDocument(reference_id=reference_id,source_file_id=source_file_id,sha256=digest,pages=(),error_code='pdf_encrypted')
            if len(pdf)>policy.limits.pdf_pages:return SourceDocument(reference_id=reference_id,source_file_id=source_file_id,sha256=digest,pages=(),error_code='pdf_page_limit')
            pages=[];total=0;excluded_section=False
            for number,page in enumerate(pdf,1):
                if check is not None:check()
                blocks=[b for b in page.get_text('blocks',sort=True) if b[6]==0]
                tables=page.find_tables().tables
                text='';parts=[]
                for index,block in enumerate(blocks):
                    raw=block[4];start=len(text);text+=raw+'\n'
                    if re.match(policy.retrieval.excluded_section_pattern,raw.strip(),re.IGNORECASE):excluded_section=True
                    if re.match(policy.retrieval.body_section_pattern,raw.strip(),re.IGNORECASE):excluded_section=False
                    box=pymupdf.Rect(block[:4])
                    facts=ParagraphFacts(table_overlap_count=sum(box.intersects(pymupdf.Rect(t.bbox)) for t in tables),abstract=excluded_section)
                    excluded=any(matches(g.when,facts) for g in policy.retrieval.paragraph_gates)
                    if raw.strip():parts.append(SourceParagraph(paragraph=index,start=start,end=start+len(raw),excluded=excluded))
                for pattern in legacy.parsing.pii_patterns:
                    if re.search(pattern,text,re.IGNORECASE):raise InputError('patient_data_detected','Potential patient data detected; processing stopped.')
                total+=len(text)
                if total>policy.limits.pdf_text_chars:return SourceDocument(reference_id=reference_id,source_file_id=source_file_id,sha256=digest,pages=(),error_code='pdf_text_limit')
                pages.append(SourcePage(page=number,text=text,paragraphs=tuple(parts)))
            readable=any(p.text.strip() for p in pages)
            return SourceDocument(reference_id=reference_id,source_file_id=source_file_id,sha256=digest,pages=tuple(pages),error_code=None if readable else 'pdf_no_text')
    except (pymupdf.FileDataError,pymupdf.EmptyFileError,RuntimeError,ValueError) as error:
        _LOG.warning('pdf_parse_failed')
        return SourceDocument(reference_id=reference_id,source_file_id=source_file_id,sha256=digest,pages=(),error_code='pdf_unreadable')
