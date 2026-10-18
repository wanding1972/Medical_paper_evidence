"""Document public API. No file, network, database or clock access."""
import re
from evidence_check.contracts.models import DocumentInput, DocumentBundle, DocumentFacts
from evidence_check.contracts.policy import Policy
from evidence_check.contracts.predicates import enforce
from evidence_check.domains.document.parser import parse_sentences


def parse_document(document: DocumentInput, policy: Policy) -> DocumentBundle:
    ids = tuple(reference.reference_id for reference in document.references)
    syntax = policy.parsing
    facts = DocumentFacts(
        authorized=document.authorized, single_section=document.single_section,
        language_mode=document.language_mode, text_length=len(document.text.strip()),
        chinese_chars=len(re.findall(syntax.chinese_pattern, document.text)),
        english_words=len(re.findall(syntax.english_word_pattern, document.text)),
        reference_count=len(ids), duplicate_reference_count=len(ids) - len(set(ids)),
        minimum_reference_id=min(ids) if ids else None,
        empty_title_count=sum(not reference.title.strip() for reference in document.references),
        heading_count=len(re.findall(syntax.heading_pattern, document.text, re.MULTILINE)),
        pii_match_count=sum(len(re.findall(pattern, text, re.IGNORECASE))
            for text in (document.text, *(reference.title for reference in document.references))
            for pattern in syntax.pii_patterns),
    )
    enforce(policy.limits.document_gates, facts)
    return DocumentBundle(document_id=document.document_id, text=document.text,
                          sentences=parse_sentences(document.text, policy), references=document.references)
