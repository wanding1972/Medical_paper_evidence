"""Local CLI composition root. Original documents are never modified or copied."""
import argparse
import json
import logging
from pathlib import Path
import sys
from pydantic import ValidationError
from evidence_check.application.api import audit_document
from evidence_check.contracts.errors import EvidenceCheckError
from evidence_check.contracts.models import DocumentInput
from evidence_check.infrastructure.api import load_policy, read_context, read_document, render_markdown


def main() -> int:
    parser = argparse.ArgumentParser(description="Evidence Check local citation-integrity POC")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()
    try:
        policy = load_policy(args.config_dir)
        context = read_context(args.context)
        text = read_document(args.input, policy)
        document = DocumentInput.model_validate_json(json.dumps({**context, "text":text}))
        report = audit_document(document, policy)
        output = report.model_dump_json(indent=2) if args.format == "json" else render_markdown(report)
        print(output)
        return 0
    except ValidationError:
        code, message = "invalid_input", "Input does not match the document contract."
    except EvidenceCheckError as error:
        code, message = error.code, error.message
    logging.getLogger(__name__).error("audit_failed code=%s", code)
    print(json.dumps({"error":{"code":code,"message":message}}, ensure_ascii=False), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
