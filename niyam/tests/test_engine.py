from decimal import Decimal
from unittest import TestCase

from niyam.engine import ValidationContext, ValidationLine, aggregate_decision, validate_context


class NiyamEngineTest(TestCase):
    def test_allows_product_and_provider_compatible_line(self):
        decisions = validate_context(
            ValidationContext(
                claim_id="claim-1",
                facility_code="HF001",
                facility_level="H",
                facility_care_type="B",
                date_of_care="2026-06-05",
                referral_present=False,
                document_codes=frozenset({"bill"}),
                lines=[
                    ValidationLine(
                        line_type="service",
                        code="OPD01",
                        name="OPD ticket",
                        care_type="O",
                        service_level="H",
                        price_asked=Decimal("50"),
                        package_active=True,
                        product_code="HIB",
                        ceiling_amount=Decimal("100"),
                        required_documents=frozenset({"bill"}),
                    )
                ],
            )
        )

        self.assertEqual("ALLOW", decisions[0].decision)
        self.assertEqual("NIYAM_VALID_FOR_PRODUCT_AND_PROVIDER", decisions[0].reason_code)

    def test_blocks_line_missing_from_active_product(self):
        decisions = validate_context(
            ValidationContext(
                claim_id="claim-1",
                facility_code="HF001",
                facility_level="H",
                facility_care_type="B",
                date_of_care="2026-06-05",
                referral_present=False,
                document_codes=frozenset(),
                lines=[
                    ValidationLine(
                        line_type="service",
                        code="MRI01",
                        name="MRI",
                        care_type="O",
                        service_level="R",
                        price_asked=Decimal("5000"),
                        package_active=False,
                        product_code="HIB",
                    )
                ],
            )
        )

        self.assertEqual("BLOCK", decisions[0].decision)
        self.assertEqual("NIYAM_ITEM_NOT_IN_ACTIVE_PRODUCT", decisions[0].reason_code)
        self.assertEqual("BLOCK", aggregate_decision(decisions))

    def test_blocks_line_without_product_link(self):
        decisions = validate_context(
            ValidationContext(
                claim_id="claim-1",
                facility_code="HF001",
                facility_level="H",
                facility_care_type="B",
                date_of_care="2026-06-05",
                referral_present=False,
                document_codes=frozenset(),
                lines=[
                    ValidationLine(
                        line_type="service",
                        code="OPD01",
                        name="OPD ticket",
                        care_type="O",
                        service_level="H",
                        price_asked=Decimal("50"),
                        package_active=False,
                    )
                ],
            )
        )

        self.assertEqual("BLOCK", decisions[0].decision)
        self.assertEqual("NIYAM_NO_PRODUCT_ON_CLAIM_LINE", decisions[0].reason_code)

    def test_warns_when_required_evidence_is_missing(self):
        decisions = validate_context(
            ValidationContext(
                claim_id="claim-1",
                facility_code="HF001",
                facility_level="H",
                facility_care_type="B",
                date_of_care="2026-06-05",
                referral_present=False,
                document_codes=frozenset({"bill"}),
                lines=[
                    ValidationLine(
                        line_type="item",
                        code="MED01",
                        name="Medicine",
                        care_type="O",
                        service_level=None,
                        price_asked=Decimal("40"),
                        package_active=True,
                        product_code="HIB",
                        required_documents=frozenset({"bill", "prescription"}),
                    )
                ],
            )
        )

        self.assertEqual("WARN", decisions[0].decision)
        self.assertEqual("NIYAM_MISSING_EVIDENCE", decisions[0].reason_code)
