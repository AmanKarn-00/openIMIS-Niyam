import uuid

from django.db import models


class NiyamValidationLog(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    claim_uuid = models.CharField(max_length=36, db_index=True)
    claim_code = models.CharField(max_length=50, blank=True, null=True)
    decision = models.CharField(max_length=10)
    reason_code = models.CharField(max_length=80)
    reason = models.TextField()
    correction_path = models.TextField()
    product_code = models.CharField(max_length=20, blank=True, null=True)
    line_type = models.CharField(max_length=20, blank=True, null=True)
    line_code = models.CharField(max_length=50, blank=True, null=True)
    trace = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "niyam_validation_log"
        indexes = [
            models.Index(fields=["claim_uuid", "created_at"]),
            models.Index(fields=["decision", "reason_code"]),
        ]
