import graphene
from django.core.exceptions import PermissionDenied, ValidationError
from django.dispatch import dispatcher
from django.utils.translation import gettext as _
from json import JSONDecodeError

from claim.gql_mutations import SubmitClaimsMutation
from claim.models import Claim
from core.schema import signal_mutation_module_validate

import json
from core.models import ModuleConfiguration

from niyam.adapters import aggregate_for_claim, decisions_to_mutation_errors, validate_claim_object
from niyam.apps import NiyamConfig


class NiyamTraceGQLType(graphene.ObjectType):
    sequence = graphene.Int()
    check = graphene.String()
    status = graphene.String()
    evidence = graphene.String()


class NiyamDecisionGQLType(graphene.ObjectType):
    decision = graphene.String()
    reason_code = graphene.String()
    reason = graphene.String()
    correction_path = graphene.String()
    claim_id = graphene.String()
    line_type = graphene.String()
    line_code = graphene.String()
    product_code = graphene.String()
    trace = graphene.List(NiyamTraceGQLType)


class NiyamClaimValidationGQLType(graphene.ObjectType):
    claim_uuid = graphene.String()
    claim_code = graphene.String()
    decision = graphene.String()
    decisions = graphene.List(NiyamDecisionGQLType)


class NiyamConfigGQLType(graphene.ObjectType):
    block_submit_on_block = graphene.Boolean()
    warn_submit_on_warn = graphene.Boolean()
    required_attachment_types_json = graphene.String()


class Query(graphene.ObjectType):
    niyam_validate_claim = graphene.Field(
        NiyamClaimValidationGQLType,
        claim_uuid=graphene.String(required=True),
        description="Run NIYAM deterministic validation for an existing openIMIS claim.",
    )
    niyam_config = graphene.Field(
        NiyamConfigGQLType,
        description="Get current NIYAM configurations"
    )

    def resolve_niyam_validate_claim(self, info, claim_uuid):
        if not info.context.user.has_perms(NiyamConfig.gql_query_niyam_perms):
            raise PermissionDenied(_("unauthorized"))
        claim = Claim.objects.get(uuid=claim_uuid, validity_to__isnull=True)
        return to_gql_payload(aggregate_for_claim(claim))

    def resolve_niyam_config(self, info):
        if not info.context.user.has_perms(NiyamConfig.gql_query_niyam_perms):
            raise PermissionDenied(_("unauthorized"))
        return NiyamConfigGQLType(
            block_submit_on_block=NiyamConfig.block_submit_on_block,
            warn_submit_on_warn=NiyamConfig.warn_submit_on_warn,
            required_attachment_types_json=json.dumps(NiyamConfig.required_attachment_types)
        )


class ValidateNiyamClaimMutation(graphene.ClientIDMutation):
    class Input:
        claim_uuid = graphene.String(required=True)

    validation = graphene.Field(NiyamClaimValidationGQLType)

    @classmethod
    def mutate_and_get_payload(cls, root, info, **data):
        if not info.context.user.has_perms(NiyamConfig.gql_mutation_validate_claim_perms):
            raise PermissionDenied(_("unauthorized"))
        claim = Claim.objects.get(uuid=data["claim_uuid"], validity_to__isnull=True)
        return ValidateNiyamClaimMutation(validation=to_gql_payload(aggregate_for_claim(claim)))


