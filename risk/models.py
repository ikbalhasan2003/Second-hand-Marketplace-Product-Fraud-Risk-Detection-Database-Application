"""SQL-owned domain mappings. Composite references always use both scalar IDs.

Schema changes belong in reviewed SQL migrations, with synchronized model state.
Unmanaged does not bypass database constraints or authorize an end user.
"""
from datetime import timedelta
from django.db import models
from django.db.models.functions import Now


class FeatureSchema(models.Model):
    feature_schema_id = models.BigAutoField(primary_key=True)
    version = models.CharField(max_length=80)
    definition = models.JSONField()
    code_revision = models.CharField(max_length=64)
    created_at = models.DateTimeField(db_default=Now())

    class Meta:
        managed = False
        db_table = 'feature_schemas'


class DatasetSource(models.Model):
    source_id = models.BigAutoField(primary_key=True)
    source_key = models.CharField(max_length=100)
    source_type = models.CharField(max_length=30)
    attribution = models.TextField()
    license_access_notes = models.TextField()
    source_uri = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(db_default=Now())

    class Meta:
        managed = False
        db_table = 'dataset_sources'


class DatasetVersion(models.Model):
    dataset_id = models.BigAutoField(primary_key=True)
    version = models.CharField(max_length=100)
    feature_schema_id = models.BigIntegerField()
    state = models.CharField(max_length=10, db_default='building')
    generator_version = models.CharField(max_length=100, null=True, blank=True)
    seed = models.BigIntegerField()
    export_cutoff = models.DateTimeField()
    split_strategy = models.TextField()
    manifest_key = models.TextField(null=True, blank=True)
    dataset_sha256 = models.CharField(max_length=64, null=True, blank=True)
    created_by = models.BigIntegerField()
    created_at = models.DateTimeField(db_default=Now())
    frozen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'dataset_versions'


class DatasetSplitGroup(models.Model):
    pk = models.CompositePrimaryKey('dataset_id', 'split_group_id')
    split_group_id = models.BigIntegerField()
    dataset_id = models.BigIntegerField()
    group_key = models.CharField(max_length=150)
    partition = models.CharField(max_length=10)

    class Meta:
        managed = False
        db_table = 'dataset_split_groups'


class DatasetRecord(models.Model):
    record_id = models.BigAutoField(primary_key=True)
    dataset_id = models.BigIntegerField()
    record_key = models.CharField(max_length=150)
    source_id = models.BigIntegerField()
    split_group_id = models.BigIntegerField()
    product_id = models.BigIntegerField(null=True, blank=True)
    revision_no = models.IntegerField(null=True, blank=True)
    review_id = models.BigIntegerField(null=True, blank=True)
    seller_group_key = models.CharField(max_length=150)
    template_family_key = models.CharField(max_length=150, null=True, blank=True)
    duplicate_group_key = models.CharField(max_length=150, null=True, blank=True)
    feature_as_of = models.DateTimeField()
    feature_values = models.JSONField()
    label = models.CharField(max_length=10)
    label_source = models.TextField()
    label_decided_at = models.DateTimeField()
    is_synthetic = models.BooleanField()
    scenario_version = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'dataset_records'


class RiskModel(models.Model):
    model_id = models.BigAutoField(primary_key=True)
    version = models.CharField(max_length=100)
    feature_schema_id = models.BigIntegerField()
    dataset_id = models.BigIntegerField()
    algorithm = models.CharField(max_length=40)
    artifact_key = models.TextField()
    artifact_sha256 = models.CharField(max_length=64)
    seed = models.BigIntegerField()
    class_mapping = models.JSONField()
    dependency_manifest = models.JSONField()
    code_revision = models.CharField(max_length=64)
    state = models.CharField(max_length=12, db_default='registered')
    registered_by = models.BigIntegerField()
    registered_at = models.DateTimeField(db_default=Now())

    class Meta:
        managed = False
        db_table = 'risk_models'


