from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone


DEPARTMENT_MODEL = getattr(
    settings,
    "CALIBRATION_DEPARTMENT_MODEL",
    "core.Department",
)


def certificate_upload_path(instance: "CalibrationCycle", filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    safe_name = f"{uuid4().hex}{suffix}"
    return (
        f"calibration/{instance.instrument.asset_number}/"
        f"cycle_{instance.cycle_number}/{safe_name}"
    )


class InstrumentCategory(models.Model):
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Instrument categories"

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class CalibrationLaboratory(models.Model):
    name = models.CharField(max_length=180, unique=True)
    accreditation_number = models.CharField(max_length=120, blank=True)
    accreditation_expiry = models.DateField(null=True, blank=True)
    contact_person = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class InstrumentStatus(models.TextChoices):
    IN_USE = "IN_USE", "In use"
    DUE_SOON = "DUE_SOON", "Calibration due soon"
    OVERDUE = "OVERDUE", "Calibration overdue"
    COLLECTED = "COLLECTED", "Collected from user"
    SENT_TO_LAB = "SENT_TO_LAB", "Sent to laboratory"
    RETURNED = "RETURNED", "Returned from laboratory"
    QUARANTINED = "QUARANTINED", "Quarantined"
    UNDER_REPAIR = "UNDER_REPAIR", "Under repair"
    NOT_USABLE = "NOT_USABLE", "Not usable"
    RETIRED = "RETIRED", "Retired"


class Instrument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    asset_number = models.CharField(
        max_length=80,
        unique=True,
        help_text="Internal instrument / gauge identification number.",
    )
    purchase_serial_number = models.CharField(max_length=120, blank=True)
    manufacturer_serial_number = models.CharField(max_length=120, blank=True)
    description = models.CharField(max_length=255)
    category = models.ForeignKey(
        InstrumentCategory,
        on_delete=models.PROTECT,
        related_name="instruments",
    )
    manufacturer = models.CharField(max_length=160, blank=True)
    model_number = models.CharField(max_length=120, blank=True)
    measurement_range = models.CharField(max_length=160, blank=True)
    least_count = models.CharField(max_length=100, blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    calibration_frequency_days = models.PositiveIntegerField(
        default=365,
        validators=[MinValueValidator(1)],
    )
    department = models.ForeignKey(
        DEPARTMENT_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="calibration_instruments",
    )
    location = models.CharField(max_length=160, blank=True)
    custodian = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="custodied_instruments",
    )
    monitor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="monitored_instruments",
    )
    latest_calibration_date = models.DateField(null=True, blank=True)
    next_due_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=30,
        choices=InstrumentStatus.choices,
        default=InstrumentStatus.IN_USE,
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_calibration_instruments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["asset_number"]
        permissions = [
            ("print_calibration_master_list", "Can print calibration master list"),
        ]

    def __str__(self) -> str:
        return f"{self.asset_number} - {self.description}"

    @property
    def days_to_due(self):
        if not self.next_due_date:
            return None
        return (self.next_due_date - timezone.localdate()).days

    def refresh_due_status(self, save=True):
        if not self.is_active or self.status in {
            InstrumentStatus.NOT_USABLE,
            InstrumentStatus.RETIRED,
            InstrumentStatus.SENT_TO_LAB,
            InstrumentStatus.COLLECTED,
            InstrumentStatus.UNDER_REPAIR,
        }:
            return self.status
        days = self.days_to_due
        if days is None:
            new_status = InstrumentStatus.IN_USE
        elif days < 0:
            new_status = InstrumentStatus.OVERDUE
        elif days <= 15:
            new_status = InstrumentStatus.DUE_SOON
        else:
            new_status = InstrumentStatus.IN_USE
        if self.status != new_status:
            self.status = new_status
            if save:
                Instrument.objects.filter(pk=self.pk).update(status=new_status)
        return new_status


class CalibrationCycleStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    COLLECTED = "COLLECTED", "Collected from user"
    SENT_TO_LAB = "SENT_TO_LAB", "Sent to laboratory"
    RETURNED = "RETURNED", "Returned from laboratory"
    VERIFIED = "VERIFIED", "QC verified"
    RELEASED = "RELEASED", "Returned to production"
    CANCELLED = "CANCELLED", "Cancelled"


class CalibrationResult(models.TextChoices):
    REUSABLE = "REUSABLE", "Reusable"
    REPAIRED = "REPAIRED", "Repaired and reusable"
    NOT_USABLE = "NOT_USABLE", "Not usable"


