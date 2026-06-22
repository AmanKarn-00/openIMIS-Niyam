from django.db import migrations, models
import uuid


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="NiyamValidationLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("claim_uuid", models.CharField(db_index=True, max_length=36)),
                ("claim_code", models.CharField(blank=True, max_length=50, null=True)),
                ("decision", models.CharField(max_length=10)),
                ("reason_code", models.CharField(max_length=80)),
                ("reason", models.TextField()),
                ("correction_path", models.TextField()),
                ("product_code", models.CharField(blank=True, max_length=20, null=True)),
                ("line_type", models.CharField(blank=True, max_length=20, null=True)),
                ("line_code", models.CharField(blank=True, max_length=50, null=True)),
                ("trace", models.JSONField(default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "niyam_validation_log",
            },
        ),
        migrations.AddIndex(
            model_name="niyamvalidationlog",
            index=models.Index(fields=["claim_uuid", "created_at"], name="niyam_valid_claim_u_c2f8db_idx"),
        ),
        migrations.AddIndex(
            model_name="niyamvalidationlog",
            index=models.Index(fields=["decision", "reason_code"], name="niyam_valid_decisio_10c172_idx"),
        ),
    ]
