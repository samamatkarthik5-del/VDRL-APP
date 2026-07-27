from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    AnnexureLineForm,
    AnnexureUploadForm,
    CoverageCompletionFormSet,
    HoldReleaseForm,
    InternalActivityExecutionForm,
    ITPClauseForm,
    ITPUploadForm,
    NOICompletionForm,
    NOICoverageFormSet,
    NOIForm,
)
from .models import (
    AuditLog,
    DocumentStatus,
    ExecutionSource,
    ITPActivityExecution,
    ITPAnnexure,
    ITPAnnexureLine,
    ITPClause,
    ITPDocument,
    ITPLineClauseMapping,
    MappingReviewStatus,
    NoticeOfInspection,
    WorkflowAlert,
)
from .services.access import can_access_sales_order
from .services.annexure_import import import_annexure
from .services.itp_import import import_itp_document
from .services.mapping import suggest_line_clause_mappings
from .services.noi import (
    HoldPointBlocked,
    confirm_noi_completion,
    create_noi,
    release_hold_execution,
)


def _assert_access(user, sales_order) -> None:
    if not can_access_sales_order(user, sales_order):
        raise PermissionDenied("You do not have access to this Sales Order.")


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    itps = [
        item
        for item in ITPDocument.objects.select_related("sales_order").all()[:100]
        if can_access_sales_order(request.user, item.sales_order)
    ][:10]
    annexures = [
        item
        for item in ITPAnnexure.objects.select_related("sales_order").all()[:100]
        if can_access_sales_order(request.user, item.sales_order)
    ][:10]
    nois = [
        item
        for item in NoticeOfInspection.objects.select_related(
            "itp__sales_order", "annexure", "responsible_user"
        ).all()[:150]
        if can_access_sales_order(request.user, item.itp.sales_order)
    ][:15]
    alerts = WorkflowAlert.objects.filter(is_resolved=False).filter(
        Q(assigned_to=request.user) | Q(assigned_to__isnull=True)
    )[:20]
    return render(
        request,
        "itp/dashboard.html",
        {"itps": itps, "annexures": annexures, "nois": nois, "alerts": alerts},
    )


@login_required
@permission_required("itp.add_itpdocument", raise_exception=True)
def upload_itp(request: HttpRequest) -> HttpResponse:
    form = ITPUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        document = form.save(commit=False)
        _assert_access(request.user, document.sales_order)
        document.uploaded_by = request.user
        document.save()
        try:
            import_itp_document(document)
            messages.success(
                request,
                f"ITP uploaded. {document.extraction_summary.get('clauses', 0)} clauses extracted for QC review.",
            )
        except Exception as exc:
            document.status = DocumentStatus.FAILED
            document.extraction_summary = {"error": str(exc)}
            document.save(update_fields=["status", "extraction_summary", "updated_at"])
            messages.error(request, f"ITP import failed: {exc}")
        return redirect("itp:itp_detail", pk=document.pk)
    return render(request, "itp/upload.html", {"form": form, "title": "Upload ITP"})


@login_required
def itp_detail(request: HttpRequest, pk) -> HttpResponse:
    document = get_object_or_404(
        ITPDocument.objects.select_related("sales_order", "uploaded_by", "approved_by"),
        pk=pk,
    )
    _assert_access(request.user, document.sales_order)
    clauses = document.clauses.prefetch_related("interventions__stakeholder")
    return render(
        request,
        "itp/itp_detail.html",
        {"document": document, "clauses": clauses, "issues": document.import_issues.all()},
    )


@login_required
@permission_required("itp.change_itpclause", raise_exception=True)
def edit_clause(request: HttpRequest, pk) -> HttpResponse:
    clause = get_object_or_404(ITPClause.objects.select_related("itp__sales_order"), pk=pk)
    _assert_access(request.user, clause.itp.sales_order)
    form = ITPClauseForm(request.POST or None, instance=clause)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Clause {clause.clause_code} updated.")
        return redirect("itp:itp_detail", pk=clause.itp_id)
    return render(request, "itp/form.html", {"form": form, "title": "Edit ITP clause"})


@login_required
@permission_required("itp.activate_itp", raise_exception=True)
@transaction.atomic
def activate_itp(request: HttpRequest, pk) -> HttpResponse:
    document = get_object_or_404(ITPDocument.objects.select_related("sales_order"), pk=pk)
    _assert_access(request.user, document.sales_order)
    if request.method != "POST":
        raise Http404
    if not document.clauses.exists():
        messages.error(request, "The ITP has no clauses and cannot be activated.")
        return redirect("itp:itp_detail", pk=pk)
    if document.import_issues.filter(severity="ERROR", is_resolved=False).exists():
        messages.error(request, "Resolve all import errors before activation.")
        return redirect("itp:itp_detail", pk=pk)
    ITPDocument.objects.filter(
        sales_order=document.sales_order,
        status=DocumentStatus.ACTIVE,
    ).exclude(pk=document.pk).update(status=DocumentStatus.SUPERSEDED)
    document.status = DocumentStatus.ACTIVE
    document.approved_by = request.user
    document.approved_at = timezone.now()
    document.activated_at = timezone.now()
    document.save(
        update_fields=["status", "approved_by", "approved_at", "activated_at", "updated_at"]
    )
    messages.success(request, "ITP revision activated.")
    return redirect("itp:itp_detail", pk=pk)


