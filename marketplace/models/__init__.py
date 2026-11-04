"""SQL-owned domain mappings. Composite references always use both scalar IDs.

Schema changes belong in reviewed SQL migrations, with synchronized model state.
Unmanaged does not bypass database constraints or authorize an end user.
"""
from datetime import timedelta
from django.db import models
from django.db.models.functions import Now


class MarketplaceSettings(models.Model):
    singleton = models.BooleanField(primary_key=True, db_default=True)
    currency = models.CharField(max_length=3)
    unanswered_order_timeout = models.DurationField(db_default=timedelta(hours=48))
    refresh_timezone = models.CharField(max_length=80, db_default='Asia/Shanghai')

    class Meta:
        managed = False
        db_table = 'marketplace_settings'


class Category(models.Model):
    category_id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=100)
    description = models.TextField(db_default='')
    is_active = models.BooleanField(db_default=True)

    class Meta:
        managed = False
        db_table = 'categories'


class Product(models.Model):
    product_id = models.BigAutoField(primary_key=True)
    seller_id = models.BigIntegerField()
    current_revision_no = models.IntegerField(null=True, blank=True)
    availability = models.CharField(max_length=16, db_default='draft')
    visibility = models.CharField(max_length=24, db_default='visible')
    context_version = models.BigIntegerField(db_default=0)
    first_published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())

    class Meta:
        managed = False
        db_table = 'products'


class ProductRevision(models.Model):
    pk = models.CompositePrimaryKey('product_id', 'revision_no')
    product_id = models.BigIntegerField()
    revision_no = models.IntegerField()
    category_id = models.BigIntegerField()
    title = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(max_digits=12, decimal_places=2)
    original_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3)
    condition = models.CharField(max_length=16)
    location = models.CharField(max_length=150)
    text_fingerprint = models.CharField(max_length=64)
    created_at = models.DateTimeField(db_default=Now())
    created_xid = models.BigIntegerField(db_default=models.Func(function="pg_current_xact_id", output_field=models.BigIntegerField()))

    class Meta:
        managed = False
        db_table = 'product_revisions'


class ProductImage(models.Model):
    image_id = models.BigAutoField(primary_key=True)
    product_id = models.BigIntegerField()
    revision_no = models.IntegerField()
    storage_key = models.CharField(max_length=500)
    sort_order = models.SmallIntegerField()
    content_type = models.CharField(max_length=32)
    byte_size = models.IntegerField()
    content_sha256 = models.CharField(max_length=64)
    width = models.IntegerField()
    height = models.IntegerField()
    uploaded_at = models.DateTimeField(db_default=Now())

    class Meta:
        managed = False
        db_table = 'product_images'


class Conversation(models.Model):
    conversation_id = models.BigAutoField(primary_key=True)
    product_id = models.BigIntegerField()
    buyer_id = models.BigIntegerField()
    created_at = models.DateTimeField(db_default=Now())

    class Meta:
        managed = False
        db_table = 'conversations'


class ChatMessage(models.Model):
    message_id = models.BigAutoField(primary_key=True)
    conversation_id = models.BigIntegerField()
    sender_id = models.BigIntegerField()
    message_text = models.TextField()
    sent_at = models.DateTimeField(db_default=Now())
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'chat_messages'


class Order(models.Model):
    transaction_id = models.BigAutoField(primary_key=True)
    product_id = models.BigIntegerField()
    revision_no = models.IntegerField()
    buyer_id = models.BigIntegerField()
    status = models.CharField(max_length=16, db_default='placed')
    request_key = models.UUIDField()
    request_fingerprint = models.CharField(max_length=64)
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())

    class Meta:
        managed = False
        db_table = 'transactions'


class OrderStatusHistory(models.Model):
    event_id = models.BigAutoField(primary_key=True)
    transaction_id = models.BigIntegerField()
    from_status = models.CharField(max_length=16, null=True, blank=True)
    to_status = models.CharField(max_length=16)
    actor_id = models.BigIntegerField(null=True, blank=True)
    system_actor = models.CharField(max_length=40, null=True, blank=True)
    reason = models.TextField()
    occurred_at = models.DateTimeField(db_default=Now())

    class Meta:
        managed = False
        db_table = 'order_status_history'


