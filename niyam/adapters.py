from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable, Optional

from django.apps import apps
from django.db.models import Q

from niyam.apps import NiyamConfig
from niyam.engine import NiyamDecision, ValidationContext, ValidationLine, aggregate_decision, validate_context
from niyam.models import NiyamValidationLog


def validate_claim_object(claim, persist: bool = True) -> list[NiyamDecision]:
    context = claim_to_context(claim)
    decisions = validate_context(context)
    if persist:
        persist_decisions(claim, decisions)
    return decisions


def claim_to_context(claim) -> ValidationContext:
    return ValidationContext(
        claim_id=str(getattr(claim, "uuid", None) or getattr(claim, "id", "")),
        facility_code=safe_attr(getattr(claim, "health_facility", None), "code"),
        facility_level=safe_attr(getattr(claim, "health_facility", None), "level"),
        facility_care_type=safe_attr(getattr(claim, "health_facility", None), "care_type"),
        date_of_care=claim_date(claim),
        referral_present=bool(getattr(claim, "refer_from_id", None) or getattr(claim, "refer_to_id", None)),
        document_codes=extract_document_codes(claim),
        lines=[*service_lines(claim), *item_lines(claim)],
    )


def service_lines(claim) -> list[ValidationLine]:
    ProductService = apps.get_model("product", "ProductService")
    lines = []
    for claim_service in active_related(getattr(claim, "services", None)):
        service = getattr(claim_service, "service", None)
        product = getattr(claim_service, "product", None) or product_from_policy(claim_service)
        product_service = None
        if product and service:
            product_service = ProductService.objects.filter(
                product=product,
                service=service,
                validity_to__isnull=True,
            ).first()
        lines.append(
            ValidationLine(
                line_type="service",
                code=safe_attr(service, "code"),
                name=safe_attr(service, "name"),
                care_type=safe_attr(service, "care_type"),
                service_level=safe_attr(service, "level"),
                price_asked=decimal_or_zero(getattr(claim_service, "price_asked", None)),
                package_active=bool(product_service and product_active(product, claim_care_date(claim))),
                product_code=safe_attr(product, "code"),
                product_name=safe_attr(product, "name"),
                ceiling_amount=first_decimal(product_service, "limit_adult", "limit_child"),
                required_documents=required_documents_for("service", service, claim),
            )
        )
    return lines


def item_lines(claim) -> list[ValidationLine]:
    ProductItem = apps.get_model("product", "ProductItem")
    lines = []
    for claim_item in active_related(getattr(claim, "items", None)):
        item = getattr(claim_item, "item", None)
        product = getattr(claim_item, "product", None) or product_from_policy(claim_item)
        product_item = None
        if product and item:
            product_item = ProductItem.objects.filter(
                product=product,
                item=item,
                validity_to__isnull=True,
            ).first()
        lines.append(
            ValidationLine(
                line_type="item",
                code=safe_attr(item, "code"),
                name=safe_attr(item, "name"),
                care_type=safe_attr(item, "care_type"),
                service_level=None,
                price_asked=decimal_or_zero(getattr(claim_item, "price_asked", None)),
                package_active=bool(product_item and product_active(product, claim_care_date(claim))),
                product_code=safe_attr(product, "code"),
                product_name=safe_attr(product, "name"),
                ceiling_amount=first_decimal(product_item, "limit_adult", "limit_child"),
                required_documents=required_documents_for("item", item, claim),
            )
        )
    return lines


def persist_decisions(claim, decisions: Iterable[NiyamDecision]) -> None:
    for decision in decisions:
        NiyamValidationLog.objects.create(
            claim_uuid=str(getattr(claim, "uuid", "")),
            claim_code=getattr(claim, "code", None),
            decision=decision.decision,
            reason_code=decision.reason_code,
            reason=decision.reason,
            correction_path=decision.correction_path,
            product_code=decision.product_code,
            line_type=decision.line_type,
            line_code=decision.line_code,
            trace=[asdict(item) for item in decision.trace],
        )


def decisions_to_mutation_errors(decisions: list[NiyamDecision]) -> list[dict]:
    errors = []
    for decision in decisions:
        if decision.decision == "BLOCK" and NiyamConfig.block_submit_on_block:
            errors.append(decision_to_error(decision))
        if decision.decision == "WARN" and NiyamConfig.warn_submit_on_warn:
            errors.append(decision_to_error(decision))
    return errors


