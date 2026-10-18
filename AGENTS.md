# Evidence Check development constraints

Read README.md, docs/constraint-ontology.json and docs/product before edits. Use the existing checkout; cloud tasks are already isolated, so do not create worktrees unless requested.

Proceed incrementally: domain/entity/dependency model → directory JSON → public interface contracts → business configuration → domain implementations with tests → complete audit/fix. Record R1–R4 pass/fail at each stage. Do not treat design checks or synthetic fixtures as product precision validation.

- R1: business rules, predicates, thresholds, filters, weights, severities, label mappings and copy belong in versioned configuration; Python computes facts and executes finite validated rules. Keep calculations pure, isolate all IO/model calls in adapters, validate inputs before domain use.
- R2: no business source flat under src or the package root; use subpackages.
- R3: acyclic static imports; cross-domain calls only through api; no eval, exec or runtime dynamic module loading.
- R4: contracts/common never import business domains, application or infrastructure.

Small focused functions and stable DTOs; avoid unnecessary abstractions, unrelated edits and N+1 IO. IO failures must be logged without source content and converted to stable error codes. Changes require normal/error-path tests. Run backend unittest and relevant browser smoke tests. All original evidence must come from uploaded cited fulltext with verifiable page text; no external evidence search, no medical verdicts, no hidden overwriting of human gold labels.

Never commit .evidence-data, keys, passwords, uploaded papers, model responses or local virtual environments. The default model flag is off; enabling requires both policy and explicit task consent. Do not claim production readiness without independent gold evaluation and privacy/security review.
