"""Pure evaluation on explicitly independent human annotations."""
import re
from evidence_check.contracts.errors import InputError


def evaluate(gold,predictions,manifest,legacy,policy):
    required=set(manifest['blind_documents']);development=set(manifest['development_documents'])
    if required & development:raise InputError('split_leakage','Development and blind documents overlap.')
    if {row['source_document_id'] for row in gold} != required:raise InputError('split_mismatch','Gold documents do not match the independent blind manifest.')
    truth={row['record_id']:row for row in gold};guesses={row['record_id']:row for row in predictions}
    if len(truth)!=len(gold) or len(guesses)!=len(predictions):raise InputError('duplicate_record','Record IDs must be unique.')
    if set(truth)!=set(guesses):raise InputError('record_mismatch','Prediction and gold IDs must match exactly.')
    labels=set(legacy.audit.labels);rules={r.id for r in legacy.audit.rules}
    for row in gold:
        if row['annotation_status'] not in policy.evaluation.accepted_statuses:raise InputError('unconfirmed_gold','Pending/preannotated templates are not gold.')
        if not row['claim_text'].strip() or any(re.search(policy.evaluation.placeholder_pattern,row[field]) for field in ('claim_text','source_document_id')):
            raise InputError('template_gold','Placeholder records are not gold.')
    for row in predictions:
        if set(row)!={'record_id','predicted_label','rule_ids','citation_ids'} or row['predicted_label'] not in labels or not set(row['rule_ids'])<=rules:
            raise InputError('invalid_prediction','Prediction contract is invalid.')
    def metrics(field,value):
        expected={key for key,row in truth.items() if value in row[field]}
        actual={key for key,row in guesses.items() if value in row[field]}
        return {'tp':len(expected&actual),'fp':len(actual-expected),'fn':len(expected-actual),
            'precision':len(expected&actual)/len(actual) if actual else None,
            'recall':len(expected&actual)/len(expected) if expected else None}
    by_rule={rule:metrics('rule_ids',rule) for rule in sorted(rules)}
    language_counts={language:sum(row['language_mode']==language for row in gold) for language in legacy.acceptance.language_modes}
    citation_accuracy=sum(set(row['citation_ids'])==set(guesses[key]['citation_ids']) for key,row in truth.items())/len(truth) if truth else None
    gates={req.rule_id:by_rule[req.rule_id]['precision'] is not None and by_rule[req.rule_id]['precision']>=getattr(legacy.acceptance,req.minimum_field) for req in policy.evaluation.precision_requirements}
    counts_ready=all(count>=legacy.acceptance.independent_claims_per_language for count in language_counts.values())
    citation_ready=citation_accuracy is not None and citation_accuracy>=legacy.acceptance.citation_accuracy_min
    return {'records':len(truth),'language_counts':language_counts,'by_rule':by_rule,'citation_accuracy':citation_accuracy,
        'precision_gates':gates,'sample_count_gate':counts_ready,'citation_gate':citation_ready,
        'passed':counts_ready and citation_ready and all(gates.values()),'note':'No-prediction precision is undefined and never passes a precision gate.'}
