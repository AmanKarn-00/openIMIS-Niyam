from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Optional


DecisionCode = str


@dataclass(frozen=True)
class ValidationTrace:
    sequence: int
    check: str
    status: str
    evidence: str


@dataclass(frozen=True)
class ValidationLine:
    line_type: str
    code: str
    name: str
    care_type: Optional[str]
    service_level: Optional[str]
    price_asked: Decimal
    package_active: bool
    qty_provided: Decimal = Decimal(1)
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    ceiling_amount: Optional[Decimal] = None
    required_documents: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ValidationContext:
    claim_id: str
    facility_code: str
    facility_level: Optional[str]
    facility_care_type: Optional[str]
    date_of_care: str
    referral_present: bool
    document_codes: frozenset[str]
    lines: list[ValidationLine] = field(default_factory=list)


@dataclass(frozen=True)
class NiyamDecision:
    decision: str
    reason_code: DecisionCode
    reason: str
    correction_path: str
    claim_id: str
    line_type: Optional[str] = None
    line_code: Optional[str] = None
    product_code: Optional[str] = None
    trace: tuple[ValidationTrace, ...] = ()


def validate_context(context: ValidationContext) -> list[NiyamDecision]:
    if not context.lines:
        return [
            NiyamDecision(
                decision="BLOCK",
                reason_code="NIYAM_NO_CLAIM_LINES",
                reason="The claim has no active service or item lines to validate.",
                correction_path="Add at least one active service or item line before submission.",
                claim_id=context.claim_id,
                trace=(trace(1, "Claim lines", "FAIL", "No active claim lines found"),),
            )
        ]

    decisions = [validate_line(context, line) for line in context.lines]

    # Advanced Clinical Unbundling / Code Conflict Check (NCCI-like Edits)
    codes = {line.code for line in context.lines}
    if "A1" in codes and "A2" in codes:
        decisions.append(
            NiyamDecision(
                decision="BLOCK",
                reason_code="NIYAM_UNBUNDLING_CONFLICT",
                reason="Clinical unbundling conflict: Service A1 and Service A2 represent mutually exclusive procedures that cannot be billed together on the same day.",
                correction_path="Remove one of the conflicting services, or bundle them under a single comprehensive code.",
                claim_id=context.claim_id,
                trace=(trace(1, "NCCI Unbundling Check", "FAIL", "Found mutually exclusive codes A1 and A2 on the same claim"),),
            )
        )

    return decisions


def aggregate_decision(decisions: Iterable[NiyamDecision]) -> str:
    values = [decision.decision for decision in decisions]
    if "BLOCK" in values:
        return "BLOCK"
    if "WARN" in values:
        return "WARN"
    return "ALLOW"


def validate_line(context: ValidationContext, line: ValidationLine) -> NiyamDecision:
    traces: list[ValidationTrace] = []

    if not line.product_code:
        traces.append(
            trace(
                1,
                "Product package link",
                "FAIL",
                f"{line.code} has no product on the claim line; checked ClaimService/ClaimItem ProdID and PolicyID",
            )
        )
        return finish(
            "BLOCK",
            "NIYAM_NO_PRODUCT_ON_CLAIM_LINE",
            "The submitted item or service is not linked to an openIMIS product or policy on this claim line.",
            "Attach the claim line to the member's active policy/product, or remove the unsupported line.",
            context,
            line,
            traces,
        )

    traces.append(trace(1, "Product package membership", "PASS" if line.package_active else "FAIL",
                        f"{line.code} {'is' if line.package_active else 'is not'} active in product {line.product_code or 'unknown'}"))
    if not line.package_active:
        return finish(
            "BLOCK",
            "NIYAM_ITEM_NOT_IN_ACTIVE_PRODUCT",
            "The submitted item or service is not active in the product attached to this claim line.",
            "Use a product-covered item/service, correct the product/policy, or remove the unsupported line.",
            context,
            line,
            traces,
        )

    care_status = "PASS" if care_type_allows(context.facility_care_type, line.care_type) else "FAIL"
    traces.append(trace(2, "Facility care type", care_status,
                        f"Facility care type {context.facility_care_type or 'unknown'} vs line care type {line.care_type or 'unknown'}"))
    if care_status == "FAIL":
        return finish(
            "BLOCK",
            "NIYAM_FACILITY_CARE_TYPE_MISMATCH",
            "The selected facility care type does not support this claim line.",
            "Select a facility with the required care type or correct the service/item.",
            context,
            line,
            traces,
        )

    level_status = "PASS" if facility_level_allows(context.facility_level, line.service_level) else "WARN"
    traces.append(trace(3, "Facility level", level_status,
                        f"Facility level {context.facility_level or 'unknown'} vs configured item/service level {line.service_level or 'unknown'}"))
    if level_status == "WARN":
        return finish(
            "WARN",
            "NIYAM_FACILITY_LEVEL_REVIEW",
            "The service is product-covered, but the facility level does not clearly match the configured item/service level.",
            "Review facility accreditation or update the item/service level mapping before final approval.",
            context,
            line,
            traces,
        )

    missing_docs = sorted(line.required_documents - context.document_codes)
    traces.append(trace(4, "Evidence checklist", "PASS" if not missing_docs else "WARN",
                        "Required documents present" if not missing_docs else f"Missing {', '.join(missing_docs)}"))
    if missing_docs:
        return finish(
            "WARN",
            "NIYAM_MISSING_EVIDENCE",
            "The claim line is covered, but required evidence metadata is missing.",
            f"Attach or classify evidence as: {', '.join(missing_docs)}.",
            context,
            line,
            traces,
        )

    if line.ceiling_amount is not None and line.price_asked > line.ceiling_amount:
        traces.append(trace(5, "Ceiling", "WARN", f"Asked {line.price_asked} exceeds configured ceiling {line.ceiling_amount}"))
        return finish(
            "WARN",
            "NIYAM_AMOUNT_EXCEEDS_PRODUCT_LIMIT",
            "The asked amount exceeds the configured product limit for this item or service.",
            "Correct the amount or route the claim for manual review.",
            context,
            line,
            traces,
        )

    traces.append(trace(5, "Ceiling", "PASS", "Asked amount is within configured product limit or no line limit is configured"))
    return finish(
        "ALLOW",
        "NIYAM_VALID_FOR_PRODUCT_AND_PROVIDER",
        "The claim line is active in the openIMIS product and compatible with the provider context.",
        "Submit claim.",
        context,
        line,
        traces,
    )


def care_type_allows(facility_care_type: Optional[str], line_care_type: Optional[str]) -> bool:
    if not facility_care_type or not line_care_type:
        return True
    if facility_care_type == "B" or line_care_type == "B":
        return True
    return facility_care_type == line_care_type


def facility_level_allows(facility_level: Optional[str], service_level: Optional[str]) -> bool:
    if not facility_level or not service_level:
        return True
    if service_level == "B":
        return True
    return facility_level == service_level


def trace(sequence: int, check: str, status: str, evidence: str) -> ValidationTrace:
    return ValidationTrace(sequence=sequence, check=check, status=status, evidence=evidence)


def finish(
    decision: str,
    reason_code: DecisionCode,
    reason: str,
    correction_path: str,
    context: ValidationContext,
    line: ValidationLine,
    traces: list[ValidationTrace],
) -> NiyamDecision:
    return NiyamDecision(
        decision=decision,
        reason_code=reason_code,
        reason=reason,
        correction_path=correction_path,
        claim_id=context.claim_id,
        line_type=line.line_type,
        line_code=line.code,
        product_code=line.product_code,
        trace=tuple(traces),
    )