class ModelEvaluation(models.Model):
    evaluation_id = models.BigAutoField(primary_key=True)
    model_id = models.BigIntegerField()
    partition = models.CharField(max_length=10)
    slice_key = models.CharField(max_length=120)
    sample_count = models.IntegerField()
    fraud_count = models.IntegerField()
    true_positive = models.IntegerField()
    false_positive = models.IntegerField()
    true_negative = models.IntegerField()
    false_negative = models.IntegerField()
    average_precision = models.DecimalField(max_digits=9, decimal_places=8, null=True, blank=True)
    report_key = models.TextField()
    evaluated_at = models.DateTimeField(db_default=Now())

    class Meta:
        managed = False
        db_table = 'model_evaluations'


class RiskRuleset(models.Model):
    ruleset_id = models.BigAutoField(primary_key=True)
    version = models.CharField(max_length=100)
    feature_schema_id = models.BigIntegerField()
    state = models.CharField(max_length=10, db_default='draft')
    max_assessment_age = models.DurationField(db_default=timedelta(hours=24))
    created_by = models.BigIntegerField()
    published_by = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(db_default=Now())
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'risk_rulesets'


class RiskRule(models.Model):
    rule_id = models.BigAutoField(primary_key=True)
    ruleset_id = models.BigIntegerField()
    rule_key = models.CharField(max_length=80)
    numeric_value = models.DecimalField(max_digits=14, decimal_places=6)
    description = models.TextField()

    class Meta:
        managed = False
        db_table = 'risk_rules'


class RiskScanJob(models.Model):
    job_id = models.BigAutoField(primary_key=True)
    product_id = models.BigIntegerField()
    revision_no = models.IntegerField()
    context_version = models.BigIntegerField()
    model_id = models.BigIntegerField(null=True, blank=True)
    ruleset_id = models.BigIntegerField(null=True, blank=True)
    feature_schema_id = models.BigIntegerField(null=True, blank=True)
    source_event_key = models.CharField(max_length=220, null=True, blank=True)
    status = models.CharField(max_length=12, db_default='queued')
    attempts = models.IntegerField(db_default=0)
    claim_token = models.UUIDField(null=True, blank=True)
    retry_at = models.DateTimeField(db_default=Now())
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    feature_as_of = models.DateTimeField(null=True, blank=True)
    feature_snapshot = models.JSONField(null=True, blank=True)
    error_code = models.CharField(max_length=80, null=True, blank=True)
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'risk_scan_jobs'


class RiskLog(models.Model):
    risk_id = models.BigAutoField(primary_key=True)
    job_id = models.BigIntegerField()
    risk_score = models.SmallIntegerField()
    risk_level = models.CharField(max_length=6)
    observed_factors = models.JSONField(db_default=list())
    model_explanation = models.JSONField(null=True, blank=True)
    predicted_at = models.DateTimeField(db_default=Now())

    class Meta:
        managed = False
        db_table = 'risk_logs'


class RiskRescanCampaign(models.Model):
    campaign_id = models.BigAutoField(primary_key=True)
    source_event_key = models.CharField(max_length=180)
    event_type = models.CharField(max_length=30)
    source_audit_id = models.BigIntegerField(null=True, blank=True)
    seller_id = models.BigIntegerField(null=True, blank=True)
    target_product_id = models.BigIntegerField(null=True, blank=True)
    cutoff_product_id = models.BigIntegerField()
    cutoff_at = models.DateTimeField(db_default=Now())
    refresh_date = models.DateField(null=True, blank=True)
    refresh_timezone = models.CharField(max_length=80, null=True, blank=True)
    status = models.CharField(max_length=12, db_default='queued')
    cursor_product_id = models.BigIntegerField(db_default=0)
    attempts = models.IntegerField(db_default=0)
    error_code = models.CharField(max_length=80, null=True, blank=True)
    created_at = models.DateTimeField(db_default=Now())
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'risk_rescan_campaigns'


class RiskRescanEvent(models.Model):
    pk = models.CompositePrimaryKey('campaign_id', 'product_id')
    campaign_id = models.BigIntegerField()
    product_id = models.BigIntegerField()
    job_id = models.BigIntegerField()
    created_at = models.DateTimeField(db_default=Now())

    class Meta:
        managed = False
        db_table = 'risk_rescan_events'

