from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


SALES_ORDER_MODEL = getattr(settings, "ITP_SALES_ORDER_MODEL", "core.SalesOrder")


def itp_upload_path(instance: "ITPDocument", filename: str) -> str:
    so = getattr(instance.sales_order, "sales_order_number", None) or getattr(
        instance.sales_order, "number", None
    ) or str(instance.sales_order_id)
    return f"itp/{so}/{instance.document_number}/{instance.revision}/{filename}"


def annexure_upload_path(instance: "ITPAnnexure", filename: str) -> str:
    so = getattr(instance.sales_order, "sales_order_number", None) or getattr(
        instance.sales_order, "number", None
    ) or str(instance.sales_order_id)
    return f"itp_annexure/{so}/{instance.document_number}/{instance.revision}/{filename}"


def evidence_upload_path(instance: models.Model, filename: str) -> str:
    return f"itp_evidence/{timezone.now():%Y/%m/%d}/{uuid.uuid4().hex}_{filename}"


class DocumentStatus(models.TextChoices):
    UPLOADED = "UPLOADED", "Uploaded"
    EXTRACTING = "EXTRACTING", "Extraction in progress"
    QC_REVIEW = "QC_REVIEW", "QC review"
    CORRECTION_REQUIRED = "CORRECTION_REQUIRED", "Correction required"
    APPROVED = "APPROVED", "QC approved"
    ACTIVE = "ACTIVE", "Active"
    SUPERSEDED = "SUPERSEDED", "Superseded"
    FAILED = "FAILED", "Import failed"


class SourceFormat(models.TextChoices):
    PDF = "PDF", "PDF"
    EXCEL = "EXCEL", "Excel"


class ITPDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sales_order = models.ForeignKey(
        SALES_ORDER_MODEL,
        on_delete=models.PROTECT,
        related_name="itp_documents",
    )
    document_number = models.CharField(max_length=160)
    revision = models.CharField(max_length=40)
    title = models.CharField(max_length=255, blank=True)
    source_format = models.CharField(max_length=10, choices=SourceFormat.choices)
    original_file = models.FileField(upload_to=itp_upload_path)
    status = models.CharField(
        max_length=30,
        choices=DocumentStatus.choices,
        default=DocumentStatus.UPLOADED,
    )
    extraction_summary = models.JSONField(default=dict, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_itps",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approved_itps",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    comments = GenericRelation("itp.ITPComment")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["sales_order", "document_number", "revision"],
                name="unique_itp_revision_per_sales_order",
            )
        ]
        permissions = [
            ("activate_itp", "Can activate ITP revision"),
        ]

    def __str__(self) -> str:
        return f"{self.document_number} Rev.{self.revision}"

    def clean(self) -> None:
        super().clean()
        suffix = Path(self.original_file.name or "").suffix.lower()
        if suffix not in {".pdf", ".xlsx", ".xls"}:
            raise ValidationError(
                {"original_file": "ITP must be uploaded as PDF, XLSX, or XLS."}
            )
        expected = SourceFormat.PDF if suffix == ".pdf" else SourceFormat.EXCEL
        if self.source_format and self.source_format != expected:
            raise ValidationError(
                {"source_format": f"Source format must be {expected}."}
            )
        self.source_format = expected


class ITPStakeholder(models.Model):
    itp = models.ForeignKey(
        ITPDocument, on_delete=models.CASCADE, related_name="stakeholders"
    )
    name = models.CharField(max_length=120)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["itp", "name"], name="unique_itp_stakeholder"
            )
        ]

    def __str__(self) -> str:
        return self.name


class HoldReleaseMode(models.TextChoices):
    AUTO = "AUTO", "Release automatically after completion"
    MANUAL = "MANUAL", "Manual QC/customer release required"


