from datetime import date

from django.core.management.base import (
    BaseCommand,
    CommandError,
)

from core.notifications import (
    send_daily_vdrl_reminders,
)


class Command(BaseCommand):
    help = (
        "Send daily VDRL document and CRS "
        "reminder/escalation digests."
    )


    def add_arguments(
        self,
        parser,
    ):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=(
                "Show who would receive reminders "
                "without sending email."
            ),
        )


        parser.add_argument(
            "--force",
            action="store_true",
            help=(
                "Send again even if a successful "
                "digest was already sent today."
            ),
        )


        parser.add_argument(
            "--date",
            type=str,
            help=(
                "Optional test date in YYYY-MM-DD format."
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
                    options["date"]
                )

            except ValueError as exc:
                raise CommandError(
                    (
                        "--date must use "
                        "YYYY-MM-DD format."
                    )
                ) from exc


        result = (
            send_daily_vdrl_reminders(
                run_date=run_date,
                dry_run=(
                    options["dry_run"]
                ),
                force=(
                    options["force"]
                ),
            )
        )


        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(
                    (
                        "DRY RUN — "
                        "No emails were sent."
                    )
                )
            )


            self.stdout.write(
                (
                    "Recipients requiring attention: "
                    f"{result['recipient_count']}"
                )
            )


            for preview in result[
                "previews"
            ]:
                self.stdout.write(
                    ""
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        (
                            f"Recipient: "
                            f"{preview['recipient_name']} "
                            f"<{preview['recipient_email']}>"
                        )
                    )
                )

                self.stdout.write(
                    (
                        f"Subject: "
                        f"{preview['subject']}"
                    )
                )

                self.stdout.write(
                    (
                        f"Actions: "
                        f"{preview['item_count']}"
                    )
                )


                for alert in preview[
                    "alerts"
                ]:
                    self.stdout.write(
                        (
                            "  - "
                            f"[{alert['severity_label']}] "
                            f"{alert['sales_order']} | "
                            f"{alert['title']} | "
                            f"{alert['timing_text']}"
                        )
                    )


            return


        self.stdout.write(
            self.style.SUCCESS(
                (
                    "VDRL reminder run completed."
                )
            )
        )


        self.stdout.write(
            (
                f"Recipients found: "
                f"{result['recipient_count']}"
            )
        )

        self.stdout.write(
            (
                f"Sent: "
                f"{result['sent']}"
            )
        )

        self.stdout.write(
            (
                f"Skipped: "
                f"{result['skipped']}"
            )
        )

        self.stdout.write(
            (
                f"Failed: "
                f"{result['failed']}"
            )
        )