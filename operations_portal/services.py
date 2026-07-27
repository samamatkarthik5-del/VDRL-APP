from __future__ import annotations

from typing import Optional

from .models import ModuleCode, UserModuleAccess


def get_user_module_access(user) -> Optional[UserModuleAccess]:
    if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return None
    try:
        return user.module_access
    except UserModuleAccess.DoesNotExist:
        return None


def has_module_access(user, module_code: str) -> bool:
    if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    access = get_user_module_access(user)
    return bool(access and access.has_module(module_code))


def module_flags(user) -> dict[str, bool]:
    return {
        "vdrl": has_module_access(user, ModuleCode.VDRL),
        "itp_noi": has_module_access(user, ModuleCode.ITP_NOI),
        "calibration": has_module_access(user, ModuleCode.CALIBRATION),
    }