@login_required
@permission_required("itp.add_itpannexure", raise_exception=True)
def upload_annexure(request: HttpRequest) -> HttpResponse:
    form = AnnexureUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        annexure = form.save(commit=False)
        _assert_access(request.user, annexure.sales_order)
        annexure.uploaded_by = request.user
        annexure.save()
        try:
            import_annexure(annexure)
            messages.success(
                request,
                f"Annexure uploaded. {annexure.import_summary.get('imported', 0)} lines imported for QC review.",
            )
        except Exception as exc:
            annexure.status = DocumentStatus.FAILED
            annexure.import_summary = {"error": str(exc)}
            annexure.save(update_fields=["status", "import_summary", "updated_at"])
            messages.error(request, f"Annexure import failed: {exc}")
        return redirect("itp:annexure_detail", pk=annexure.pk)
    return render(
        request,
        "itp/upload.html",
        {"form": form, "title": "Upload ITP Annexure (Excel only)"},
    )


@login_required
def annexure_detail(request: HttpRequest, pk) -> HttpResponse:
    annexure = get_object_or_404(
        ITPAnnexure.objects.select_related("sales_order", "uploaded_by", "approved_by"),
        pk=pk,
    )
    _assert_access(request.user, annexure.sales_order)
    return render(
        request,
        "itp/annexure_detail.html",
        {
            "annexure": annexure,
            "lines": annexure.lines.all(),
            "issues": annexure.import_issues.all(),
        },
    )


@login_required
@permission_required("itp.change_itpannexureline", raise_exception=True)
def edit_annexure_line(request: HttpRequest, pk) -> HttpResponse:
    line = get_object_or_404(
        ITPAnnexureLine.objects.select_related("annexure__sales_order"), pk=pk
    )
    _assert_access(request.user, line.annexure.sales_order)
    form = AnnexureLineForm(request.POST or None, instance=line)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Annexure line {line.po_line_no} updated.")
        return redirect("itp:annexure_detail", pk=line.annexure_id)
    return render(request, "itp/form.html", {"form": form, "title": "Edit annexure line"})


@login_required
@permission_required("itp.activate_annexure", raise_exception=True)
@transaction.atomic
def activate_annexure(request: HttpRequest, pk) -> HttpResponse:
    annexure = get_object_or_404(ITPAnnexure.objects.select_related("sales_order"), pk=pk)
    _assert_access(request.user, annexure.sales_order)
    if request.method != "POST":
        raise Http404
    if not annexure.lines.exists():
        messages.error(request, "The annexure has no lines and cannot be activated.")
        return redirect("itp:annexure_detail", pk=pk)
    if annexure.import_issues.filter(severity="ERROR", is_resolved=False).exists():
        messages.error(request, "Resolve all import errors before activation.")
        return redirect("itp:annexure_detail", pk=pk)
    ITPAnnexure.objects.filter(
        sales_order=annexure.sales_order,
        status=DocumentStatus.ACTIVE,
    ).exclude(pk=annexure.pk).update(status=DocumentStatus.SUPERSEDED)
    annexure.status = DocumentStatus.ACTIVE
    annexure.approved_by = request.user
    annexure.approved_at = timezone.now()
    annexure.activated_at = timezone.now()
    annexure.save(
        update_fields=["status", "approved_by", "approved_at", "activated_at", "updated_at"]
    )
    messages.success(request, "Annexure revision activated.")
    return redirect("itp:annexure_detail", pk=pk)