def decision_to_error(decision: NiyamDecision) -> dict:
    return {
        "message": f"{decision.reason_code}: {decision.reason}",
        "detail": decision.correction_path,
        "code": decision.reason_code,
        "line": decision.line_code,
    }


def aggregate_for_claim(claim) -> dict:
    decisions = validate_claim_object(claim)
    return {
        "claimUuid": str(getattr(claim, "uuid", "")),
        "claimCode": getattr(claim, "code", None),
        "decision": aggregate_decision(decisions),
        "decisions": [decision_to_dict(decision) for decision in decisions],
    }


def decision_to_dict(decision: NiyamDecision) -> dict:
    data = asdict(decision)
    data["reasonCode"] = data.pop("reason_code")
    data["correctionPath"] = data.pop("correction_path")
    data["lineType"] = data.pop("line_type")
    data["lineCode"] = data.pop("line_code")
    data["productCode"] = data.pop("product_code")
    return data


def active_related(manager):
    if manager is None:
        return []
    return manager.filter(Q(validity_to__isnull=True) & (Q(rejection_reason__isnull=True) | Q(rejection_reason=0))).all()


def product_from_policy(claim_line):
    policy = getattr(claim_line, "policy", None)
    return getattr(policy, "product", None)


def product_active(product, date_of_care) -> bool:
    if not product:
        return False
    date_from = getattr(product, "date_from", None)
    date_to = getattr(product, "date_to", None)
    if hasattr(date_from, "date"):
        date_from = date_from.date()
    if hasattr(date_to, "date"):
        date_to = date_to.date()
    date_of_care = normalize_date(date_of_care)
    if date_from and date_of_care and date_of_care < date_from:
        return False
    if date_to and date_of_care and date_of_care > date_to:
        return False
    return True


def extract_document_codes(claim) -> frozenset[str]:
    codes = set()
    attachments = getattr(claim, "attachments", None)
    if attachments is not None:
        for attachment in attachments.filter(validity_to__isnull=True).all():
            values = [
                getattr(attachment, "type", None),
                getattr(attachment, "title", None),
                getattr(attachment, "filename", None),
                safe_attr(getattr(attachment, "predefined_type", None), "claim_attachment_type"),
            ]
            for value in values:
                normalized = normalize_document_code(value)
                if normalized:
                    codes.add(normalized)
    if getattr(claim, "refer_from_id", None) or getattr(claim, "refer_to_id", None):
        codes.add("referral")
    return frozenset(codes)


def required_documents_for(line_type: str, item_or_service, claim) -> frozenset[str]:
    required = {"bill"}
    code = (safe_attr(item_or_service, "code") or "").lower()
    name = (safe_attr(item_or_service, "name") or "").lower()
    care_type = safe_attr(item_or_service, "care_type")
    if line_type == "item":
        required.add("prescription")
    if care_type == "I" or "ipd" in code or "inpatient" in name:
        required.add("discharge")
    if any(token in code or token in name for token in ("lab", "rad", "xray", "ct", "mri", "diagnostic")):
        required.add("diagnostic")
    if getattr(claim, "refer_from_id", None) or getattr(claim, "refer_to_id", None):
        required.add("referral")
    return frozenset(required)


def normalize_document_code(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = value.lower().replace("-", "_").replace(" ", "_")
    for canonical, aliases in NiyamConfig.required_attachment_types.items():
        if canonical in text or any(alias in text for alias in aliases):
            return canonical
    return None


def first_decimal(obj, *names) -> Optional[Decimal]:
    if not obj:
        return None
    for name in names:
        value = getattr(obj, name, None)
        if value is not None:
            return Decimal(value)
    return None


def decimal_or_zero(value) -> Decimal:
    return Decimal(value or 0)


def safe_attr(obj, name: str) -> Optional[str]:
    if obj is None:
        return None
    value = getattr(obj, name, None)
    return str(value) if value is not None else None


def claim_date(claim) -> str:
    value = claim_care_date(claim) or getattr(claim, "date_claimed", None)
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")


def claim_care_date(claim):
    return getattr(claim, "date_from", None) or getattr(claim, "date_to", None) or getattr(claim, "date_claimed", None)


def normalize_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None
