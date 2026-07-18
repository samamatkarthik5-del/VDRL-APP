from django.db.models import Q

from .models import (
    SalesOrder,
    SalesOrderVDRLDocument,
)


ROLE_MANAGEMENT = "VDRL Management"

ROLE_PROJECT_MANAGER = (
    "Project Managers"
)

ROLE_DOCUMENT_CONTROLLER = (
    "Document Controllers"
)

ROLE_DEPARTMENT_MANAGER = (
    "Department Managers"
)

ROLE_CONTRIBUTOR = (
    "Contributors"
)

ROLE_VIEWER = (
    "VDRL Viewers"
)


def user_in_group(
    user,
    group_name,
):
    if not user.is_authenticated:
        return False

    return (
        user.groups
        .filter(
            name=group_name
        )
        .exists()
    )


def get_user_department(user):
    """
    Return the user's EmployeeProfile department,
    or None when no profile/department exists.
    """

    if not user.is_authenticated:
        return None

    try:
        profile = user.employee_profile

    except Exception:
        return None

    return profile.department


def user_has_global_vdrl_access(user):
    """
    Superusers and users with the global VDRL
    permission can access all operational records.
    """

    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    return user.has_perm(
        "core.view_all_vdrl_data"
    )


def filter_documents_for_user(
    user,
    queryset=None,
):
    """
    Return only VDRL documents that the user is
    permitted to see.
    """

    if queryset is None:
        queryset = (
            SalesOrderVDRLDocument
            .objects
            .all()
        )

    if not user.is_authenticated:
        return queryset.none()

    if user_has_global_vdrl_access(
        user
    ):
        return queryset

    department = get_user_department(
        user
    )

    access_query = (
        Q(
            vdrl__sales_order__project_manager=(
                user
            )
        )
        |
        Q(
            vdrl__sales_order__document_controller=(
                user
            )
        )
        |
        Q(
            responsible_person=user
        )
        |
        Q(
            crs_registers__comments__assigned_person=(
                user
            )
        )
    )

    if department:
        access_query |= (
            Q(
                responsible_department=(
                    department
                )
            )
            |
            Q(
                crs_registers__comments__assigned_department=(
                    department
                )
            )
        )

    return (
        queryset
        .filter(
            access_query
        )
        .distinct()
    )


def filter_sales_orders_for_user(
    user,
    queryset=None,
):
    """
    Return only Sales Orders related to the user.
    """

    if queryset is None:
        queryset = (
            SalesOrder
            .objects
            .all()
        )

    if not user.is_authenticated:
        return queryset.none()

    if user_has_global_vdrl_access(
        user
    ):
        return queryset

    department = get_user_department(
        user
    )

    access_query = (
        Q(
            project_manager=user
        )
        |
        Q(
            document_controller=user
        )
        |
        Q(
            vdrls__documents__responsible_person=(
                user
            )
        )
        |
        Q(
            vdrls__documents__crs_registers__comments__assigned_person=(
                user
            )
        )
    )

    if department:
        access_query |= (
            Q(
                vdrls__documents__responsible_department=(
                    department
                )
            )
            |
            Q(
                vdrls__documents__crs_registers__comments__assigned_department=(
                    department
                )
            )
        )

    return (
        queryset
        .filter(
            access_query
        )
        .distinct()
    )


def can_view_sales_order(
    user,
    sales_order,
):
    if not user.is_authenticated:
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


def can_view_document(
    user,
    document,
):
    if not user.is_authenticated:
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


def can_edit_document_details(
    user,
    document,
):
    return (
        user.has_perm(
            (
                "core."
                "manage_vdrl_document_details"
            )
        )
        and can_view_document(
            user,
            document,
        )
    )


def can_manage_workflow(
    user,
    document,
):
    return (
        user.has_perm(
            "core.manage_vdrl_workflow"
        )
        and can_view_document(
            user,
            document,
        )
    )


def can_manage_files(
    user,
    document,
):
    return (
        user.has_perm(
            "core.manage_vdrl_files"
        )
        and can_view_document(
            user,
            document,
        )
    )


def can_manage_crs_for_document(
    user,
    document,
):
    return (
        user.has_perm(
            "core.manage_crs"
        )
        and can_view_document(
            user,
            document,
        )
    )