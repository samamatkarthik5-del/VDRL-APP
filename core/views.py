from pathlib import Path

from django.http import (
    FileResponse,
    Http404,
)
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.utils import timezone
from django.views.decorators.http import require_POST
from .models import (
    AuditLog,
    CRSComment,
    CRSRegister,
    Department,
    DocumentFile,
    DocumentTransaction,
    SalesOrder,
    SalesOrderVDRLDocument,
)
from .forms import (
    CRSCommentForm,
    CRSRegisterForm,
    DocumentFileUploadForm,
    DocumentTransactionActionForm,
    SalesOrderVDRLDocumentUpdateForm,
)

from django.core.exceptions import (
    PermissionDenied,
)

from .access import (
    can_edit_document_details,
    can_manage_crs_for_document,
    can_manage_files,
    can_manage_workflow,
    can_view_document,
    can_view_sales_order,
    filter_documents_for_user,
    filter_sales_orders_for_user,
)

from .audit import (
    record_audit_event,
)

CUSTOMER_STATUSES = [
    SalesOrderVDRLDocument.DocumentStatus.SUBMITTED,
    SalesOrderVDRLDocument.DocumentStatus.UNDER_CUSTOMER_REVIEW,
    SalesOrderVDRLDocument.DocumentStatus.RESUBMITTED,
]


COMPLETED_STATUSES = [
    SalesOrderVDRLDocument.DocumentStatus.APPROVED,
    SalesOrderVDRLDocument.DocumentStatus.NOT_APPLICABLE,
    SalesOrderVDRLDocument.DocumentStatus.CANCELLED,
]


def get_allowed_actions(document):
    """
    Returns the workflow actions that are logical for the
    document's current status.
    """

    Status = SalesOrderVDRLDocument.DocumentStatus
    Action = DocumentTransaction.TransactionType

    action_map = {
        Status.PLANNED: [
            Action.ASSIGNED_INTERNAL,
            Action.MARK_NOT_APPLICABLE,
            Action.ON_HOLD,
            Action.CANCELLED,
        ],

        Status.UNDER_PREPARATION: [
            Action.READY_INITIAL_SUBMISSION,
            Action.INITIAL_SUBMISSION,
            Action.ON_HOLD,
        ],

        Status.INTERNAL_REVIEW: [
            Action.READY_INITIAL_SUBMISSION,
            Action.INITIAL_SUBMISSION,
            Action.ON_HOLD,
        ],

        Status.READY_FOR_SUBMISSION: [
            Action.INITIAL_SUBMISSION,
            Action.ON_HOLD,
        ],

        Status.SUBMITTED: [
            Action.RETURNED_WITH_COMMENTS,
            Action.APPROVED_WITH_COMMENTS,
            Action.FINAL_APPROVAL,
        ],

        Status.UNDER_CUSTOMER_REVIEW: [
            Action.RETURNED_WITH_COMMENTS,
            Action.APPROVED_WITH_COMMENTS,
            Action.FINAL_APPROVAL,
        ],

        Status.RESUBMITTED: [
            Action.RETURNED_WITH_COMMENTS,
            Action.APPROVED_WITH_COMMENTS,
            Action.FINAL_APPROVAL,
        ],

        Status.RETURNED_WITH_COMMENTS: [
            Action.COMMENT_ASSESSMENT,
            Action.REVISION_STARTED,
            Action.CRS_STARTED,
            Action.ON_HOLD,
        ],

        Status.COMMENT_ASSESSMENT: [
            Action.REVISION_STARTED,
            Action.CRS_STARTED,
            Action.ON_HOLD,
        ],

        Status.REVISION_IN_PROGRESS: [
            Action.REVISION_COMPLETED,
            Action.CRS_STARTED,
            Action.ON_HOLD,
        ],

        Status.CRS_IN_PROGRESS: [
            Action.CRS_COMPLETED,
            Action.ON_HOLD,
        ],

        Status.READY_FOR_RESUBMISSION: [
            Action.RESUBMISSION,
            Action.ON_HOLD,
        ],

        Status.APPROVED_WITH_COMMENTS: [
            Action.COMMENT_ASSESSMENT,
            Action.REVISION_STARTED,
            Action.RESUBMISSION,
            Action.ON_HOLD,
        ],

        Status.ON_HOLD: [
            Action.REACTIVATED,
        ],
    }

    action_labels = dict(
        DocumentTransaction.TransactionType.choices
    )

    actions = action_map.get(
        document.status,
        [],
    )

    return [
        {
            "value": action,
            "label": action_labels.get(
                action,
                action,
            ),
        }
        for action in actions
    ]