class CalibrationCycle(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    instrument = models.ForeignKey(
        Instrument,
        on_delete=models.PROTECT,
        related_name="calibration_cycles",
    )
    cycle_number = models.PositiveIntegerField(editable=False)
    status = models.CharField(
        max_length=30,
        choices=CalibrationCycleStatus.choices,
        default=CalibrationCycleStatus.DRAFT,
    )
    collected_from_user_date = models.DateField(null=True, blank=True)
    sent_to_lab_date = models.DateField(null=True, blank=True)
    laboratory = models.ForeignKey(
        CalibrationLaboratory,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="calibration_cycles",
    )
    returned_from_lab_date = models.DateField(null=True, blank=True)
    calibration_date = models.DateField(null=True, blank=True)
    next_due_date = models.DateField(null=True, blank=True)
    certificate_number = models.CharField(max_length=160, blank=True)
    certificate_file = models.FileField(
        upload_to=certificate_upload_path,
        null=True,
        blank=True,
    )
    result = models.CharField(
        max_length=30,
        choices=CalibrationResult.choices,
        blank=True,
    )
    repair_details = models.TextField(blank=True)
    qc_comments = models.TextField(blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_calibration_cycles",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    returned_to_production_date = models.DateField(null=True, blank=True)
    put_back_in_service_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_calibration_cycles",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-cycle_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["instrument", "cycle_number"],
                name="unique_calibration_cycle_number",
            )
        ]
        permissions = [
            ("verify_calibration_cycle", "Can verify calibration cycle"),
            ("release_calibrated_instrument", "Can release calibrated instrument"),
        ]

    def __str__(self) -> str:
        return f"{self.instrument.asset_number} - Cycle {self.cycle_number}"

    def clean(self):
        super().clean()
        errors = {}
        if self.sent_to_lab_date and self.collected_from_user_date:
            if self.sent_to_lab_date < self.collected_from_user_date:
                errors["sent_to_lab_date"] = "Sent date cannot be before collection date."
        if self.returned_from_lab_date and self.sent_to_lab_date:
            if self.returned_from_lab_date < self.sent_to_lab_date:
                errors["returned_from_lab_date"] = "Return date cannot be before sent date."
        if self.next_due_date and self.calibration_date:
            if self.next_due_date <= self.calibration_date:
                errors["next_due_date"] = "Next due date must be after calibration date."
        if self.status in {CalibrationCycleStatus.VERIFIED, CalibrationCycleStatus.RELEASED}:
            required = {
                "calibration_date": self.calibration_date,
                "next_due_date": self.next_due_date,
                "result": self.result,
                "certificate_file": self.certificate_file,
            }
            for field, value in required.items():
                if not value:
                    errors[field] = "This field is required for QC verification."
        if self.result == CalibrationResult.REPAIRED and not self.repair_details.strip():
            errors["repair_details"] = "Enter repair details."
        if errors:
            raise ValidationError(errors)

    @transaction.atomic
    def save(self, *args, **kwargs):
        adding = self._state.adding
        old_status = None
        if not adding and self.pk:
            old_status = (
                CalibrationCycle.objects.filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )
        if adding and not self.cycle_number:
            last = (
                CalibrationCycle.objects.select_for_update()
                .filter(instrument=self.instrument)
                .order_by("-cycle_number")
                .first()
            )
            self.cycle_number = (last.cycle_number if last else 0) + 1
        if self.status == CalibrationCycleStatus.VERIFIED and not self.verified_at:
            self.verified_at = timezone.now()
        self.full_clean()
        super().save(*args, **kwargs)

        status_to_instrument = {
            CalibrationCycleStatus.COLLECTED: InstrumentStatus.COLLECTED,
            CalibrationCycleStatus.SENT_TO_LAB: InstrumentStatus.SENT_TO_LAB,
            CalibrationCycleStatus.RETURNED: InstrumentStatus.RETURNED,
        }
        instrument_status = status_to_instrument.get(self.status)
        update_values = {}
        if instrument_status:
            update_values["status"] = instrument_status
        if self.status in {CalibrationCycleStatus.VERIFIED, CalibrationCycleStatus.RELEASED}:
            update_values.update(
                latest_calibration_date=self.calibration_date,
                next_due_date=self.next_due_date,
                status=(
                    InstrumentStatus.NOT_USABLE
                    if self.result == CalibrationResult.NOT_USABLE
                    else InstrumentStatus.IN_USE
                ),
            )
        if update_values:
            Instrument.objects.filter(pk=self.instrument_id).update(**update_values)

        if old_status != self.status:
            InstrumentHistoryEvent.objects.create(
                instrument=self.instrument,
                calibration_cycle=self,
                event_type=self.status,
                event_date=timezone.localdate(),
                performed_by=self.verified_by or self.created_by,
                details={
                    "result": self.result,
                    "certificate_number": self.certificate_number,
                    "calibration_date": str(self.calibration_date or ""),
                    "next_due_date": str(self.next_due_date or ""),
                },
            )


class InstrumentHistoryEvent(models.Model):
    instrument = models.ForeignKey(
        Instrument,
        on_delete=models.CASCADE,
        related_name="history_events",
    )
    calibration_cycle = models.ForeignKey(
        CalibrationCycle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="history_events",
    )
    event_type = models.CharField(max_length=50)
    event_date = models.DateField(default=timezone.localdate)
    details = models.JSONField(default=dict, blank=True)
    remarks = models.TextField(blank=True)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="calibration_history_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-event_date", "-created_at"]

    def __str__(self) -> str:
        return f"{self.instrument.asset_number} - {self.event_type}"


class CalibrationAlertType(models.TextChoices):
    DUE_SOON = "DUE_SOON", "Due within 15 days"
    OVERDUE = "OVERDUE", "Overdue"
    CERTIFICATE_PENDING = "CERTIFICATE_PENDING", "Certificate pending"
    VERIFICATION_PENDING = "VERIFICATION_PENDING", "QC verification pending"


class CalibrationAlert(models.Model):
    instrument = models.ForeignKey(
        Instrument,
        on_delete=models.CASCADE,
        related_name="alerts",
    )
    alert_type = models.CharField(max_length=40, choices=CalibrationAlertType.choices)
    due_date = models.DateField(null=True, blank=True)
    message = models.TextField()
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="calibration_alerts",
    )
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["is_resolved", "due_date", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["instrument", "alert_type"],
                condition=Q(is_resolved=False),
                name="unique_open_calibration_alert_type",
            )
        ]

    def __str__(self) -> str:
        return f"{self.instrument.asset_number} - {self.get_alert_type_display()}"
