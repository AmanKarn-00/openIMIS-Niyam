# NIYAM openIMIS Integration and Standards Analysis

## Scope

This document is a static review of the `niyam_openimis` backend module as provided in this workspace. It explains how the module integrates with openIMIS, what each major file does, and whether the implementation follows common openIMIS backend-module patterns.

This is not a runtime certification. It is based on source inspection, the included tests, and the documented integration flow.

## Executive Summary

NIYAM is implemented as a Django backend module that plugs into openIMIS through the standard module installation path, AppConfig startup, GraphQL exposure, and the core mutation-validation signal. The dominant design choice is good: claim validation is isolated in a pure engine, while the openIMIS-specific glue is kept in adapters and schema code.

Overall, the module is reasonably aligned with openIMIS backend standards for a feature module. It uses the expected packaging pattern, module configuration, signal-based mutation interception, and a dedicated audit table. The largest gaps are not architectural, but quality and robustness issues: the code has limited tests, some schema/config handling is a little loose, and a few integration points depend on assumptions that are not enforced by tests.

## How NIYAM Integrates With openIMIS

### 1. Installation as an openIMIS module

The module is declared in `openimis-module-entry.json` and installed in editable mode from the parent openIMIS assembly. That is the standard openIMIS packaging approach for backend modules.

- `openimis-module-entry.json` declares the module name and pip install path.
- `setup.py` packages the backend as `openimis-be-niyam` and declares dependencies on openIMIS backend modules such as core, claim, location, medical, product, and policy.
- `README.md` and `docs/openimis-integration.md` describe the expected placement next to `openimis-be_py` and the required entry in `openimis.json`.

### 2. Django app startup and configuration loading

`niyam.apps.NiyamConfig` is the module entry point. Its `ready()` method loads `ModuleConfiguration` and then binds the signal handler.

This is the key openIMIS integration point:

- `core.models.ModuleConfiguration.get_or_default()` is used to read module settings.
- `bind_signals()` registers the claim submission validation handler.
- The module keeps permission settings and attachment-type mappings in the app config for runtime use.

### 3. Claim-submission validation hook

The module binds to `core.schema.signal_mutation_module_validate["claim"]`. That means NIYAM participates in the same pre-submit validation flow used by the claim mutation, rather than replacing claim logic or patching the claim app.

At runtime:

- `SubmitClaimsMutation` triggers validation through the core signal.
- NIYAM receives claim UUIDs.
- Each claim is converted into a validation context.
- The deterministic engine returns `ALLOW`, `WARN`, or `BLOCK` decisions.
- Those decisions are converted into GraphQL mutation errors when the config says they should block or warn submission.

This is the strongest sign that the module is integrated in a standard openIMIS way.

### 4. GraphQL surface for operators

`niyam.schema` exposes a small GraphQL API:

- Query a claim validation result manually.
- Read current NIYAM config.
- Run a manual validation mutation.
- Update the module config.

This makes the module operationally usable without coupling business rules to the UI layer.

### 5. Audit logging

Validation decisions are persisted in `niyam_validation_log`. This is useful for auditability, debugging, and future reconciliation with claim decisions.

That table stores:

- claim UUID and code
- decision and reason code
- reason and correction path
- product and line identifiers
- trace data
- creation timestamp

That is a healthy pattern for a pre-submission validation module.

## File-by-File Analysis

### `setup.py`

This file declares the backend package and its dependencies.

What it does well:

- Uses normal Python packaging with `setuptools`.
- Names the package like an openIMIS backend module.
- Declares openIMIS-related dependencies explicitly.
- Uses a Markdown long description and a compatible license declaration.

Assessment:

- Good alignment with backend packaging expectations.
- The dependency list is broad and plausible for claim/product/facility validation.
- There is no obvious packaging anti-pattern in the file itself.

### `openimis-module-entry.json`

This is the module assembly entry used by the parent openIMIS workspace.

What it shows:

- The module is intended to be installed as `niyam`.
- The pip source is an editable local path.

Assessment:

- This is exactly the kind of entry openIMIS assemblies expect for local module inclusion.

### `niyam/apps.py`

This is the runtime bootstrap point.

Key behaviors:

- Declares `NiyamConfig` as a Django `AppConfig`.
- Defines module defaults for GraphQL permissions and submission behavior.
- Loads module configuration from `ModuleConfiguration` in `ready()`.
- Calls `bind_signals()` during startup.

Assessment:

- This is a normal and correct pattern for an openIMIS backend app.
- It centralizes config defaults in one place.
- The only caution is that `ready()` performs runtime work that depends on ORM access. That is accepted in many Django modules, but it is something to watch during startup and tests.

### `niyam/engine.py`

This is the pure business-rule engine.

Core structure:

- `ValidationLine` describes one claim line.
- `ValidationContext` describes the overall claim context.
- `NiyamDecision` captures the result.
- `validate_context()` drives the validation flow.
- `validate_line()` applies the actual rule checks.
- `aggregate_decision()` reduces multiple decisions to a claim-level outcome.

Rules implemented:

- Reject claims with no active lines.
- Block if the line is not linked to an active product package.
- Block if facility care type is incompatible with line care type.
- Warn if facility level is ambiguous or mismatched.
- Warn if required evidence is missing.
- Warn if the asked amount exceeds the configured ceiling.
- Emit a claim-level block for the A1/A2 unbundling conflict.

Assessment:

- This is the strongest part of the module.
- The engine is deterministic, side-effect free, and easy to test.
- The trace model is useful for explainability.
- The only visible concern is that some domain rules are encoded in broad heuristics, for example document classification and the special A1/A2 conflict check. That is acceptable for a first implementation, but those rules should ideally be data-driven if the policy becomes more complex.

