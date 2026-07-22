from django.db.models import Q

from .models import (
    SalesOrder,
    SalesOrderVDRL,
    SalesOrderVDRLDocument,
)


def has_global_vdrl_access(user):
    if not user or not user.is_authenticated:
        return False

    return bool(
        user.is_superuser
        or user.has_perm(
            "core.view_all_vdrl_data"
        )
    )


def user_has_global_vdrl_access(user):
    return has_global_vdrl_access(user)


def _sales_order_access_query(user):
    return (
        Q(authorized_users=user)
        | Q(
            project_team__project_manager=user
        )
        | Q(application_engineer=user)
        | Q(document_controller=user)
        | Q(
            backup_document_controllers=user
        )
    )


def filter_sales_orders_for_user(
    user,
    queryset=None,
):
    if queryset is None:
        queryset = SalesOrder.objects.all()

    if not user or not user.is_authenticated:
        return queryset.none()

    if has_global_vdrl_access(user):
        return queryset

    return (
        queryset
        .filter(
            _sales_order_access_query(user)
        )
        .distinct()
    )


def filter_vdrls_for_user(
    user,
    queryset=None,
):
    if queryset is None:
        queryset = SalesOrderVDRL.objects.all()

    if not user or not user.is_authenticated:
        return queryset.none()

    if has_global_vdrl_access(user):
        return queryset

    access_query = (
        Q(
            sales_order__authorized_users=user
        )
        | Q(
            sales_order__project_team__project_manager=user
        )
        | Q(
            sales_order__application_engineer=user
        )
        | Q(
            sales_order__document_controller=user
        )
        | Q(
            sales_order__backup_document_controllers=user
        )
        | Q(
            sales_order__sales_manager=user
        )
    )

    return (
        queryset
        .filter(access_query)
        .distinct()
    )


def filter_documents_for_user(
    user,
    queryset=None,
):
    if queryset is None:
        queryset = (
            SalesOrderVDRLDocument.objects.all()
        )

    if not user or not user.is_authenticated:
        return queryset.none()

    if has_global_vdrl_access(user):
        return queryset

    access_query = (
        Q(
            vdrl__sales_order__authorized_users=user
        )
        | Q(
            vdrl__sales_order__project_team__project_manager=user
        )
        | Q(
            vdrl__sales_order__application_engineer=user
        )
        | Q(
            vdrl__sales_order__document_controller=user
        )
        | Q(
            vdrl__sales_order__backup_document_controllers=user
        )
        | Q(
            vdrl__sales_order__sales_manager=user
        )
    )

    return (
        queryset
        .filter(access_query)
        .distinct()
    )


def can_view_sales_order(
    user,
    sales_order,
):
    if sales_order is None:
        return False

    return filter_sales_orders_for_user(
        user,
        SalesOrder.objects.filter(
            pk=sales_order.pk,
        ),
    ).exists()


def can_view_vdrl(
    user,
    vdrl,
):
    if vdrl is None:
        return False

    return can_view_sales_order(
        user,
        vdrl.sales_order,
    )


def can_view_document(
    user,
    document,
):
    if document is None:
        return False

    return can_view_sales_order(
        user,
        document.vdrl.sales_order,
    )


def can_manage_document_details(
    user,
    document,
):
    return bool(
        can_view_document(
            user,
            document,
        )
        and (
            user.is_superuser
            or user.has_perm(
                "core.manage_vdrl_document_details"
            )
        )
    )


def can_edit_document_details(
    user,
    document,
):
    return can_manage_document_details(
        user,
        document,
    )


def can_manage_workflow(
    user,
    document,
):
    return bool(
        can_view_document(
            user,
            document,
        )
        and (
            user.is_superuser
            or user.has_perm(
                "core.manage_vdrl_workflow"
            )
        )
    )


def can_manage_document_workflow(
    user,
    document,
):
    return can_manage_workflow(
        user,
        document,
    )


def can_manage_files(
    user,
    document,
):
    return bool(
        can_view_document(
            user,
            document,
        )
        and (
            user.is_superuser
            or user.has_perm(
                "core.manage_vdrl_files"
            )
        )
    )


def can_manage_document_files(
    user,
    document,
):
    return can_manage_files(
        user,
        document,
    )


def can_manage_crs(
    user,
    document,
):
    return bool(
        can_view_document(
            user,
            document,
        )
        and (
            user.is_superuser
            or user.has_perm(
                "core.manage_crs"
            )
        )
    )


def can_manage_crs_for_document(
    user,
    document,
):
    return can_manage_crs(
        user,
        document,
    )


def can_view_management_reports(user):
    if not user or not user.is_authenticated:
        return False

    return bool(
        user.is_superuser
        or user.has_perm(
            "core.view_management_reports"
        )
    )


def can_view_reports(user):
    return can_view_management_reports(user)


def can_bulk_import_vdrl_data(user):
    if not user or not user.is_authenticated:
        return False

    return bool(
        user.is_superuser
        or user.has_perm(
            "core.bulk_import_vdrl_data"
        )
    )


def can_bulk_import(user):
    return can_bulk_import_vdrl_data(user)


def can_view_audit_log(user):
    if not user or not user.is_authenticated:
        return False

    return bool(
        user.is_superuser
        or user.has_perm(
            "core.view_audit_log"
        )
    )