def dashboard(request):
    """
    Main management and operational dashboard.
    """

    today = timezone.localdate()

    documents = (
        SalesOrderVDRLDocument.objects
        .filter(
            is_active=True,
            vdrl__is_current=True,
            vdrl__sales_order__is_active=True,
        )
        .select_related(
            "vdrl",
            "vdrl__sales_order",
            "vdrl__sales_order__customer",
            "responsible_department",
            "responsible_person",
        )
    )

    documents = (
    filter_documents_for_user(
        request.user,
        documents,
        )
    )

    overdue_query = (
        Q(
            applicability_status=(
                SalesOrderVDRLDocument
                .ApplicabilityStatus
                .REQUIRED
            ),
            first_submission_at__isnull=True,
            planned_submission_date__lt=today,
        )
        |
        Q(
            status__in=CUSTOMER_STATUSES,
            customer_review_due_date__lt=today,
        )
    )

    statistics = {
        "total_documents": documents.count(),

        "approved_documents": documents.filter(
            status=(
                SalesOrderVDRLDocument
                .DocumentStatus
                .APPROVED
            )
        ).count(),

        "with_customer": documents.filter(
            status__in=CUSTOMER_STATUSES
        ).count(),

        "internal_pending": documents.exclude(
            status__in=(
                CUSTOMER_STATUSES
                + COMPLETED_STATUSES
                + [
                    SalesOrderVDRLDocument
                    .DocumentStatus
                    .ON_HOLD
                ]
            )
        ).count(),

        "overdue_documents": documents.filter(
            overdue_query
        ).count(),

        "on_hold": documents.filter(
            status=(
                SalesOrderVDRLDocument
                .DocumentStatus
                .ON_HOLD
            )
        ).count(),

                "open_crs_comments": (
            CRSComment.objects
            .exclude(
                status=CRSComment.Status.CLOSED
            )
            .count()
        ),

        "overdue_crs_comments": (
            CRSComment.objects
            .exclude(
                status=CRSComment.Status.CLOSED
            )
            .filter(
                target_response_date__lt=today
            )
            .count()
        ),
    }

    overdue_documents = (
        documents
        .filter(overdue_query)
        .distinct()
        .order_by(
            "planned_submission_date",
            "customer_review_due_date",
        )[:10]
    )

    my_actions = (
        documents
        .filter(
            responsible_person=request.user
        )
        .exclude(
            status__in=(
                CUSTOMER_STATUSES
                + COMPLETED_STATUSES
                + [
                    SalesOrderVDRLDocument
                    .DocumentStatus
                    .ON_HOLD
                ]
            )
        )
        .order_by(
            "planned_submission_date",
            "sequence_number",
        )[:10]
    )

    sales_order_rows = []

    sales_orders = (
        SalesOrder.objects
        .filter(is_active=True)
        .select_related(
            "customer",
            "project",
            "project_manager",
            "document_controller",
        )
        .order_by(
            "-order_date",
            "sales_order_number",
        )
    )

    sales_orders = (
    filter_sales_orders_for_user(
        request.user,
        sales_orders,
        )
    )

    for sales_order in sales_orders:
        current_vdrl = (
            sales_order.vdrls
            .filter(is_current=True)
            .order_by("-created_at")
            .first()
        )

        if current_vdrl:
            vdrl_documents = (
                current_vdrl.documents
                .filter(is_active=True)
            )

            total_count = vdrl_documents.count()

            approved_count = vdrl_documents.filter(
                status=(
                    SalesOrderVDRLDocument
                    .DocumentStatus
                    .APPROVED
                )
            ).count()

            customer_count = vdrl_documents.filter(
                status__in=CUSTOMER_STATUSES
            ).count()

            if total_count:
                progress = round(
                    approved_count
                    * 100
                    / total_count
                )
            else:
                progress = 0

        else:
            total_count = 0
            approved_count = 0
            customer_count = 0
            progress = 0

        sales_order_rows.append(
            {
                "sales_order": sales_order,
                "current_vdrl": current_vdrl,
                "total_count": total_count,
                "approved_count": approved_count,
                "customer_count": customer_count,
                "progress": progress,
            }
        )

    my_crs_comments = (
        CRSComment.objects
        .filter(
            assigned_person=request.user
        )
        .exclude(
            status=CRSComment.Status.CLOSED
        )
        .select_related(
            "crs",
            "crs__document",
            "crs__document__vdrl",
            "crs__document__vdrl__sales_order",
        )
        .order_by(
            "target_response_date",
            "assigned_at",
        )[:10]
    )

    context = {
        "statistics": statistics,
        "overdue_documents": overdue_documents,
        "my_actions": my_actions,
        "sales_order_rows": sales_order_rows,
        "today": today,
         "my_crs_comments": my_crs_comments,
    }

    return render(
        request,
        "core/dashboard.html",
        context,
    )


