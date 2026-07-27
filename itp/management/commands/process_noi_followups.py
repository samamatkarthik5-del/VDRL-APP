from django.core.management.base import BaseCommand

from itp.services.reminders import process_noi_followups


class Command(BaseCommand):
    help = (
        "Create next-day NOI completion confirmation tasks, send reminders, "
        "and escalate overdue confirmations."
    )

    def handle(self, *args, **options):
        result = process_noi_followups()
        self.stdout.write(
            self.style.SUCCESS(
                "NOI follow-ups processed: "
                f"prompted={result['prompted']}, "
                f"overdue={result['overdue']}, "
                f"escalated={result['escalated']}"
            )
        )
