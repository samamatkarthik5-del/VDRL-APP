from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Instrument, InstrumentHistoryEvent


@receiver(post_save, sender=Instrument)
def create_initial_history(sender, instance, created, **kwargs):
    if created:
        InstrumentHistoryEvent.objects.create(
            instrument=instance,
            event_type="MASTER_CREATED",
            event_date=instance.purchase_date or timezone.localdate(),
            performed_by=instance.created_by,
            details={
                "purchase_serial_number": instance.purchase_serial_number,
                "manufacturer_serial_number": instance.manufacturer_serial_number,
                "purchase_date": str(instance.purchase_date or ""),
            },
        )
