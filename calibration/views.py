from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from operations_portal.decorators import module_access_required
from operations_portal.models import ModuleCode

from .forms import (
    CalibrationCycleForm,
    CalibrationReleaseForm,
    CalibrationVerificationForm,
    InstrumentForm,
)
from .models import (
    CalibrationAlert,
    CalibrationCycle,
    CalibrationCycleStatus,
    Instrument,
    InstrumentStatus,
)


@login_required
@module_access_required(ModuleCode.CALIBRATION)
def dashboard(request):
    today = timezone.localdate()
    due_limit = today + timedelta(days=15)
    instruments = Instrument.objects.filter(is_active=True).select_related(
        "category", "department", "custodian", "monitor"
    )
    context = {
        "total_count": instruments.count(),
        "due_soon_count": instruments.filter(
            next_due_date__gte=today, next_due_date__lte=due_limit
        ).count(),
        "overdue_count": instruments.filter(next_due_date__lt=today).count(),
        "at_lab_count": instruments.filter(status=InstrumentStatus.SENT_TO_LAB).count(),
        "due_instruments": instruments.filter(
            next_due_date__lte=due_limit
        ).order_by("next_due_date")[:20],
        "open_alerts": CalibrationAlert.objects.filter(is_resolved=False).select_related(
            "instrument", "assigned_to"
        )[:20],
    }
    return render(request, "calibration/dashboard.html", context)


@login_required
@module_access_required(ModuleCode.CALIBRATION)
def instrument_list(request):
    qs = Instrument.objects.select_related(
        "category", "department", "custodian", "monitor"
    )
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    if query:
        qs = qs.filter(
            Q(asset_number__icontains=query)
            | Q(description__icontains=query)
            | Q(purchase_serial_number__icontains=query)
            | Q(manufacturer_serial_number__icontains=query)
            | Q(location__icontains=query)
        )
    if status:
        qs = qs.filter(status=status)
    return render(
        request,
        "calibration/instrument_list.html",
        {"instruments": qs, "query": query, "status": status, "status_choices": InstrumentStatus.choices},
    )


@login_required
@module_access_required(ModuleCode.CALIBRATION)
def instrument_detail(request, pk):
    instrument = get_object_or_404(
        Instrument.objects.select_related(
            "category", "department", "custodian", "monitor"
        ),
        pk=pk,
    )
    return render(
        request,
        "calibration/instrument_detail.html",
        {
            "instrument": instrument,
            "cycles": instrument.calibration_cycles.select_related("laboratory", "verified_by"),
            "history": instrument.history_events.select_related("performed_by", "calibration_cycle")[:100],
        },
    )


@login_required
@module_access_required(ModuleCode.CALIBRATION)
@permission_required("calibration.add_instrument", raise_exception=True)
def instrument_create(request):
    form = InstrumentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        instrument = form.save(commit=False)
        instrument.created_by = request.user
        instrument.save()
        messages.success(request, "Instrument added to the calibration master list.")
        return redirect("calibration:instrument_detail", pk=instrument.pk)
    return render(request, "calibration/form.html", {"form": form, "title": "Add instrument or gauge"})


@login_required
@module_access_required(ModuleCode.CALIBRATION)
@permission_required("calibration.change_instrument", raise_exception=True)
def instrument_update(request, pk):
    instrument = get_object_or_404(Instrument, pk=pk)
    form = InstrumentForm(request.POST or None, instance=instrument)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Instrument master record updated.")
        return redirect("calibration:instrument_detail", pk=instrument.pk)
    return render(request, "calibration/form.html", {"form": form, "title": "Update instrument"})


@login_required
@module_access_required(ModuleCode.CALIBRATION)
@permission_required("calibration.add_calibrationcycle", raise_exception=True)
def cycle_create(request, instrument_pk):
    instrument = get_object_or_404(Instrument, pk=instrument_pk)
    form = CalibrationCycleForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        cycle = form.save(commit=False)
        cycle.instrument = instrument
        cycle.created_by = request.user
        cycle.save()
        messages.success(request, f"Calibration cycle {cycle.cycle_number} created.")
        return redirect("calibration:instrument_detail", pk=instrument.pk)
    return render(
        request,
        "calibration/form.html",
        {"form": form, "title": f"New calibration cycle - {instrument.asset_number}"},
    )


@login_required
@module_access_required(ModuleCode.CALIBRATION)
@permission_required("calibration.verify_calibration_cycle", raise_exception=True)
def cycle_verify(request, pk):
    cycle = get_object_or_404(CalibrationCycle.objects.select_related("instrument"), pk=pk)
    form = CalibrationVerificationForm(
        request.POST or None,
        request.FILES or None,
        instance=cycle,
    )
    if request.method == "POST" and form.is_valid():
        form.save(verified_by=request.user)
        messages.success(request, "Calibration certificate verified and history card updated.")
        return redirect("calibration:instrument_detail", pk=cycle.instrument_id)
    return render(
        request,
        "calibration/form.html",
        {"form": form, "title": f"QC verification - {cycle.instrument.asset_number}"},
    )


@login_required
@module_access_required(ModuleCode.CALIBRATION)
@permission_required("calibration.release_calibrated_instrument", raise_exception=True)
def cycle_release(request, pk):
    cycle = get_object_or_404(CalibrationCycle.objects.select_related("instrument"), pk=pk)
    if cycle.status != CalibrationCycleStatus.VERIFIED:
        messages.error(
            request,
            "Only a QC-verified cycle can be released back to production.",
        )
        return redirect("calibration:instrument_detail", pk=cycle.instrument_id)
    form = CalibrationReleaseForm(request.POST or None, instance=cycle)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Instrument released back to production.")
        return redirect("calibration:instrument_detail", pk=cycle.instrument_id)
    return render(
        request,
        "calibration/form.html",
        {"form": form, "title": f"Release to production - {cycle.instrument.asset_number}"},
    )


@login_required
@module_access_required(ModuleCode.CALIBRATION)
@permission_required("calibration.print_calibration_master_list", raise_exception=True)
def master_list(request):
    instruments = Instrument.objects.filter(is_active=True).select_related(
        "category", "department", "custodian", "monitor"
    )
    return render(request, "calibration/master_list.html", {"instruments": instruments})


@login_required
@module_access_required(ModuleCode.CALIBRATION)
def due_list(request):
    today = timezone.localdate()
    due_limit = today + timedelta(days=15)
    instruments = Instrument.objects.filter(
        is_active=True,
        next_due_date__lte=due_limit,
    ).select_related("category", "department", "custodian", "monitor").order_by("next_due_date")
    return render(request, "calibration/due_list.html", {"instruments": instruments, "today": today})