class FraudReport(models.Model):
    report_id = models.BigAutoField(primary_key=True)
    product_id = models.BigIntegerField()
    revision_no = models.IntegerField()
    reporter_id = models.BigIntegerField()
    transaction_id = models.BigIntegerField(null=True, blank=True)
    reason_code = models.CharField(max_length=32)
    comment = models.TextField()
    status = models.CharField(max_length=16, db_default='pending')
    assigned_admin_id = models.BigIntegerField(null=True, blank=True)
    public_outcome = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(db_default=Now())
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'fraud_reports'


class ReportAttachment(models.Model):
    attachment_id = models.BigAutoField(primary_key=True)
    report_id = models.BigIntegerField()
    storage_key = models.CharField(max_length=500)
    sort_order = models.SmallIntegerField()
    content_type = models.CharField(max_length=32)
    byte_size = models.IntegerField()
    content_sha256 = models.CharField(max_length=64)
    uploaded_at = models.DateTimeField(db_default=Now())

    class Meta:
        managed = False
        db_table = 'report_attachments'


class ModerationReview(models.Model):
    review_id = models.BigAutoField(primary_key=True)
    product_id = models.BigIntegerField()
    revision_no = models.IntegerField()
    report_id = models.BigIntegerField(null=True, blank=True)
    reviewer_id = models.BigIntegerField()
    verdict = models.CharField(max_length=16)
    reason = models.TextField()
    evidence_summary = models.TextField()
    supersedes_review_id = models.BigIntegerField(null=True, blank=True)
    reviewed_at = models.DateTimeField(db_default=Now())

    class Meta:
        managed = False
        db_table = 'moderation_reviews'


class AdminAuditLog(models.Model):
    audit_id = models.BigAutoField(primary_key=True)
    admin_id = models.BigIntegerField()
    action_type = models.CharField(max_length=64)
    user_id = models.BigIntegerField(null=True, blank=True)
    product_id = models.BigIntegerField(null=True, blank=True)
    report_id = models.BigIntegerField(null=True, blank=True)
    review_id = models.BigIntegerField(null=True, blank=True)
    transaction_id = models.BigIntegerField(null=True, blank=True)
    model_id = models.BigIntegerField(null=True, blank=True)
    ruleset_id = models.BigIntegerField(null=True, blank=True)
    dataset_id = models.BigIntegerField(null=True, blank=True)
    reason = models.TextField()
    before_data = models.JSONField(db_default=dict())
    after_data = models.JSONField(db_default=dict())
    occurred_at = models.DateTimeField(db_default=Now())

    class Meta:
        managed = False
        db_table = 'admin_audit_logs'


class SellerAppeal(models.Model):
    appeal_id = models.BigAutoField(primary_key=True)
    review_id = models.BigIntegerField()
    seller_id = models.BigIntegerField()
    reason = models.TextField()
    status = models.CharField(max_length=16, db_default='pending')
    assigned_admin_id = models.BigIntegerField(null=True, blank=True)
    outcome = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(db_default=Now())
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'seller_appeals'


class Notification(models.Model):
    notification_id = models.BigAutoField(primary_key=True)
    recipient_id = models.BigIntegerField()
    source_event_key = models.CharField(max_length=200)
    summary = models.CharField(max_length=500)
    product_id = models.BigIntegerField(null=True, blank=True)
    transaction_id = models.BigIntegerField(null=True, blank=True)
    report_id = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(db_default=Now())
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'notifications'


class ListingDraft(models.Model):
    product_id = models.BigIntegerField(primary_key=True)
    seller_id = models.BigIntegerField()
    payload = models.JSONField(default=dict)
    version = models.IntegerField(default=1)
    updated_at = models.DateTimeField(db_default=Now())

    class Meta:
        managed = False
        db_table = 'app_listing_drafts'

