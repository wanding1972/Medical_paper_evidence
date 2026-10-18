"""Independent blind evaluation CLI; never modifies gold records."""
import argparse
import json
from pathlib import Path
import sys
from jsonschema import Draft202012Validator
from evidence_check.application.evaluation import evaluate
from evidence_check.contracts.errors import EvidenceCheckError
from evidence_check.infrastructure.api import load_policy,load_product_policy


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--gold',type=Path,required=True);parser.add_argument('--predictions',type=Path,required=True)
    parser.add_argument('--split-manifest',type=Path,required=True)
    parser.add_argument('--schema',type=Path,default=Path('evaluation/annotation-schema.json'))
    parser.add_argument('--config-dir',type=Path,default=Path('backend/config'))
    args=parser.parse_args()
    try:
        gold=[json.loads(line) for line in args.gold.read_text().splitlines() if line.strip()]
        predictions=[json.loads(line) for line in args.predictions.read_text().splitlines() if line.strip()]
        manifest=json.loads(args.split_manifest.read_text())
        if set(manifest)!={'development_documents','blind_documents'} or any(not isinstance(v,list) or any(not isinstance(s,str) for s in v) for v in manifest.values()):raise ValueError('Invalid manifest')
        schema=Draft202012Validator(json.loads(args.schema.read_text()))
        if any(not schema.is_valid(row) for row in gold):raise ValueError('Gold schema failed')
        result=evaluate(gold,predictions,manifest,load_policy(args.config_dir),load_product_policy(args.config_dir))
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['passed'] else 2
    except (OSError,ValueError,KeyError,TypeError,EvidenceCheckError):
        print(json.dumps({'error':'evaluation_input_invalid'}),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