@login_required
def sales_order_vdrl(request, pk):
    """
    Displays the current VDRL for one Sales Order.
    """

    sales_order = get_object_or_404(
        SalesOrder.objects.select_related(
            "customer",
            "project",
            "project_manager",
            "document_controller",
        ),
        pk=pk,
    )

    if not can_view_sales_order(
    request.user,
    sales_order,
    ):
        raise PermissionDenied

    vdrl = (
        sales_order.vdrls
        .filter(is_current=True)
        .order_by("-created_at")
        .first()
    )

    if not vdrl:
        context = {
            "sales_order": sales_order,
            "vdrl": None,
        }

        return render(
            request,
            "core/sales_order_vdrl.html",
            context,
        )

    all_documents = (
        vdrl.documents
        .filter(is_active=True)
        .select_related(
            "document",
            "responsible_department",
            "responsible_person",
        )
        .order_by("sequence_number")
    )

    statistics = {
        "total": all_documents.count(),

        "approved": all_documents.filter(
            status=(
                SalesOrderVDRLDocument
                .DocumentStatus
                .APPROVED
            )
        ).count(),

        "with_customer": all_documents.filter(
            status__in=CUSTOMER_STATUSES
        ).count(),

        "internal": all_documents.exclude(
            status__in=(
                CUSTOMER_STATUSES
                + COMPLETED_STATUSES
                + [
                    SalesOrderVDRLDocument
                    .DocumentStatus
                    .ON_HOLD
                ]
            )
        ).count(),
    }

    documents = all_documents

    search_text = request.GET.get(
        "q",
        "",
    ).strip()

    status_filter = request.GET.get(
        "status",
        "",
    ).strip()

    department_filter = request.GET.get(
        "department",
        "",
    ).strip()

    holder_filter = request.GET.get(
        "holder",
        "",
    ).strip()

    overdue_filter = request.GET.get(
        "overdue",
        "",
    ).strip()

    if search_text:
        documents = documents.filter(
            Q(
                customer_document_code__icontains=(
                    search_text
                )
            )
            |
            Q(
                document_title__icontains=(
                    search_text
                )
            )
            |
            Q(
                document__internal_document_code__icontains=(
                    search_text
                )
            )
        )

    if status_filter:
        documents = documents.filter(
            status=status_filter
        )

    if department_filter:
        documents = documents.filter(
            responsible_department_id=(
                department_filter
            )
        )

    if holder_filter == "CUSTOMER":
        documents = documents.filter(
            status__in=CUSTOMER_STATUSES
        )

    elif holder_filter == "COMPLETED":
        documents = documents.filter(
            status__in=COMPLETED_STATUSES
        )

    elif holder_filter == "ON_HOLD":
        documents = documents.filter(
            status=(
                SalesOrderVDRLDocument
                .DocumentStatus
                .ON_HOLD
            )
        )

    elif holder_filter == "INTERNAL":
        documents = documents.exclude(
            status__in=(
                CUSTOMER_STATUSES
                + COMPLETED_STATUSES
                + [
                    SalesOrderVDRLDocument
                    .DocumentStatus
                    .ON_HOLD
                ]
            )
        )

    if overdue_filter == "YES":
        today = timezone.localdate()

        documents = documents.filter(
            Q(
                applicability_status=(
                    SalesOrderVDRLDocument
                    .ApplicabilityStatus
                    .REQUIRED
                ),
                first_submission_at__isnull=True,
                planned_submission_date__lt=today,
            )
            |
            Q(
                status__in=CUSTOMER_STATUSES,
                customer_review_due_date__lt=today,
            )
        )

    document_list = list(documents)

    for document in document_list:

        document.can_edit_details = (
        can_edit_document_details(
            request.user,
            document,
            )
        )

    document.can_manage_files = (
        can_manage_files(
            request.user,
            document,
        )
    )

    document.can_manage_crs = (
        can_manage_crs_for_document(
            request.user,
            document,
        )
    )

    if can_manage_workflow(
        request.user,
        document,
    ):
        document.available_actions = (
            get_allowed_actions(
                document
            )
        )

    else:
        document.available_actions = []


    document.default_open_file = (
        document.get_default_file()
    )

    context = {
        "sales_order": sales_order,
        "vdrl": vdrl,
        "documents": document_list,
        "statistics": statistics,
        "status_choices": (
            SalesOrderVDRLDocument
            .DocumentStatus
            .choices
        ),
        "departments": (
            Department.objects
            .filter(is_active=True)
            .order_by("name")
        ),
        "search_text": search_text,
        "status_filter": status_filter,
        "department_filter": department_filter,
        "holder_filter": holder_filter,
        "overdue_filter": overdue_filter,
    }

    return render(
        request,
        "core/sales_order_vdrl.html",
        context,
    )


