from django.apps import AppConfig

MODULE_NAME = "niyam"

DEFAULT_CFG = {
    "gql_query_niyam_perms": ["111001"],
    "gql_mutation_validate_claim_perms": ["111007"],
    "block_submit_on_block": True,
    "warn_submit_on_warn": False,
    "required_attachment_types": {
        "referral": ["referral", "referral_sheet"],
        "prescription": ["prescription", "rx"],
        "bill": ["bill", "invoice", "digital_bill"],
        "discharge": ["discharge", "discharge_summary"],
        "diagnostic": ["diagnostic", "diagnostic_report", "lab_report"],
    },
}


class NiyamConfig(AppConfig):
    name = MODULE_NAME
    default_auto_field = "django.db.models.BigAutoField"

    gql_query_niyam_perms = []
    gql_mutation_validate_claim_perms = []
    block_submit_on_block = True
    warn_submit_on_warn = False
    required_attachment_types = {}

    def ready(self):
        from core.models import ModuleConfiguration
        from niyam.schema import bind_signals

        cfg = ModuleConfiguration.get_or_default(MODULE_NAME, DEFAULT_CFG)
        self.load_config(cfg)
        bind_signals()

    @classmethod
    def load_config(cls, cfg):
        cls.gql_query_niyam_perms = cfg.get("gql_query_niyam_perms", DEFAULT_CFG["gql_query_niyam_perms"])
        cls.gql_mutation_validate_claim_perms = cfg.get(
            "gql_mutation_validate_claim_perms",
            DEFAULT_CFG["gql_mutation_validate_claim_perms"],
        )
        cls.block_submit_on_block = cfg.get("block_submit_on_block", DEFAULT_CFG["block_submit_on_block"])
        cls.warn_submit_on_warn = cfg.get("warn_submit_on_warn", DEFAULT_CFG["warn_submit_on_warn"])
        cls.required_attachment_types = cfg.get(
            "required_attachment_types",
            DEFAULT_CFG["required_attachment_types"],
        )