@login_required
@permission_required("itp.add_itplineclausemapping", raise_exception=True)
def generate_mapping(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        itp = get_object_or_404(ITPDocument, pk=request.POST.get("itp"))
        annexure = get_object_or_404(ITPAnnexure, pk=request.POST.get("annexure"))
        _assert_access(request.user, itp.sales_order)
        result = suggest_line_clause_mappings(itp, annexure)
        messages.success(
            request,
            f"Mapping suggestions generated: {result['applicable']} applicable combinations. QC approval is required.",
        )
        return redirect("itp:mapping_review", itp_pk=itp.pk, annexure_pk=annexure.pk)
    return render(
        request,
        "itp/generate_mapping.html",
        {
            "itps": ITPDocument.objects.filter(status=DocumentStatus.ACTIVE),
            "annexures": ITPAnnexure.objects.filter(status=DocumentStatus.ACTIVE),
        },
    )


@login_required
@permission_required("itp.change_itplineclausemapping", raise_exception=True)
def mapping_review(request: HttpRequest, itp_pk, annexure_pk) -> HttpResponse:
    itp = get_object_or_404(ITPDocument.objects.select_related("sales_order"), pk=itp_pk)
    annexure = get_object_or_404(ITPAnnexure, pk=annexure_pk)
    _assert_access(request.user, itp.sales_order)
    mappings = ITPLineClauseMapping.objects.filter(
        clause__itp=itp,
        annexure_line__annexure=annexure,
    ).select_related("clause", "annexure_line")

    clause_filter = request.GET.get("clause")
    line_filter = request.GET.get("line")
    if clause_filter:
        mappings = mappings.filter(clause_id=clause_filter)
    if line_filter:
        mappings = mappings.filter(annexure_line_id=line_filter)

    if request.method == "POST":
        selected_ids = request.POST.getlist("mapping_ids")
        action = request.POST.get("action")
        if action not in {"approve", "reject"}:
            messages.error(request, "Select Approve or Reject.")
        else:
            status = (
                MappingReviewStatus.APPROVED
                if action == "approve"
                else MappingReviewStatus.REJECTED
            )
            ITPLineClauseMapping.objects.filter(pk__in=selected_ids).update(
                review_status=status,
                is_applicable=(action == "approve"),
                reviewed_by=request.user,
                reviewed_at=timezone.now(),
            )
            messages.success(request, f"{len(selected_ids)} mappings updated.")
        return redirect("itp:mapping_review", itp_pk=itp.pk, annexure_pk=annexure.pk)

    return render(
        request,
        "itp/mapping_review.html",
        {
            "itp": itp,
            "annexure": annexure,
            "mappings": mappings[:1000],
            "clauses": itp.clauses.all(),
            "lines": annexure.lines.all(),
        },
    )


@login_required
@permission_required("itp.add_noticeofinspection", raise_exception=True)
def create_noi_view(request: HttpRequest) -> HttpResponse:
    selected_itp = None
    selected_annexure = None
    if request.method == "POST":
        try:
            selected_itp = ITPDocument.objects.get(pk=request.POST.get("itp"))
            selected_annexure = ITPAnnexure.objects.get(pk=request.POST.get("annexure"))
        except (ITPDocument.DoesNotExist, ITPAnnexure.DoesNotExist, ValueError, TypeError):
            pass

    form = NOIForm(request.POST or None)
    formset = NOICoverageFormSet(
        request.POST or None,
        prefix="coverage",
        form_kwargs={"itp": selected_itp, "annexure": selected_annexure},
    )

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        _assert_access(request.user, form.cleaned_data["itp"].sales_order)
        coverage_rows = [
            row
            for row in formset.cleaned_data
            if row and not row.get("DELETE") and row.get("clause") and row.get("annexure_line")
        ]
        if not coverage_rows:
            messages.error(request, "Add at least one ITP clause and annexure line coverage row.")
        else:
            try:
                noi = create_noi(form_data=form.cleaned_data, coverage_rows=coverage_rows, user=request.user)
                messages.success(request, f"NOI {noi.number} created.")
                return redirect("itp:noi_detail", pk=noi.pk)
            except HoldPointBlocked as exc:
                for item in exc.blocked_items:
                    messages.error(
                        request,
                        f"Line {item['line']}: previous Hold Point {item['previous_clause']} is {item['state']}. Current clause {item['current_clause']} is blocked.",
                    )
            except Exception as exc:
                messages.error(request, str(exc))

    return render(
        request,
        "itp/noi_create.html",
        {"form": form, "formset": formset},
    )


@login_required
def noi_list(request: HttpRequest) -> HttpResponse:
    nois = [
        item
        for item in NoticeOfInspection.objects.select_related(
            "itp__sales_order", "annexure", "responsible_user"
        ).all()[:1000]
        if can_access_sales_order(request.user, item.itp.sales_order)
    ]
    return render(request, "itp/noi_list.html", {"nois": nois})


@login_required
def noi_detail(request: HttpRequest, pk) -> HttpResponse:
    noi = get_object_or_404(
        NoticeOfInspection.objects.select_related(
            "itp__sales_order", "annexure", "responsible_user", "created_by"
        ),
        pk=pk,
    )
    _assert_access(request.user, noi.itp.sales_order)
    coverages = noi.coverages.select_related("clause", "annexure_line")
    return render(
        request,
        "itp/noi_detail.html",
        {"noi": noi, "coverages": coverages, "alerts": noi.alerts.filter(is_resolved=False)},
    )


@login_required
def confirm_noi(request: HttpRequest, pk) -> HttpResponse:
    noi = get_object_or_404(
        NoticeOfInspection.objects.select_related("itp__sales_order", "responsible_user"),
        pk=pk,
    )
    _assert_access(request.user, noi.itp.sales_order)
    if request.user != noi.responsible_user and not request.user.has_perm(
        "itp.change_noticeofinspection"
    ):
        raise PermissionDenied("Only the responsible user or authorised QC user can confirm completion.")

    initial = [
        {
            "coverage_id": coverage.pk,
            "completed_quantity": coverage.offered_quantity,
            "result": "ACCEPTED",
        }
        for coverage in noi.coverages.all()
    ]
    form = NOICompletionForm(request.POST or None)
    formset = CoverageCompletionFormSet(
        request.POST or None,
        prefix="completion",
        initial=initial,
    )
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        try:
            confirm_noi_completion(
                noi=noi,
                overall_status=form.cleaned_data["overall_status"],
                comment=form.cleaned_data["comment"],
                coverage_updates=[row for row in formset.cleaned_data if row],
                user=request.user,
            )
            messages.success(request, "NOI completion status updated.")
            return redirect("itp:noi_detail", pk=noi.pk)
        except Exception as exc:
            messages.error(request, str(exc))
    coverage_lookup = {str(c.pk): c for c in noi.coverages.select_related("clause", "annexure_line")}
    rows = [(subform, coverage_lookup.get(str(subform.initial.get("coverage_id")))) for subform in formset]
    return render(
        request,
        "itp/noi_confirm.html",
        {"noi": noi, "form": form, "formset": formset, "rows": rows},
    )


@login_required
@permission_required("itp.release_hold_point", raise_exception=True)
def release_hold(request: HttpRequest, pk) -> HttpResponse:
    execution = get_object_or_404(
        ITPActivityExecution.objects.select_related(
            "mapping__clause__itp__sales_order", "mapping__annexure_line"
        ),
        pk=pk,
    )
    _assert_access(request.user, execution.mapping.clause.itp.sales_order)
    form = HoldReleaseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            release_hold_execution(
                execution=execution,
                user=request.user,
                reference=form.cleaned_data["release_reference"],
                remarks=form.cleaned_data["remarks"],
            )
            messages.success(request, "Hold Point released.")
            if execution.noi_coverage_id:
                return redirect("itp:noi_detail", pk=execution.noi_coverage.noi_id)
            return redirect("itp:dashboard")
        except Exception as exc:
            messages.error(request, str(exc))
    return render(
        request,
        "itp/form.html",
        {"form": form, "title": f"Release Hold Point {execution.mapping.clause.clause_code}"},
    )


@login_required
@permission_required("itp.add_itpactivityexecution", raise_exception=True)
def record_internal_activity(request: HttpRequest) -> HttpResponse:
    form = InternalActivityExecutionForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        execution = form.save(commit=False)
        _assert_access(request.user, execution.mapping.clause.itp.sales_order)
        execution.source = ExecutionSource.INTERNAL
        execution.completed_by = request.user
        if execution.status in {"RELEASED", "WAIVED"} and not request.user.has_perm(
            "itp.release_hold_point"
        ):
            raise PermissionDenied("You do not have permission to release or waive a Hold Point.")
        if execution.status in {"COMPLETED", "RELEASED", "WAIVED"} and not execution.completed_at:
            execution.completed_at = timezone.now()
        if execution.status in {"RELEASED", "WAIVED"}:
            execution.released_by = request.user
            execution.released_at = timezone.now()
        execution.full_clean()
        execution.save()
        messages.success(request, "Internal ITP activity recorded.")
        return redirect("itp:dashboard")
    return render(
        request,
        "itp/form.html",
        {"form": form, "title": "Record internal ITP activity"},
    )


@login_required
def alerts(request: HttpRequest) -> HttpResponse:
    alert_list = WorkflowAlert.objects.filter(
        Q(assigned_to=request.user) | Q(assigned_to__isnull=True)
    ).select_related("noi", "coverage")
    return render(request, "itp/alerts.html", {"alerts": alert_list})


@login_required
def resolve_alert(request: HttpRequest, pk) -> HttpResponse:
    alert = get_object_or_404(WorkflowAlert, pk=pk)
    if alert.assigned_to and alert.assigned_to != request.user and not request.user.is_superuser:
        raise PermissionDenied
    if request.method == "POST":
        alert.is_resolved = True
        alert.resolved_by = request.user
        alert.resolved_at = timezone.now()
        alert.save(update_fields=["is_resolved", "resolved_by", "resolved_at"])
    return redirect("itp:alerts")