@login_required
def document_detail(request, pk):
    document = get_object_or_404(
        SalesOrderVDRLDocument.objects.select_related(
            "vdrl",
            "vdrl__sales_order",
            "vdrl__sales_order__customer",
            "document",
            "responsible_department",
            "responsible_person",
        ),
        pk=pk,
    )

    if not can_view_document(
    request.user,
    document,
):
        raise PermissionDenied

    transactions = (
        document.transactions
        .select_related(
            "responsible_person_after_event",
            "elapsed_responsible_person",
            "created_by",
        )
        .order_by(
            "transaction_at",
            "id",
        )
    )

    files = (
        document.files
        .filter(
            is_active=True
        )
        .select_related(
            "uploaded_by"
        )
        .order_by(
            "-uploaded_at",
            "-id",
        )
    )

    crs_registers = (
        document.crs_registers
        .select_related(
            "prepared_by",
            "reviewed_by",
            "approved_by",
            "crs_file",
            "source_return_transaction",
        )
        .prefetch_related(
            "comments"
        )
        .order_by(
            "-cycle_number",
            "-created_at",
        )
    )

    context = {
        "document": document,
        "transactions": transactions,
        "files": files,
        "available_actions": (
    get_allowed_actions(
        document
    )

    if can_manage_workflow(
        request.user,
        document,
    )

    else []
),
        "can_edit_document_details": (
    can_edit_document_details(
        request.user,
        document,
    )
),

"can_manage_workflow": (
    can_manage_workflow(
        request.user,
        document,
    )
),

"can_manage_files": (
    can_manage_files(
        request.user,
        document,
    )
),

"can_manage_crs": (
    can_manage_crs_for_document(
        request.user,
        document,
    )
),
    }

    return render(
        request,
        "core/document_detail.html",
        context,
    )