class UpdateNiyamConfigMutation(graphene.ClientIDMutation):
    class Input:
        block_submit_on_block = graphene.Boolean()
        warn_submit_on_warn = graphene.Boolean()
        required_attachment_types_json = graphene.String()

    config = graphene.Field(NiyamConfigGQLType)

    @classmethod
    def mutate_and_get_payload(cls, root, info, **data):
        if not info.context.user.has_perms(NiyamConfig.gql_mutation_validate_claim_perms):
            raise PermissionDenied(_("unauthorized"))

        block_submit_on_block = data.get("block_submit_on_block")
        warn_submit_on_warn = data.get("warn_submit_on_warn")
        required_attachment_types_json = data.get("required_attachment_types_json")

        cfg_obj = ModuleConfiguration.objects.filter(module="niyam", layer="be").first()
        if not cfg_obj:
            cfg_obj = ModuleConfiguration(module="niyam", layer="be", version="1.0")
            cfg_val = {}
        else:
            try:
                cfg_val = json.loads(cfg_obj.config) if cfg_obj.config else {}
            except Exception:
                cfg_val = {}

        if block_submit_on_block is not None:
            cfg_val["block_submit_on_block"] = block_submit_on_block
            NiyamConfig.block_submit_on_block = block_submit_on_block
        if warn_submit_on_warn is not None:
            cfg_val["warn_submit_on_warn"] = warn_submit_on_warn
            NiyamConfig.warn_submit_on_warn = warn_submit_on_warn
        if required_attachment_types_json is not None:
            parsed = parse_attachment_types(required_attachment_types_json)
            cfg_val["required_attachment_types"] = parsed
            NiyamConfig.required_attachment_types = parsed

        cfg_obj.config = json.dumps(cfg_val)
        cfg_obj.save()

        return UpdateNiyamConfigMutation(
            config=NiyamConfigGQLType(
                block_submit_on_block=NiyamConfig.block_submit_on_block,
                warn_submit_on_warn=NiyamConfig.warn_submit_on_warn,
                required_attachment_types_json=json.dumps(NiyamConfig.required_attachment_types)
            )
        )


class Mutation(graphene.ObjectType):
    validate_niyam_claim = ValidateNiyamClaimMutation.Field()
    update_niyam_config = UpdateNiyamConfigMutation.Field()


def on_claim_submit_mutation(sender: dispatcher.Signal, **kwargs):
    if getattr(sender, "_mutation_class", None) != SubmitClaimsMutation._mutation_class:
        return []

    errors = []
    uuids = kwargs.get("data", {}).get("uuids", [])
    if not uuids:
        return []

    claims = Claim.objects.filter(uuid__in=uuids, validity_to__isnull=True)
    for claim in claims:
        decisions = validate_claim_object(claim)
        errors.extend(decisions_to_mutation_errors(decisions))
    return errors


def bind_signals():
    signal_mutation_module_validate["claim"].connect(on_claim_submit_mutation, dispatch_uid="niyam_claim_submit_validation")


def to_gql_payload(payload: dict) -> NiyamClaimValidationGQLType:
    decisions = []
    for decision in payload["decisions"]:
        trace = [NiyamTraceGQLType(**item) for item in decision["trace"]]
        decisions.append(
            NiyamDecisionGQLType(
                decision=decision["decision"],
                reason_code=decision["reasonCode"],
                reason=decision["reason"],
                correction_path=decision["correctionPath"],
                claim_id=decision["claim_id"],
                line_type=decision["lineType"],
                line_code=decision["lineCode"],
                product_code=decision["productCode"],
                trace=trace,
            )
        )
    return NiyamClaimValidationGQLType(
        claim_uuid=payload["claimUuid"],
        claim_code=payload["claimCode"],
        decision=payload["decision"],
        decisions=decisions,
    )


def parse_attachment_types(raw_json: str) -> dict:
    try:
        parsed = json.loads(raw_json)
    except JSONDecodeError as exc:
        raise ValidationError(_("required_attachment_types_json must be valid JSON")) from exc

    if not isinstance(parsed, dict):
        raise ValidationError(_("required_attachment_types_json must be a JSON object"))

    for category, aliases in parsed.items():
        if not isinstance(category, str):
            raise ValidationError(_("attachment type category keys must be strings"))
        if not isinstance(aliases, list) or not all(isinstance(alias, str) for alias in aliases):
            raise ValidationError(_("attachment type aliases must be arrays of strings"))

    return parsed