class ITPClause(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    itp = models.ForeignKey(ITPDocument, on_delete=models.CASCADE, related_name="clauses")
    section_code = models.CharField(max_length=20, blank=True)
    section_title = models.CharField(max_length=255, blank=True)
    clause_number = models.CharField(max_length=60)
    clause_code = models.CharField(max_length=100)
    sequence_order = models.PositiveIntegerField(default=1)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    activity = models.TextField(blank=True)
    reference_document = models.TextField(blank=True)
    characteristics = models.TextField(blank=True)
    inspection_extent = models.TextField(blank=True)
    acceptance_criteria = models.TextField(blank=True)
    verifying_document = models.TextField(blank=True)
    is_hold_point = models.BooleanField(default=False)
    hold_release_mode = models.CharField(
        max_length=10,
        choices=HoldReleaseMode.choices,
        default=HoldReleaseMode.AUTO,
    )
    completion_followup_days = models.PositiveSmallIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    raw_source = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sequence_order", "clause_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["itp", "clause_code"], name="unique_clause_code_per_itp"
            )
        ]

    def __str__(self) -> str:
        return f"{self.clause_code} - {self.activity[:70]}"

    def clean(self) -> None:
        super().clean()
        if self.parent_id and self.parent and self.parent.itp_id != self.itp_id:
            raise ValidationError({"parent": "Parent clause must belong to the same ITP."})


class InterventionCode(models.TextChoices):
    HOLD = "H", "Hold point"
    WITNESS = "W", "Witness"
    REVIEW = "R", "Review"
    APPROVAL = "A", "Approval"
    SURVEILLANCE = "S", "Surveillance"
    MONITOR = "M", "Monitoring"
    RANDOM_WITNESS = "RW", "Random witness"
    ACTUAL = "AI", "Actual inspection"
    TEST_CERTIFICATE = "TC", "Test certificate"
    NONE = "-", "Not applicable"
    OTHER = "OTHER", "Other"


class ITPClauseIntervention(models.Model):
    clause = models.ForeignKey(
        ITPClause, on_delete=models.CASCADE, related_name="interventions"
    )
    stakeholder = models.ForeignKey(
        ITPStakeholder, on_delete=models.CASCADE, related_name="interventions"
    )
    point_code = models.CharField(max_length=30, blank=True)
    sampling_text = models.CharField(max_length=120, blank=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["clause", "stakeholder"],
                name="unique_clause_stakeholder_intervention",
            )
        ]

    @property
    def is_hold(self) -> bool:
        return self.point_code.strip().upper().startswith("H")

    def __str__(self) -> str:
        return f"{self.clause.clause_code} / {self.stakeholder}: {self.point_code}"


class DependencyType(models.TextChoices):
    FINISH_TO_START = "FS", "Finish to start"
    REVIEW_BEFORE_START = "RBS", "Review before start"


class ITPClauseDependency(models.Model):
    predecessor = models.ForeignKey(
        ITPClause, on_delete=models.CASCADE, related_name="successor_links"
    )
    successor = models.ForeignKey(
        ITPClause, on_delete=models.CASCADE, related_name="predecessor_links"
    )
    dependency_type = models.CharField(
        max_length=10,
        choices=DependencyType.choices,
        default=DependencyType.FINISH_TO_START,
    )
    mandatory = models.BooleanField(default=True)
    applies_to_same_annexure_line = models.BooleanField(default=True)
    blocking_if_predecessor_is_hold = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["predecessor", "successor"],
                name="unique_clause_dependency",
            )
        ]

    def clean(self) -> None:
        super().clean()
        if self.predecessor_id == self.successor_id:
            raise ValidationError("A clause cannot depend on itself.")
        if (
            self.predecessor_id
            and self.successor_id
            and self.predecessor.itp_id != self.successor.itp_id
        ):
            raise ValidationError("Both clauses must belong to the same ITP.")
        if (
            self.predecessor_id
            and self.successor_id
            and self.predecessor.sequence_order >= self.successor.sequence_order
        ):
            raise ValidationError(
                "Predecessor sequence must be before successor sequence."
            )

    def __str__(self) -> str:
        return f"{self.predecessor.clause_code} -> {self.successor.clause_code}"


