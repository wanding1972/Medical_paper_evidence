"""Stateless local API, deliberately not a production upload service."""
import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from evidence_check.application.api import audit_document
from evidence_check.contracts.errors import EvidenceCheckError
from evidence_check.contracts.models import AuditReport, ClaimCandidate, DocumentInput, Reference
from evidence_check.infrastructure.api import load_policy

_LOG = logging.getLogger(__name__)


class AuditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    document_id: str
    text: str
    references: list[Reference] = []
    claims: list[ClaimCandidate] = []
    language_mode: str
    authorized: bool
    single_section: bool

    def to_domain(self) -> DocumentInput:
        return DocumentInput(document_id=self.document_id, text=self.text,
            references=tuple(self.references), claims=tuple(self.claims),
            language_mode=self.language_mode, authorized=self.authorized, single_section=self.single_section)


def create_app(config_dir: Path) -> FastAPI:
    policy = load_policy(config_dir)
    app = FastAPI(title="Evidence Check local POC-A")

    @app.exception_handler(EvidenceCheckError)
    async def stable_error(request: Request, error: EvidenceCheckError) -> JSONResponse:
        _LOG.warning("audit_failed code=%s", error.code)
        return JSONResponse(status_code=422, content={"error":{"code":error.code,"message":error.message}})

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        _LOG.warning("invalid_input")
        return JSONResponse(status_code=422, content={"error":{"code":"invalid_input","message":"Input does not match the document contract."}})

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status":"ok"}

    @app.post("/audits", response_model=AuditReport)
    def audit(body: AuditRequest) -> AuditReport:
        return audit_document(body.to_domain(), policy)

    return app
