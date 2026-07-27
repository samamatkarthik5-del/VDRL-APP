from __future__ import annotations

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .services import module_flags


@login_required
def home(request):
    flags = module_flags(request.user)
    cards = [
        {
            "key": "vdrl",
            "title": "VDRL",
            "subtitle": "Vendor document planning, submission and customer review control",
            "url": getattr(settings, "OPERATIONS_VDRL_URL", "/work-bucket/"),
            "enabled": flags["vdrl"],
            "icon": "documents",
        },
        {
            "key": "itp_noi",
            "title": "Send for TPI NOI",
            "subtitle": "ITP clauses, annexure lines, hold points and inspection notifications",
            "url": "/itp/",
            "enabled": flags["itp_noi"],
            "icon": "inspection",
        },
        {
            "key": "calibration",
            "title": "Calibration",
            "subtitle": "Instrument master list, due dates, certificates and history cards",
            "url": "/calibration/",
            "enabled": flags["calibration"],
            "icon": "gauge",
        },
    ]
    return render(request, "operations_portal/home.html", {"cards": cards})