class ITPAnnexure(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sales_order = models.ForeignKey(
        SALES_ORDER_MODEL,
        on_delete=models.PROTECT,
        related_name="itp_annexures",
    )
    document_number = models.CharField(max_length=160)
    revision = models.CharField(max_length=40)
    title = models.CharField(max_length=255, blank=True)
    original_file = models.FileField(upload_to=annexure_upload_path)
    status = models.CharField(
        max_length=30,
        choices=DocumentStatus.choices,
        default=DocumentStatus.UPLOADED,
    )
    import_summary = models.JSONField(default=dict, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_itp_annexures",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approved_itp_annexures",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    comments = GenericRelation("itp.ITPComment")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["sales_order", "document_number", "revision"],
                name="unique_annexure_revision_per_sales_order",
            )
        ]
        permissions = [
            ("activate_annexure", "Can activate ITP annexure revision"),
        ]

    def __str__(self) -> str:
        return f"{self.document_number} Rev.{self.revision}"

    def clean(self) -> None:
        super().clean()
        suffix = Path(self.original_file.name or "").suffix.lower()
        if suffix not in {".xlsx", ".xls"}:
            raise ValidationError(
                {"original_file": "Annexure must be uploaded as an Excel file (XLSX or XLS)."}
            )


class ITPAnnexureLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    annexure = models.ForeignKey(
        ITPAnnexure, on_delete=models.CASCADE, related_name="lines"
    )
    row_number = models.PositiveIntegerField()
    po_line_no = models.CharField(max_length=80)
    description = models.TextField()
    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0"))],
    )
    inspection_class = models.CharField(max_length=80, blank=True)
    nde_applicable = models.CharField(max_length=255, blank=True)
    temperature_text = models.CharField(max_length=120, blank=True)
    temperature_min = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True
    )
    temperature_max = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True
    )
    tag_number = models.CharField(max_length=255, blank=True)
    piping_class = models.CharField(max_length=255, blank=True)
    service = models.CharField(max_length=120, blank=True)
    insulation = models.CharField(max_length=120, blank=True)
    datasheet_number = models.CharField(max_length=255, blank=True)
    valve_size = models.CharField(max_length=80, blank=True)
    pressure_class = models.CharField(max_length=80, blank=True)
    valve_type = models.CharField(max_length=120, blank=True)
    body_material = models.CharField(max_length=160, blank=True)
    raw_data = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["row_number", "po_line_no"]
        constraints = [
            models.UniqueConstraint(
                fields=["annexure", "po_line_no"],
                name="unique_po_line_per_annexure",
            )
        ]

    def __str__(self) -> str:
        return f"Line {self.po_line_no} - {self.tag_number or self.description[:60]}"


class MappingSource(models.TextChoices):
    AUTO = "AUTO", "Auto suggested"
    IMPORTED = "IMPORTED", "Imported"
    MANUAL = "MANUAL", "Manual"


class MappingReviewStatus(models.TextChoices):
    SUGGESTED = "SUGGESTED", "Suggested - review required"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected / not applicable"


class ITPLineClauseMapping(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    clause = models.ForeignKey(
        ITPClause, on_delete=models.CASCADE, related_name="line_mappings"
    )
    annexure_line = models.ForeignKey(
        ITPAnnexureLine, on_delete=models.CASCADE, related_name="clause_mappings"
    )
    is_applicable = models.BooleanField(default=True)
    required_quantity = models.DecimalField(
        max_digits=14, decimal_places=3, null=True, blank=True
    )
    extent_override = models.CharField(max_length=255, blank=True)
    source = models.CharField(
        max_length=20, choices=MappingSource.choices, default=MappingSource.AUTO
    )
    review_status = models.CharField(
        max_length=20,
        choices=MappingReviewStatus.choices,
        default=MappingReviewStatus.SUGGESTED,
    )
    rationale = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_itp_mappings",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["clause__sequence_order", "annexure_line__row_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["clause", "annexure_line"],
                name="unique_clause_annexure_line_mapping",
            )
        ]

    def clean(self) -> None:
        super().clean()
        if self.clause_id and self.annexure_line_id:
            if self.clause.itp.sales_order_id != self.annexure_line.annexure.sales_order_id:
                raise ValidationError(
                    "ITP clause and annexure line must belong to the same Sales Order."
                )

    @property
    def effective_required_quantity(self) -> Decimal:
        return self.required_quantity if self.required_quantity is not None else self.annexure_line.quantity

    def __str__(self) -> str:
        return f"{self.clause.clause_code} / line {self.annexure_line.po_line_no}"


class NOIStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SUBMITTED = "SUBMITTED", "Submitted"
    ACCEPTED = "ACCEPTED", "Accepted"
    WAIVED = "WAIVED", "Waived"
    RESCHEDULED = "RESCHEDULED", "Rescheduled"
    ATTENDED = "ATTENDED", "Attended"
    COMPLETED = "COMPLETED", "Completed"
    NOT_COMPLETED = "NOT_COMPLETED", "Not completed"
    CLOSED = "CLOSED", "Closed"
    CANCELLED = "CANCELLED", "Cancelled"


class CompletionStatus(models.TextChoices):
    PENDING = "PENDING", "Pending confirmation"
    COMPLETED = "COMPLETED", "Completed"
    NOT_COMPLETED = "NOT_COMPLETED", "Not completed"


class NOINumberSequence(models.Model):
    year = models.PositiveIntegerField(unique=True)
    last_number = models.PositiveIntegerField(default=0)


class NoticeOfInspection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.CharField(max_length=80, unique=True)
    itp = models.ForeignKey(
        ITPDocument, on_delete=models.PROTECT, related_name="inspection_notices"
    )
    annexure = models.ForeignKey(
        ITPAnnexure, on_delete=models.PROTECT, related_name="inspection_notices"
    )
    scheduled_start = models.DateTimeField()
    scheduled_end = models.DateTimeField()
    location = models.CharField(max_length=255, blank=True)
    responsible_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="responsible_nois",
    )
    status = models.CharField(
        max_length=30, choices=NOIStatus.choices, default=NOIStatus.DRAFT
    )
    completion_status = models.CharField(
        max_length=30,
        choices=CompletionStatus.choices,
        default=CompletionStatus.PENDING,
    )
    completion_confirmation_due_at = models.DateTimeField(null=True, blank=True)
    completion_prompt_sent_at = models.DateTimeField(null=True, blank=True)
    completion_confirmed_at = models.DateTimeField(null=True, blank=True)
    completion_comment = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_nois",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    comments = GenericRelation("itp.ITPComment")

    class Meta:
        ordering = ["-scheduled_start", "-created_at"]

    def clean(self) -> None:
        super().clean()
        if self.scheduled_end and self.scheduled_start and self.scheduled_end < self.scheduled_start:
            raise ValidationError({"scheduled_end": "End date cannot be before start date."})
        if self.itp_id and self.annexure_id and self.itp.sales_order_id != self.annexure.sales_order_id:
            raise ValidationError("ITP and annexure must belong to the same Sales Order.")
        if self.itp_id and self.itp.status != DocumentStatus.ACTIVE:
            raise ValidationError({"itp": "Only an active ITP can be used for an NOI."})
        if self.annexure_id and self.annexure.status != DocumentStatus.ACTIVE:
            raise ValidationError({"annexure": "Only an active annexure can be used for an NOI."})

    def __str__(self) -> str:
        return self.number


class CoverageResult(models.TextChoices):
    PENDING = "PENDING", "Pending"
    ACCEPTED = "ACCEPTED", "Accepted"
    REJECTED = "REJECTED", "Rejected"
    WAIVED = "WAIVED", "Waived"
    NOT_COMPLETED = "NOT_COMPLETED", "Not completed"


