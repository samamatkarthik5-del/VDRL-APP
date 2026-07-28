from __future__ import annotations

from django.conf import settings
from django.core.exceptions import PermissionDenied

from .models import ModuleCode
from .services import has_module_access

# Configurable so this keeps working even if your VDRL app isn't literally
# named "core". Set OPERATIONS_VDRL_APP_LABEL in settings if it's different.
VDRL_APP_LABEL = getattr(settings, "OPERATIONS_VDRL_APP_LABEL", "core")


class ModuleAccessMiddleware:
    """Block direct URL access, not only clicks from the landing page."""

    MODULE_PREFIXES = {
        f"{VDRL_APP_LABEL}.": ModuleCode.VDRL,
        "itp.": ModuleCode.ITP_NOI,
        "calibration.": ModuleCode.CALIBRATION,
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.user.is_authenticated:
            return None

        module_name = getattr(view_func, "__module__", "")
        view_class = getattr(view_func, "view_class", None)
        if view_class is not None:
            module_name = getattr(view_class, "__module__", module_name)

        required_module = None
        for prefix, module_code in self.MODULE_PREFIXES.items():
            if module_name.startswith(prefix):
                required_module = module_code
                break

        if required_module and not has_module_access(request.user, required_module):
            raise PermissionDenied("This module is inactive for your user account.")
        return None
