from django.contrib.auth.models import (
    AnonymousUser,
)

from .models import (
    SalesOrder,
    SalesOrderVDRLDocument,
)


ROLE_VDRL_MANAGEMENT = "VDRL Management"

ROLE_PROJECT_MANAGERS = "Project Managers"

ROLE_DOCUMENT_CONTROLLERS = (
    "Document Controllers"
)

ROLE_DEPARTMENT_MANAGERS = (
    "Department Managers"
)

ROLE_CONTRIBUTORS = "Contributors"

ROLE_VDRL_VIEWERS = "VDRL Viewers"


def user_in_group(
    user,
    group_name,
):
    if (
        not user
        or isinstance(
            user,
            AnonymousUser,
        )
        or not user.is_authenticated
    ):
        return False

    return (
        user.groups
        .filter(
            name=group_name
        )
        .exists()
    )


def get_user_department(
    user,
):
    """
    Retained for forms, reports and display.

    Department membership no longer grants
    visibility to Sales Orders or documents.
    """

    if (
        not user
        or not user.is_authenticated
    ):
        return None

    try:
        return (
            user
            .employee_profile
            .department
        )

    except (
        AttributeError,
        ObjectDoesNotExist,
    ):
        return None


# Import here to support ObjectDoesNotExist above.
from django.core.exceptions import (
    ObjectDoesNotExist,
)


# =========================================================
# GLOBAL ACCESS
# =========================================================

def user_has_global_vdrl_access(
    user,
):
    """
    Only superusers or users with the explicit
    global permission may view every Sales Order.

    Group membership alone does not grant global
    record visibility.
    """

    if (
        not user
        or not user.is_authenticated
    ):
        return False

    return bool(
        user.is_superuser
        or user.has_perm(
            "core.view_all_vdrl_data"
        )
    )


# =========================================================
# SALES ORDER FILTERING
# =========================================================

def filter_sales_orders_for_user(
    user,
    queryset=None,
):
    """
    Restrict normal users to Sales Orders where
    they appear in authorized_users.
    """

    if queryset is None:
        queryset = (
            SalesOrder
            .objects
            .all()
        )

    if (
        not user
        or not user.is_authenticated
    ):
        return queryset.none()

    if user_has_global_vdrl_access(
        user
    ):
        return queryset

    return (
        queryset
        .filter(
            authorized_users=user
        )
        .distinct()
    )


def can_view_sales_order(
    user,
    sales_order,
):
    if sales_order is None:
        return False

    return (
        filter_sales_orders_for_user(
            user,
            SalesOrder.objects.filter(
                pk=sales_order.pk
            ),
        )
        .exists()
    )


# =========================================================
# DOCUMENT FILTERING
# =========================================================

def filter_documents_for_user(
    user,
    queryset=None,
):
    """
    Restrict documents through the related
    Sales Order's authorized_users field.
    """

    if queryset is None:
        queryset = (
            SalesOrderVDRLDocument
            .objects
            .all()
        )

    if (
        not user
        or not user.is_authenticated
    ):
        return queryset.none()

    if user_has_global_vdrl_access(
        user
    ):
        return queryset

    return (
        queryset
        .filter(
            vdrl__sales_order__authorized_users=(
                user
            )
        )
        .distinct()
    )


def can_view_document(
    user,
    document,
):
    if document is None:
        return False

    return (
        filter_documents_for_user(
            user,
            (
                SalesOrderVDRLDocument
                .objects
                .filter(
                    pk=document.pk
                )
            ),
        )
        .exists()
    )


# =========================================================
# ACTION PERMISSIONS
# =========================================================

def can_edit_document_details(
    user,
    document,
):
    return bool(
        can_view_document(
            user,
            document,
        )
        and user.has_perm(
            (
                "core."
                "manage_vdrl_document_details"
            )
        )
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
        and user.has_perm(
            "core.manage_vdrl_workflow"
        )
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
        and user.has_perm(
            "core.manage_vdrl_files"
        )
    )


def can_manage_crs_for_document(
    user,
    document,
):
    return bool(
        can_view_document(
            user,
            document,
        )
        and user.has_perm(
            "core.manage_crs"
        )
    )