@login_required
def document_edit(request, pk):
    document = get_object_or_404(
        SalesOrderVDRLDocument,
        pk=pk,
    )

    if not can_edit_document_details(
    request.user,
    document,
):
        raise PermissionDenied

    if request.method == "POST":
        form = SalesOrderVDRLDocumentUpdateForm(
            request.POST,
            instance=document,
        )

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "VDRL document details updated successfully.",
            )

            return redirect(
                "core:document_detail",
                pk=document.pk,
            )

    else:
        form = SalesOrderVDRLDocumentUpdateForm(
            instance=document
        )

    context = {
        "document": document,
        "form": form,
    }

    return render(
        request,
        "core/document_edit.html",
        context,
    )


@login_required
def document_action(
    request,
    pk,
    action_type,
):
    document = get_object_or_404(
        SalesOrderVDRLDocument.objects.select_related(
            "vdrl",
            "vdrl__sales_order",
            "responsible_person",
        ),
        pk=pk,
    )

    if not can_manage_workflow(
    request.user,
    document,
):
        raise PermissionDenied

    allowed_actions = get_allowed_actions(document)

    allowed_action_values = {
        item["value"]
        for item in allowed_actions
    }

    if action_type not in allowed_action_values:
        messages.error(
            request,
            (
                "This action is not available for the "
                "document's current status."
            ),
        )

        return redirect(
            "core:document_detail",
            pk=document.pk,
        )

    action_labels = dict(
        DocumentTransaction
        .TransactionType
        .choices
    )

    action_label = action_labels.get(
        action_type,
        action_type,
    )

    transaction_instance = DocumentTransaction(
        document=document,
        transaction_type=action_type,
        created_by=request.user,
    )

    if request.method == "POST":
        form = DocumentTransactionActionForm(
            request.POST,
            instance=transaction_instance,
        )

        if form.is_valid():
            transaction_record = form.save(
                commit=False
            )

            transaction_record.document = document
            transaction_record.transaction_type = (
                action_type
            )
            transaction_record.created_by = (
                request.user
            )

            transaction_record.save()

            messages.success(
                request,
                (
                    f"{action_label} recorded successfully."
                ),
            )

            return redirect(
                "core:document_detail",
                pk=document.pk,
            )

    else:
        form = DocumentTransactionActionForm(
            instance=transaction_instance,
            initial={
                "transaction_at": (
                    timezone.localtime(
                        timezone.now()
                    )
                    .replace(
                        second=0,
                        microsecond=0,
                    )
                ),
                "revision": (
                    document.current_revision
                ),
                "responsible_person_after_event": (
                    document.responsible_person
                ),
            },
        )

    preview_transaction = DocumentTransaction(
        document=document,
        transaction_type=action_type,
    )

    holder_after_event = (
        preview_transaction
        .get_holder_after_event()
    )

    needs_responsible_person = (
        holder_after_event
        == DocumentTransaction.HolderType.INTERNAL
    )

    show_comment_count = action_type in {
        DocumentTransaction
        .TransactionType
        .RETURNED_WITH_COMMENTS,

        DocumentTransaction
        .TransactionType
        .APPROVED_WITH_COMMENTS,
    }

    show_crs_reference = action_type in {
        DocumentTransaction
        .TransactionType
        .RETURNED_WITH_COMMENTS,

        DocumentTransaction
        .TransactionType
        .CRS_STARTED,

        DocumentTransaction
        .TransactionType
        .CRS_COMPLETED,
    }

    context = {
        "document": document,
        "form": form,
        "action_type": action_type,
        "action_label": action_label,
        "holder_after_event": holder_after_event,
        "needs_responsible_person": (
            needs_responsible_person
        ),
        "show_comment_count": show_comment_count,
        "show_crs_reference": (
            show_crs_reference
        ),
    }

    return render(
        request,
        "core/document_action.html",
        context,
    )