### `niyam/adapters.py`

This file converts openIMIS models into the engine context and converts engine output back into persistence and GraphQL-friendly forms.

What it does:

- Converts a `Claim` into `ValidationContext`.
- Builds service lines from `Claim.services`.
- Builds item lines from `Claim.items`.
- Resolves product membership through `ProductService` and `ProductItem`.
- Checks product activity against product validity dates.
- Extracts attachment/document codes from claim attachments.
- Derives required evidence by line type and keywords.
- Persists decisions into `NiyamValidationLog`.
- Converts decisions into GraphQL error dictionaries.

Assessment:

- This is the right place for openIMIS-specific model access.
- The split between engine and adapter is clean and maintainable.
- There are some assumptions worth tracking:
- `claim.services`, `claim.items`, and `claim.attachments` must exist and behave as related managers.
- Attachment-type normalization depends on configuration aliases and string matching.
- Evidence requirements are inferred from code/name heuristics rather than from a dedicated product rule model.

### `niyam/schema.py`

This file exposes validation and configuration through GraphQL and wires the claim submission signal.

What it does:

- Exposes claim validation query and mutation.
- Exposes module config query and update mutation.
- Checks user permissions before reading or mutating.
- Hooks `on_claim_submit_mutation()` into the claim submission validation signal.
- Converts internal decision payloads into GraphQL types.

Assessment:

- The overall shape is consistent with openIMIS backend GraphQL modules.
- Permission gating is present and appropriate.
- The signal handler is the critical integration point and is implemented in the expected direction.
- The config mutation is functional, but it is a little permissive: it writes JSON directly into `ModuleConfiguration` and accepts raw JSON for attachment types without extra validation. That is workable, but stricter validation would reduce operator error.

### `niyam/models.py`

This file defines the persistent audit log.

Assessment:

- The schema is simple and useful.
- The indexes are sensible for claim lookup and reason-based reporting.
- The model is append-only in practice, which fits audit needs.
- This is aligned with a production validation module.

### `niyam/migrations/0001_initial.py`

This migration creates the audit log table and indexes.

Assessment:

- Standard Django migration structure.
- Matches the model cleanly.
- No obvious migration issues in the file.

### `niyam/urls.py`

This file is empty.

Assessment:

- That is not necessarily wrong for a GraphQL-driven backend module.
- It does mean the module does not expose REST endpoints or custom page routes.
- If the intended surface is GraphQL-only, this is fine.

### `niyam/tests/test_engine.py`

The tests currently cover the engine only.

What is covered:

- Allowing a valid product/provider-compatible line.
- Blocking lines missing from an active product.
- Warning when required evidence is missing.

Assessment:

- Good start for the pure engine.
- Coverage is too narrow for the whole openIMIS integration.
- Missing tests include adapter mapping, GraphQL serialization, signal handler behavior, config updates, and persistence logging.

## Standards Assessment

### Where the module follows openIMIS standards well

- Uses a normal backend module package structure.
- Integrates through `ModuleConfiguration` instead of hardcoding deployment settings.
- Uses the mutation validation signal rather than patching claim submission code.
- Keeps validation logic isolated from openIMIS model access.
- Persists audit data for operational traceability.
- Uses GraphQL permissions before exposing module data.
- Avoids embedding product package rows or benefit-package data in code.

### Where the module is weaker or slightly off-pattern

- `default_app_config` is a legacy Django pattern. It still works in many setups, but newer Django projects usually rely on automatic app config discovery.
- `ready()` performs runtime initialization that depends on database-backed configuration. That is common, but it increases startup coupling.
- The config mutation accepts raw JSON input without much structural validation.
- The rules for document type detection and required documents are heuristic-based rather than fully model-driven.
- The test suite does not yet cover the openIMIS integration layer, only the pure engine.

### Bottom-line compliance judgment

If the question is whether NIYAM is integrated with openIMIS in the expected backend-module way, the answer is yes.

If the question is whether the implementation is already production-hardened and fully standards-complete, the answer is not yet. The architecture is sound, but the integration surface needs more tests and stricter validation before it should be considered fully mature.

## Strengths

- Clean separation between engine and openIMIS adapters.
- Deterministic, explainable decision model.
- Good use of GraphQL permissions.
- Signal-based integration matches openIMIS extension patterns.
- Audit trail is built in.
- No hardcoded benefit package data.

## Risks And Gaps

- Integration behavior is not covered by tests end to end.
- The claim adapter depends on several openIMIS model fields and related managers being present exactly as expected.
- Evidence-classification logic relies on string matching and config aliases.
- The `A1`/`A2` unbundling rule is hardcoded and may not scale as a policy model.
- `ready()`-time DB access can become fragile in unusual startup or testing environments.

## Recommendations

1. Add integration tests for the adapter layer, especially `claim_to_context()`, `validate_claim_object()`, and the signal handler.
2. Add GraphQL tests for the query and mutation paths.
3. Validate configuration input before writing JSON back to `ModuleConfiguration`.
4. Consider replacing heuristic evidence detection with a more explicit rule table if the rule set grows.
5. Consider removing `default_app_config` if the target openIMIS stack no longer needs it.
6. Add tests for persistence into `niyam_validation_log`.

## Final Verdict

NIYAM is integrated with openIMIS in a standard and sensible way. The module architecture is good: openIMIS-specific access is isolated in adapters, business rules live in a pure engine, and submission-time enforcement happens through the core mutation signal.

The implementation is close to standards-compliant for a backend module, but it is not fully mature. The biggest issue is not integration design; it is validation depth. More integration tests and stricter config handling would make the module substantially stronger for production use.