class NOICoverage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    noi = models.ForeignKey(
        NoticeOfInspection, on_delete=models.CASCADE, related_name="coverages"
    )
    clause = models.ForeignKey(
        ITPClause, on_delete=models.PROTECT, related_name="noi_coverages"
    )
    annexure_line = models.ForeignKey(
        ITPAnnexureLine, on_delete=models.PROTECT, related_name="noi_coverages"
    )
    offered_quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    completed_quantity = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal("0")
    )
    heat_numbers = models.TextField(blank=True)
    serial_numbers = models.TextField(blank=True)
    previous_activity_state = models.JSONField(default=list, blank=True)
    blocked_on_creation = models.BooleanField(default=False)
    result = models.CharField(
        max_length=30, choices=CoverageResult.choices, default=CoverageResult.PENDING
    )
    actual_completion_at = models.DateTimeField(null=True, blank=True)
    report_reference = models.CharField(max_length=255, blank=True)
    evidence_file = models.FileField(
        upload_to=evidence_upload_path, null=True, blank=True
    )

    class Meta:
        ordering = ["clause__sequence_order", "annexure_line__row_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["noi", "clause", "annexure_line"],
                name="unique_noi_clause_line_coverage",
            )
        ]

    def clean(self) -> None:
        super().clean()
        if self.clause_id and self.noi_id and self.clause.itp_id != self.noi.itp_id:
            raise ValidationError("Clause must belong to the NOI ITP.")
        if (
            self.annexure_line_id
            and self.noi_id
            and self.annexure_line.annexure_id != self.noi.annexure_id
        ):
            raise ValidationError("Annexure line must belong to the NOI annexure.")
        if self.offered_quantity and self.annexure_line_id:
            if self.offered_quantity > self.annexure_line.quantity:
                raise ValidationError(
                    {"offered_quantity": "Offered quantity exceeds annexure line quantity."}
                )

    def __str__(self) -> str:
        return f"{self.noi.number}: {self.clause.clause_code} / {self.annexure_line.po_line_no}"


class ExecutionStatus(models.TextChoices):
    PLANNED = "PLANNED", "Planned"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    COMPLETED = "COMPLETED", "Completed"
    NOT_COMPLETED = "NOT_COMPLETED", "Not completed"
    RELEASED = "RELEASED", "Hold point released"
    WAIVED = "WAIVED", "Waived"
    REJECTED = "REJECTED", "Rejected"
    OVERRIDDEN = "OVERRIDDEN", "Authorised override"


class ExecutionSource(models.TextChoices):
    NOI = "NOI", "NOI"
    INTERNAL = "INTERNAL", "Internal completion"


