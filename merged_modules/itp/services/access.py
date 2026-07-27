from __future__ import annotations

from django.conf import settings
from django.utils.module_loading import import_string

from operations_portal.models import ModuleCode
from operations_portal.services import get_user_module_access, has_module_access


def can_access_sales_order(user, sales_order) -> bool:
    """
    Combine module-level authorisation with Sales Order-level access.

    A custom checker can be configured through ITP_SALES_ORDER_ACCESS_CHECKER.
    Without one, access is allowed for users assigned to the Sales Order as
    project manager/document controller, users assigned to a VDRL document
    under the order, or users granted "all Sales Orders" for ITP/NOI.
    """
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    if not has_module_access(user, ModuleCode.ITP_NOI):
        return False

    checker_path = getattr(settings, "ITP_SALES_ORDER_ACCESS_CHECKER", "")
    if checker_path:
        checker = import_string(checker_path)
        return bool(checker(user, sales_order))

    access = get_user_module_access(user)
    if access and access.itp_all_sales_orders:
        return True

    if getattr(sales_order, "project_manager_id", None) == user.id:
        return True
    if getattr(sales_order, "document_controller_id", None) == user.id:
        return True

    vdrls = getattr(sales_order, "vdrls", None)
    if vdrls is not None:
        try:
            if vdrls.filter(documents__responsible_person=user).exists():
                return True
            profile = getattr(user, "employee_profile", None)
            department_id = getattr(profile, "department_id", None)
            if department_id and vdrls.filter(
                documents__responsible_department_id=department_id
            ).exists():
                return True
        except Exception:
            pass

    return False