@login_required
def document_file_upload(
    request,
    pk,
):
    document = get_object_or_404(
        SalesOrderVDRLDocument.objects.select_related(
            "vdrl",
            "vdrl__sales_order",
            "vdrl__sales_order__customer",
            "document",
        ),
        pk=pk,
    )

    if not can_manage_files(
    request.user,
    document,
):
        raise PermissionDenied

    if request.method == "POST":
        form = DocumentFileUploadForm(
            request.POST,
            request.FILES,
            document=document,
        )

        if form.is_valid():
            with transaction.atomic():
                file_record = (
                    form.save(
                        commit=False
                    )
                )

                file_record.document = (
                    document
                )

                file_record.uploaded_by = (
                    request.user
                )

                uploaded_file = (
                    request.FILES.get(
                        "file"
                    )
                )

                if uploaded_file:
                    file_record.original_filename = (
                        uploaded_file.name
                    )

                if file_record.is_current:
                    (
                        DocumentFile.objects
                        .filter(
                            document=document,
                            file_type=(
                                file_record
                                .file_type
                            ),
                            is_current=True,
                        )
                        .update(
                            is_current=False
                        )
                    )

                file_record.save()

            messages.success(
                request,
                (
                    "File uploaded successfully: "
                    f"{file_record.original_filename}"
                ),
            )

            return redirect(
                "core:document_detail",
                pk=document.pk,
            )

    else:
        form = DocumentFileUploadForm(
            document=document,
            initial={
                "revision": (
                    document.current_revision
                ),
                "cycle_number": (
                    document.current_cycle
                ),
                "is_current": True,
            },
        )

    context = {
        "document": document,
        "form": form,
    }

    return render(
        request,
        "core/document_file_upload.html",
        context,
    )

@login_required
def document_file_open(
    request,
    pk,
):
    file_record = get_object_or_404(
        DocumentFile,
        pk=pk,
        is_active=True,
    )

    if not can_view_document(
    request.user,
    file_record.document,
):
        raise PermissionDenied

    try:
        file_handle = (
            file_record
            .file
            .open("rb")
        )

    except (
        FileNotFoundError,
        OSError,
        ValueError,
    ):
        raise Http404(
            "The physical file could not be found."
        )

    filename = (
        file_record.original_filename
        or Path(
            file_record.file.name
        ).name
    )

    return FileResponse(
        file_handle,
        as_attachment=False,
        filename=filename,
    )

@login_required
def document_file_download(
    request,
    pk,
):
    file_record = get_object_or_404(
        DocumentFile,
        pk=pk,
        is_active=True,
    )

    if not can_view_document(
    request.user,
    file_record.document,
):
        raise PermissionDenied

    try:
        file_handle = (
            file_record
            .file
            .open("rb")
        )

    except (
        FileNotFoundError,
        OSError,
        ValueError,
    ):
        raise Http404(
            "The physical file could not be found."
        )

    filename = (
        file_record.original_filename
        or Path(
            file_record.file.name
        ).name
    )

    record_audit_event(
    action=(
        AuditLog
        .Action
        .DOWNLOAD
    ),

    instance=file_record,

    actor=request.user,

    request=request,

    description=(
        f"Downloaded file "
        f"{file_record.original_filename}."
    ),

    event_data={
        "filename": (
            file_record
            .original_filename
        ),

        "file_type": (
            file_record
            .file_type
        ),

        "revision": (
            file_record
            .revision
        ),
    },
)

    return FileResponse(
        file_handle,
        as_attachment=True,
        filename=filename,
    )

