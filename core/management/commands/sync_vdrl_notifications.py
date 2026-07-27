from datetime import date

from django.core.management.base import (
    BaseCommand,
    CommandError,
)

from core.notifications import (
    sync_in_app_notifications,
)


class Command(BaseCommand):
    help = (
        "Create or refresh in-app VDRL "
        "due and overdue notifications."
    )

    def add_arguments(
        self,
        parser,
    ):
        parser.add_argument(
            "--date",
            type=str,
            help=(
                "Optional test date using "
                "YYYY-MM-DD format."
            ),
        )

    def handle(
        self,
        *args,
        **options,
    ):
        run_date = None

        if options["date"]:
            try:
                run_date = date.fromisoformat(
                    options[
                        "date"
                    ]
                )

            except ValueError as exc:
                raise CommandError(
                    (
                        "--date must use "
                        "YYYY-MM-DD format."
                    )
                ) from exc

        result = (
            sync_in_app_notifications(
                run_date=run_date
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                (
                    "In-app notification sync "
                    "completed."
                )
            )
        )

        self.stdout.write(
            (
                "Recipients: "
                f"{result['recipients']}"
            )
        )

        self.stdout.write(
            (
                "Notifications created or refreshed: "
                f"{result['notifications']}"
            )
        )