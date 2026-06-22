# openIMIS Backend NIYAM Module

`niyam` is a deterministic pre-submission validation module for openIMIS. It is designed as a normal openIMIS backend module and can also be used independently from Python code.

The module does not ship a mock benefit package. It reads claim, facility, medical, product, policy, and attachment data from openIMIS models, then evaluates whether submitted claim lines are claimable for the active product and provider context.

## Install Into An openIMIS Assembly

Place this folder beside `openimis-be_py`:

```text
Downloads/
  openimis-be_py/
  niyam_openimis/
```

Add this module entry to `openimis-be_py/openimis.json`:

```json
{
  "name": "niyam",
  "pip": "-e ../niyam_openimis"
}
```

The same snippet is available in `openimis-module-entry.json`.

Then install requirements and run migrations from `openimis-be_py`:

```bash
pip install -e ../niyam_openimis
cd openIMIS
python manage.py migrate niyam
```

If you are already inside `openimis-be_py/openIMIS`, the editable install path is `../../niyam_openimis`.

## openIMIS Hook

The module binds to:

```python
core.schema.signal_mutation_module_validate["claim"]
```

When `SubmitClaimsMutation` runs, NIYAM loads the submitted `Claim` objects and validates each active service and item line before openIMIS changes the claim state.

## Independent Use

The pure engine can run without Django:

```python
from niyam.engine import NiyamDecision, ValidationContext, ValidationLine, validate_context

context = ValidationContext(
    claim_id="claim-1",
    facility_code="HF001",
    facility_level="H",
    facility_care_type="B",
    date_of_care="2026-06-05",
    referral_present=False,
    document_codes={"prescription"},
    lines=[
        ValidationLine(
            line_type="service",
            code="OPD01",
            name="OPD ticket",
            care_type="O",
            service_level="H",
            price_asked=50,
            package_active=True,
            product_code="HIB",
            ceiling_amount=50,
        )
    ],
)
decisions = validate_context(context)
```

## Decisions

Each decision is one of:

- `ALLOW`: line is compatible with active product and facility context.
- `WARN`: line can proceed but needs operational attention, usually missing evidence or amount over ceiling.
- `BLOCK`: line should not be submitted until corrected.

Every decision includes a reason code, human-readable reason, correction path, policy/product context, and trace entries.