@login_required
@require_POST
def document_file_set_current(
    request,
    pk,
):
    file_record = get_object_or_404(
        DocumentFile,
        pk=pk,
        is_active=True,
    )

    if not can_manage_files(
    request.user,
    file_record.document,
):
        raise PermissionDenied

    with transaction.atomic():
        (
            DocumentFile.objects
            .filter(
                document=(
                    file_record.document
                ),
                file_type=(
                    file_record.file_type
                ),
                is_current=True,
            )
            .update(
                is_current=False
            )
        )

        file_record.is_current = True

        file_record.save(
            update_fields=[
                "is_current",
                "updated_at",
            ]
        )

    messages.success(
        request,
        (
            f"{file_record.original_filename} "
            "is now the current file."
        ),
    )

    return redirect(
        "core:document_detail",
        pk=file_record.document.pk,
    )

@login_required
def crs_create(
    request,
    document_pk,
):
    document = get_object_or_404(
        SalesOrderVDRLDocument.objects.select_related(
            "vdrl",
            "vdrl__sales_order",
            "document",
        ),
        pk=document_pk,
    )

    if not can_manage_crs_for_document(
    request.user,
    document,
):
        raise PermissionDenied

    latest_return_transaction = (
        document.transactions
        .filter(
            transaction_type__in=[
                DocumentTransaction
                .TransactionType
                .RETURNED_WITH_COMMENTS,

                DocumentTransaction
                .TransactionType
                .APPROVED_WITH_COMMENTS,
            ]
        )
        .order_by(
            "-transaction_at"
        )
        .first()
    )

    if request.method == "POST":
        form = CRSRegisterForm(
            request.POST,
            document=document,
        )

        if form.is_valid():
            crs = form.save(
                commit=False
            )

            crs.document = document

            crs.created_by = (
                request.user
            )

            if not crs.prepared_by:
                crs.prepared_by = (
                    request.user
                )

            if (
                crs.source_return_transaction
                and not crs.expected_comment_count
            ):
                crs.expected_comment_count = (
                    crs
                    .source_return_transaction
                    .customer_comment_count
                )

            crs.save()

            messages.success(
                request,
                (
                    "CRS register created successfully."
                ),
            )

            return redirect(
                "core:crs_detail",
                pk=crs.pk,
            )

    else:
        initial_data = {
            "cycle_number": max(
                document.current_cycle,
                1,
            ),

            "document_revision": (
                document.current_revision
            ),

            "opened_at": (
                timezone.localtime(
                    timezone.now()
                )
                .replace(
                    second=0,
                    microsecond=0,
                )
            ),

            "prepared_by": request.user,
        }

        if latest_return_transaction:
            initial_data[
                "source_return_transaction"
            ] = latest_return_transaction

            initial_data[
                "expected_comment_count"
            ] = (
                latest_return_transaction
                .customer_comment_count
            )

        form = CRSRegisterForm(
            document=document,
            initial=initial_data,
        )

    context = {
        "document": document,
        "form": form,
        "page_title": "Create CRS Register",
    }

    return render(
        request,
        "core/crs_form.html",
        context,
    )


@login_required
def crs_detail(
    request,
    pk,
):
    crs = get_object_or_404(
        CRSRegister.objects.select_related(
            "document",
            "document__vdrl",
            "document__vdrl__sales_order",
            "document__vdrl__sales_order__customer",
            "prepared_by",
            "reviewed_by",
            "approved_by",
            "crs_file",
        ),
        pk=pk,
    )

    if not can_view_document(
    request.user,
    crs.document,
):
        raise PermissionDenied

    comments = (
        crs.comments
        .select_related(
            "assigned_department",
            "assigned_person",
            "created_by",
            "updated_by",
        )
        .order_by(
            "comment_number"
        )
    )

    context = {
        "crs": crs,
        "document": crs.document,
        "comments": comments,
        "can_manage_crs": (
    can_manage_crs_for_document(
        request.user,
        crs.document,
    )
),
    }

    return render(
        request,
        "core/crs_detail.html",
        context,
    )