class ITPActivityExecution(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mapping = models.ForeignKey(
        ITPLineClauseMapping,
        on_delete=models.PROTECT,
        related_name="executions",
    )
    noi_coverage = models.ForeignKey(
        NOICoverage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="executions",
    )
    source = models.CharField(
        max_length=20, choices=ExecutionSource.choices, default=ExecutionSource.INTERNAL
    )
    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    status = models.CharField(
        max_length=30, choices=ExecutionStatus.choices, default=ExecutionStatus.PLANNED
    )
    scheduled_end = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="completed_itp_activities",
    )
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="released_itp_hold_points",
    )
    release_reference = models.CharField(max_length=255, blank=True)
    remarks = models.TextField(blank=True)
    evidence_file = models.FileField(
        upload_to=evidence_upload_path, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        permissions = [
            ("release_hold_point", "Can release ITP hold point"),
            ("override_hold_point", "Can override incomplete hold point"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.noi_coverage_id:
            if self.noi_coverage.clause_id != self.mapping.clause_id:
                raise ValidationError("NOI coverage clause does not match execution mapping.")
            if self.noi_coverage.annexure_line_id != self.mapping.annexure_line_id:
                raise ValidationError(
                    "NOI coverage annexure line does not match execution mapping."
                )
        if self.status in {ExecutionStatus.RELEASED, ExecutionStatus.WAIVED, ExecutionStatus.OVERRIDDEN}:
            if not self.mapping.clause.is_hold_point:
                raise ValidationError("Only Hold Point clauses can be released or overridden.")

    def __str__(self) -> str:
        return f"{self.mapping} - {self.status} ({self.quantity})"


class CompletionTaskStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    COMPLETED = "COMPLETED", "Completed"
    OVERDUE = "OVERDUE", "Overdue"


class NOICompletionTask(models.Model):
    noi = models.OneToOneField(
        NoticeOfInspection, on_delete=models.CASCADE, related_name="completion_task"
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="noi_completion_tasks",
    )
    due_at = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=CompletionTaskStatus.choices,
        default=CompletionTaskStatus.OPEN,
    )
    reminder_count = models.PositiveIntegerField(default=0)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    escalated_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["due_at"]

    def __str__(self) -> str:
        return f"Completion task: {self.noi.number}"


class AlertSeverity(models.TextChoices):
    INFO = "INFO", "Information"
    WARNING = "WARNING", "Warning"
    CRITICAL = "CRITICAL", "Critical"


class AlertType(models.TextChoices):
    COMPLETION_DUE = "COMPLETION_DUE", "Completion confirmation due"
    COMPLETION_OVERDUE = "COMPLETION_OVERDUE", "Completion confirmation overdue"
    HOLD_INCOMPLETE = "HOLD_INCOMPLETE", "Previous Hold Point incomplete"
    HOLD_AWAITING_RELEASE = "HOLD_AWAITING_RELEASE", "Hold Point awaiting release"
    IMPORT_ERROR = "IMPORT_ERROR", "Import error"


class WorkflowAlert(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    alert_type = models.CharField(max_length=40, choices=AlertType.choices)
    severity = models.CharField(
        max_length=20, choices=AlertSeverity.choices, default=AlertSeverity.WARNING
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="itp_workflow_alerts",
    )
    noi = models.ForeignKey(
        NoticeOfInspection,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="alerts",
    )
    coverage = models.ForeignKey(
        NOICoverage,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="alerts",
    )
    is_resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_itp_alerts",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["is_resolved", "-created_at"]

    def __str__(self) -> str:
        return self.title


class ImportIssueSeverity(models.TextChoices):
    WARNING = "WARNING", "Warning"
    ERROR = "ERROR", "Error"


class ImportIssue(models.Model):
    itp = models.ForeignKey(
        ITPDocument,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="import_issues",
    )
    annexure = models.ForeignKey(
        ITPAnnexure,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="import_issues",
    )
    severity = models.CharField(
        max_length=20,
        choices=ImportIssueSeverity.choices,
        default=ImportIssueSeverity.WARNING,
    )
    source_location = models.CharField(max_length=120, blank=True)
    message = models.TextField()
    raw_data = models.JSONField(default=dict, blank=True)
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["is_resolved", "severity", "id"]

    def clean(self) -> None:
        super().clean()
        if bool(self.itp_id) == bool(self.annexure_id):
            raise ValidationError("Select exactly one of ITP or annexure.")

    def __str__(self) -> str:
        return f"{self.severity}: {self.message[:100]}"


class AuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="itp_audit_actions",
    )
    action = models.CharField(max_length=120)
    object_type = models.CharField(max_length=120)
    object_id = models.CharField(max_length=120)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} - {self.object_type}:{self.object_id}"


class CommentKind(models.TextChoices):
    COMMENT = "COMMENT", "Comment"
    CORRECTION_REQUEST = "CORRECTION_REQUEST", "Correction requested"


class ITPComment(models.Model):
    """A remark or a QC correction request attached to an ITP document, annexure, or NOI.

    Uses a generic relation so the same model/view/template code covers all
    three cases instead of three near-duplicate comment tables.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    content_object = GenericForeignKey("content_type", "object_id")
    kind = models.CharField(
        max_length=20, choices=CommentKind.choices, default=CommentKind.COMMENT
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="itp_comments",
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} by {self.author} on {self.content_object}"
