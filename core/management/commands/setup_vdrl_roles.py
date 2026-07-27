from django.contrib.auth.models import (
    Group,
    Permission,
)
from django.core.management.base import (
    BaseCommand,
)


class Command(BaseCommand):
    help = (
        "Create or update the standard "
        "VDRL user roles and permissions."
    )


    def handle(
        self,
        *args,
        **options,
    ):
        all_core_permissions = (
            Permission.objects
            .filter(
                content_type__app_label=(
                    "core"
                )
            )
        )


        standard_view_permissions = (
            all_core_permissions
            .filter(
                codename__startswith=(
                    "view_"
                )
            )
            .exclude(
                codename=(
                    "view_all_vdrl_data"
                )
            )
        )


        custom_permissions = {
            permission.codename:
            permission

            for permission
            in all_core_permissions.filter(
               codename__in=[
    "view_all_vdrl_data",
    (
        "manage_vdrl_"
        "document_details"
    ),
    "manage_vdrl_workflow",
    "manage_vdrl_files",
    "manage_crs",
    (
        "view_management_"
        "reports"
    ),
    "bulk_import_vdrl_data",
    "view_audit_log",
    "export_audit_log",
]
            )
        }


        def permission_list(
            *codenames,
        ):
            permissions = list(
                standard_view_permissions
            )

            for codename in codenames:
                permission = (
                    custom_permissions.get(
                        codename
                    )
                )

                if permission:
                    permissions.append(
                        permission
                    )

            return permissions


        role_permissions = {
            "VDRL Management": list(
                all_core_permissions
            ),

            "Project Managers": (
                permission_list(
                    (
                        "manage_vdrl_"
                        "document_details"
                    ),
                    "manage_vdrl_workflow",
                    "manage_vdrl_files",
                    "manage_crs",
                    (
                        "view_management_"
                        "reports"
                    ),
                    "bulk_import_vdrl_data",
                    "view_audit_log",
                    "export_audit_log"
                )
            ),

            "Document Controllers": (
                permission_list(
                    (
                        "manage_vdrl_"
                        "document_details"
                    ),
                    "manage_vdrl_workflow",
                    "manage_vdrl_files",
                    "manage_crs",
                    (
                        "view_management_"
                        "reports"
                    ),
                    "bulk_import_vdrl_data",
                    "view_audit_log",
                    "export_audit_log"
                    "assign_document_department",
                    "record_customer_document_action",
                )
            ),

            "Department Managers": (
                permission_list(
                    (
                        "manage_vdrl_"
                        "document_details"
                    ),
                    "manage_vdrl_workflow",
                    "manage_vdrl_files",
                    "manage_crs",
                    (
                        "view_management_"
                        "reports"
                    ),
                    "view_audit_log",
                    "export_audit_log",
                    "assign_document_contributor",
                    "reassign_document_contributor",
                    "review_department_document",
                )
            ),

            "Contributors": (
                permission_list(
                    "manage_vdrl_workflow",
                    "manage_vdrl_files",
                    "manage_crs",
                    "raise_document_open_point",
                    "close_document_open_point",
                )
            ),

            "VDRL Viewers": (
                permission_list(
                    (
                        "view_management_"
                        "reports"
                    ),
                )
            ),

            "Application Engineers":(
                permission_list(
                    (
                        "respond_document_open_point",
                    )
                )
            )
        }


        for (
            role_name,
            permissions,
        ) in role_permissions.items():

            group, created = (
                Group.objects.get_or_create(
                    name=role_name
                )
            )

            group.permissions.set(
                permissions
            )

            status = (
                "Created"
                if created
                else "Updated"
            )

            self.stdout.write(
                self.style.SUCCESS(
                    (
                        f"{status}: "
                        f"{role_name} "
                        f"({len(permissions)} "
                        "permissions)"
                    )
                )
            )


        self.stdout.write(
            self.style.SUCCESS(
                (
                    "VDRL role configuration "
                    "completed successfully."
                )
            )
        )