@login_required
def crs_edit(
    request,
    pk,
):
    crs = get_object_or_404(
        CRSRegister.objects.select_related(
            "document"
        ),
        pk=pk,
    )

    if not can_manage_crs_for_document(
    request.user,
    crs.document,
):
        raise PermissionDenied

    if request.method == "POST":
        form = CRSRegisterForm(
            request.POST,
            instance=crs,
            document=crs.document,
        )

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "CRS register updated successfully.",
            )

            return redirect(
                "core:crs_detail",
                pk=crs.pk,
            )

    else:
        form = CRSRegisterForm(
            instance=crs,
            document=crs.document,
        )

    context = {
        "document": crs.document,
        "crs": crs,
        "form": form,
        "page_title": "Edit CRS Register",
    }

    return render(
        request,
        "core/crs_form.html",
        context,
    )


@login_required
def crs_comment_create(
    request,
    crs_pk,
):
    crs = get_object_or_404(
        CRSRegister.objects.select_related(
            "document",
            "document__responsible_department",
            "document__responsible_person",
        ),
        pk=crs_pk,
    )

    if not can_manage_crs_for_document(
    request.user,
    crs.document,
):
        raise PermissionDenied

    if request.method == "POST":
        form = CRSCommentForm(
            request.POST
        )

        if form.is_valid():
            comment = form.save(
                commit=False
            )

            comment.crs = crs

            comment.created_by = (
                request.user
            )

            comment.updated_by = (
                request.user
            )

            comment.save()

            if (
                crs.status
                == CRSRegister.Status.DRAFT
            ):
                crs.status = (
                    CRSRegister
                    .Status
                    .IN_PROGRESS
                )

                crs.save(
                    update_fields=[
                        "status",
                        "updated_at",
                    ]
                )

            messages.success(
                request,
                (
                    f"Comment "
                    f"{comment.comment_number} "
                    "added successfully."
                ),
            )

            return redirect(
                "core:crs_detail",
                pk=crs.pk,
            )

    else:
        next_comment_number = (
            crs.comments.count()
            + 1
        )

        form = CRSCommentForm(
            initial={
                "comment_number": (
                    str(
                        next_comment_number
                    )
                ),

                "assigned_department": (
                    crs.document
                    .responsible_department
                ),

                "assigned_person": (
                    crs.document
                    .responsible_person
                ),

                "assigned_at": (
                    timezone.localtime(
                        timezone.now()
                    )
                    .replace(
                        second=0,
                        microsecond=0,
                    )
                ),
            }
        )

    context = {
        "crs": crs,
        "document": crs.document,
        "form": form,
        "page_title": "Add Customer Comment",
    }

    return render(
        request,
        "core/crs_comment_form.html",
        context,
    )


@login_required
def crs_comment_edit(
    request,
    pk,
):
    comment = get_object_or_404(
        CRSComment.objects.select_related(
            "crs",
            "crs__document",
        ),
        pk=pk,
    )

    if not can_manage_crs_for_document(
    request.user,
    comment.crs.document,
):
        raise PermissionDenied

    if request.method == "POST":
        form = CRSCommentForm(
            request.POST,
            instance=comment,
        )

        if form.is_valid():
            comment = form.save(
                commit=False
            )

            comment.updated_by = (
                request.user
            )

            comment.save()

            messages.success(
                request,
                (
                    f"Comment "
                    f"{comment.comment_number} "
                    "updated successfully."
                ),
            )

            return redirect(
                "core:crs_detail",
                pk=comment.crs.pk,
            )

    else:
        form = CRSCommentForm(
            instance=comment
        )

    context = {
        "crs": comment.crs,
        "document": (
            comment.crs.document
        ),
        "comment": comment,
        "form": form,
        "page_title": (
            f"Edit Comment "
            f"{comment.comment_number}"
        ),
    }

    return render(
        request,
        "core/crs_comment_form.html",
        context,
    )