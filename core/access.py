from .models import (
    SalesOrder,
    SalesOrderVDRL,
    SalesOrderVDRLDocument,
)


def user_has_global_vdrl_access(user):
    """Return True for superusers and VDRL management users."""
    if not user or not user.is_authenticated:
        return False

    return bool(
        user.is_superuser
        or user.has_perm(
            "core.view_all_vdrl_data"
        )
    )


def filter_sales_orders_for_user(
    user,
    queryset=None,
):
    """Return only Sales Orders the user is authorized to access."""
    if queryset is None:
        queryset = SalesOrder.objects.all()

    if not user or not user.is_authenticated:
        return queryset.none()

    if user_has_global_vdrl_access(user):
        return queryset

    return (
        queryset
        .filter(
            authorized_users=user,
        )
        .distinct()
    )


def filter_vdrls_for_user(
    user,
    queryset=None,
):
    """Return only VDRLs belonging to authorized Sales Orders."""
    if queryset is None:
        queryset = SalesOrderVDRL.objects.all()

    if not user or not user.is_authenticated:
        return queryset.none()

    if user_has_global_vdrl_access(user):
        return queryset

    return (
        queryset
        .filter(
            sales_order__authorized_users=user,
        )
        .distinct()
    )


def filter_documents_for_user(
    user,
    queryset=None,
):
    """Return only documents belonging to authorized Sales Orders."""
    if queryset is None:
        queryset = SalesOrderVDRLDocument.objects.all()

    if not user or not user.is_authenticated:
        return queryset.none()

    if user_has_global_vdrl_access(user):
        return queryset

    return (
        queryset
        .filter(
            vdrl__sales_order__authorized_users=user,
        )
        .distinct()
    )


def can_view_sales_order(
    user,
    sales_order,
):
    """Check whether the user may view one Sales Order."""
    if not user or not user.is_authenticated:
        return False

    if user_has_global_vdrl_access(user):
        return True

    if sales_order is None:
        return False

    return sales_order.authorized_users.filter(
        pk=user.pk,
    ).exists()


def can_view_vdrl(
    user,
    vdrl,
):
    """Check whether the user may view one VDRL."""
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
    """Check whether the user may view one VDRL document."""
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
    """Compatibility alias used by existing views."""
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
    """Compatibility alias used by some views."""
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
    """Compatibility alias used by some views."""
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
    """Compatibility alias used by older report views."""
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
    """Compatibility alias used by older import views."""
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

def can_manage_crs_for_document(
    user,
    document,
):
    """Compatibility alias used by existing CRS views."""
    return can_manage_crs(
        user,
        document,
    )