from __future__ import annotations

from functools import wraps

from django.core.exceptions import PermissionDenied

from .services import has_module_access


def module_access_required(module_code: str):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not has_module_access(request.user, module_code):
                raise PermissionDenied("You are not authorised for this application module.")
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator
