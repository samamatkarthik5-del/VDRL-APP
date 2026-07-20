from django.core.management.base import (
    BaseCommand,
)

from core.models import (
    DocumentWorkflow,
    SalesOrderVDRLDocument,
)


class Command(BaseCommand):
    help = (
        "Create workflow records for existing "
        "VDRL documents."
    )

    def handle(
        self,
        *args,
        **options,
    ):
        created_count = 0
        existing_count = 0

        for document in (
            SalesOrderVDRLDocument
            .objects
            .all()
            .iterator()
        ):
            _, created = (
                DocumentWorkflow.objects
                .get_or_create(
                    document=document,
                )
            )

            if created:
                created_count += 1
            else:
                existing_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                (
                    f"Created: {created_count}, "
                    f"already existed: "
                    f"{existing_count}"
                )
            )
        )