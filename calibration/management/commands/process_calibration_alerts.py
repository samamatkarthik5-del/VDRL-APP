from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from calibration.models import (
    CalibrationAlert,
    CalibrationAlertType,
    Instrument,
    InstrumentStatus,
)


class Command(BaseCommand):
    help = "Create 15-day due reminders and overdue calibration alerts."

    def handle(self, *args, **options):
        today = timezone.localdate()
        due_limit = today + timedelta(days=15)
        created = 0
        resolved = 0

        for instrument in Instrument.objects.filter(is_active=True):
            instrument.refresh_due_status()
            if not instrument.next_due_date:
                continue

            if instrument.next_due_date < today:
                alert_type = CalibrationAlertType.OVERDUE
                message = (
                    f"Calibration is overdue from {instrument.next_due_date:%d-%b-%Y}. "
                    "Collect and quarantine the instrument until calibration is completed."
                )
            elif instrument.next_due_date <= due_limit:
                alert_type = CalibrationAlertType.DUE_SOON
                message = (
                    f"Calibration is due on {instrument.next_due_date:%d-%b-%Y}. "
                    "Arrange collection and external laboratory calibration."
                )
            else:
                updated = CalibrationAlert.objects.filter(
                    instrument=instrument,
                    alert_type__in=[CalibrationAlertType.DUE_SOON, CalibrationAlertType.OVERDUE],
                    is_resolved=False,
                ).update(is_resolved=True, resolved_at=timezone.now())
                resolved += updated
                continue

            # Resolve the opposite alert type, then create the current one if missing.
            opposite = (
                CalibrationAlertType.DUE_SOON
                if alert_type == CalibrationAlertType.OVERDUE
                else CalibrationAlertType.OVERDUE
            )
            resolved += CalibrationAlert.objects.filter(
                instrument=instrument,
                alert_type=opposite,
                is_resolved=False,
            ).update(is_resolved=True, resolved_at=timezone.now())

            _, was_created = CalibrationAlert.objects.get_or_create(
                instrument=instrument,
                alert_type=alert_type,
                is_resolved=False,
                defaults={
                    "due_date": instrument.next_due_date,
                    "message": message,
                    "assigned_to": instrument.monitor or instrument.custodian,
                },
            )
            if was_created:
                created += 1

        self.stdout.write(self.style.SUCCESS(f"Created {created} alerts; resolved {resolved}."))
