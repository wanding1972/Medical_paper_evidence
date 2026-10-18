"""Synthetic fixtures only; these are not medical gold annotations."""
from pathlib import Path
from evidence_check.contracts.models import DocumentInput, Reference
from evidence_check.infrastructure.api import load_policy

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent


def policy():
    return load_policy(BACKEND / 'config')


def document(text='Synthetic assertion[1].', **changes):
    values = dict(document_id='synthetic',text=text,
        references=(Reference(reference_id=1,title='Synthetic source'),), claims=(),
        language_mode='en-en',authorized=True,single_section=True)
    return DocumentInput(**(values | changes))
