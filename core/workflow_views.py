from django.contrib import messages
from django.contrib.auth.decorators import (
    login_required,
)
from django.core.exceptions import (
    PermissionDenied,
    ValidationError,
)
from django.db.models import Q
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)

from .access import (
    filter_documents_for_user,
)
from .models import (
    DocumentOpenPoint,
    DocumentWorkflow,
    SalesOrderVDRLDocument,
)
from .workflow_forms import (
    AssignContributorForm,
    AssignDepartmentForm,
    DepartmentReviewForm,
    OpenPointDecisionForm,
    OpenPointResponseForm,
    RaiseOpenPointForm,
    ReassignContributorForm,
    WorkflowCommentForm,
)
from .workflow_services import (
    assign_contributor,
    assign_department,
    department_review,
    raise_open_point,
    reassign_contributor,
    respond_open_point,
    review_open_point_response,
    submit_for_department_review,
)


def _accessible_document(
    request,
    document_id,
):
    queryset = (
        SalesOrderVDRLDocument
        .objects
        .select_related(
            "vdrl",
            "vdrl__sales_order",
        )
    )

    queryset = filter_documents_for_user(
        request.user,
        queryset,
    )

    return get_object_or_404(
        queryset,
        pk=document_id,
    )


def _workflow(
    request,
    document_id,
):
    document = _accessible_document(
        request,
        document_id,
    )

    workflow, _ = (
        DocumentWorkflow.objects
        .get_or_create(
            document=document,
        )
    )

    return workflow


def _add_validation_error(
    form,
    exc,
):
    if hasattr(
        exc,
        "messages",
    ):
        for message in exc.messages:
            form.add_error(
                None,
                message,
            )
    else:
        form.add_error(
            None,
            str(exc),
        )


@login_required
def document_workflow(
    request,
    document_id,
):
    workflow = _workflow(
        request,
        document_id,
    )

    open_points = (
        workflow
        .open_points
        .select_related(
            "application_engineer",
            "raised_by",
            "closed_by",
        )
        .prefetch_related(
            "transactions",
        )
    )

    transactions = (
        workflow
        .transactions
        .select_related(
            "actor",
        )
    )

    context = {
        "workflow": workflow,
        "document": workflow.document,
        "open_points": open_points,
        "transactions": transactions,
    }

    return render(
        request,
        "core/document_workflow.html",
        context,
    )


@login_required
def workflow_assign_department(
    request,
    document_id,
):
    workflow = _workflow(
        request,
        document_id,
    )

    form = AssignDepartmentForm(
        request.POST or None,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        try:
            assign_department(
                workflow_id=workflow.pk,
                department=(
                    form.cleaned_data[
                        "department"
                    ]
                ),
                actor=request.user,
                comment=(
                    form.cleaned_data[
                        "comment"
                    ]
                ),
            )

        except ValidationError as exc:
            _add_validation_error(
                form,
                exc,
            )

        else:
            messages.success(
                request,
                "Department assigned successfully.",
            )

            return redirect(
                "core:document_workflow",
                document_id=document_id,
            )

    return render(
        request,
        "core/workflow_action_form.html",
        {
            "title": "Assign Department",
            "form": form,
            "workflow": workflow,
        },
    )


@login_required
def workflow_assign_contributor(
    request,
    document_id,
):
    workflow = _workflow(
        request,
        document_id,
    )

    form = AssignContributorForm(
        request.POST or None,
        department=workflow.department,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        try:
            assign_contributor(
                workflow_id=workflow.pk,
                contributor=(
                    form.cleaned_data[
                        "contributor"
                    ]
                ),
                planned_submission_date=(
                    form.cleaned_data[
                        "planned_submission_date"
                    ]
                ),
                actor=request.user,
                comment=(
                    form.cleaned_data[
                        "comment"
                    ]
                ),
            )

        except ValidationError as exc:
            _add_validation_error(
                form,
                exc,
            )

        else:
            messages.success(
                request,
                "Contributor assigned successfully.",
            )

            return redirect(
                "core:document_workflow",
                document_id=document_id,
            )

    return render(
        request,
        "core/workflow_action_form.html",
        {
            "title": "Assign Contributor",
            "form": form,
            "workflow": workflow,
        },
    )


@login_required
def workflow_reassign_contributor(
    request,
    document_id,
):
    workflow = _workflow(
        request,
        document_id,
    )

    form = ReassignContributorForm(
        request.POST or None,
        department=workflow.department,
        initial={
            "planned_submission_date": (
                workflow
                .planned_submission_date
            ),
        },
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        try:
            reassign_contributor(
                workflow_id=workflow.pk,
                contributor=(
                    form.cleaned_data[
                        "contributor"
                    ]
                ),
                planned_submission_date=(
                    form.cleaned_data[
                        "planned_submission_date"
                    ]
                ),
                actor=request.user,
                reason=(
                    form.cleaned_data[
                        "reason"
                    ]
                ),
            )

        except ValidationError as exc:
            _add_validation_error(
                form,
                exc,
            )

        else:
            messages.success(
                request,
                "Task reassigned successfully.",
            )

            return redirect(
                "core:document_workflow",
                document_id=document_id,
            )

    return render(
        request,
        "core/workflow_action_form.html",
        {
            "title": "Reassign Contributor",
            "form": form,
            "workflow": workflow,
        },
    )


@login_required
def workflow_raise_open_point(
    request,
    document_id,
):
    workflow = _workflow(
        request,
        document_id,
    )

    form = RaiseOpenPointForm(
        request.POST or None,
        request.FILES or None,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        try:
            raise_open_point(
                workflow_id=workflow.pk,
                actor=request.user,
                subject=(
                    form.cleaned_data[
                        "subject"
                    ]
                ),
                description=(
                    form.cleaned_data[
                        "description"
                    ]
                ),
                priority=(
                    form.cleaned_data[
                        "priority"
                    ]
                ),
                required_by=(
                    form.cleaned_data[
                        "required_by"
                    ]
                ),
                is_blocking=(
                    form.cleaned_data[
                        "is_blocking"
                    ]
                ),
                attachment=(
                    form.cleaned_data[
                        "attachment"
                    ]
                ),
            )

        except ValidationError as exc:
            _add_validation_error(
                form,
                exc,
            )

        else:
            messages.success(
                request,
                "Open point raised successfully.",
            )

            return redirect(
                "core:document_workflow",
                document_id=document_id,
            )

    return render(
        request,
        "core/workflow_action_form.html",
        {
            "title": "Raise Missing-Data Open Point",
            "form": form,
            "workflow": workflow,
        },
    )


@login_required
def open_point_respond(
    request,
    open_point_id,
):
    open_point = get_object_or_404(
        DocumentOpenPoint.objects.select_related(
            "workflow__document",
        ),
        pk=open_point_id,
    )

    _accessible_document(
        request,
        open_point.workflow.document_id,
    )

    form = OpenPointResponseForm(
        request.POST or None,
        request.FILES or None,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        try:
            respond_open_point(
                open_point_id=open_point.pk,
                actor=request.user,
                response=(
                    form.cleaned_data[
                        "response"
                    ]
                ),
                attachment=(
                    form.cleaned_data[
                        "attachment"
                    ]
                ),
            )

        except ValidationError as exc:
            _add_validation_error(
                form,
                exc,
            )

        else:
            messages.success(
                request,
                "Response submitted successfully.",
            )

            return redirect(
                "core:document_workflow",
                document_id=(
                    open_point
                    .workflow
                    .document_id
                ),
            )

    return render(
        request,
        "core/workflow_action_form.html",
        {
            "title": (
                f"Respond to "
                f"{open_point.reference_number}"
            ),
            "form": form,
            "workflow": open_point.workflow,
        },
    )


@login_required
def open_point_decide(
    request,
    open_point_id,
):
    open_point = get_object_or_404(
        DocumentOpenPoint.objects.select_related(
            "workflow__document",
        ),
        pk=open_point_id,
    )

    _accessible_document(
        request,
        open_point.workflow.document_id,
    )

    form = OpenPointDecisionForm(
        request.POST or None,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        try:
            review_open_point_response(
                open_point_id=open_point.pk,
                actor=request.user,
                decision=(
                    form.cleaned_data[
                        "decision"
                    ]
                ),
                comment=(
                    form.cleaned_data[
                        "comment"
                    ]
                ),
            )

        except ValidationError as exc:
            _add_validation_error(
                form,
                exc,
            )

        else:
            messages.success(
                request,
                "Open-point review recorded.",
            )

            return redirect(
                "core:document_workflow",
                document_id=(
                    open_point
                    .workflow
                    .document_id
                ),
            )

    return render(
        request,
        "core/workflow_action_form.html",
        {
            "title": (
                f"Verify "
                f"{open_point.reference_number}"
            ),
            "form": form,
            "workflow": open_point.workflow,
        },
    )


@login_required
def workflow_submit_for_review(
    request,
    document_id,
):
    workflow = _workflow(
        request,
        document_id,
    )

    form = WorkflowCommentForm(
        request.POST or None,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        try:
            submit_for_department_review(
                workflow_id=workflow.pk,
                actor=request.user,
                comment=(
                    form.cleaned_data[
                        "comment"
                    ]
                ),
            )

        except ValidationError as exc:
            _add_validation_error(
                form,
                exc,
            )

        else:
            messages.success(
                request,
                "Document submitted for "
                "department review.",
            )

            return redirect(
                "core:document_workflow",
                document_id=document_id,
            )

    return render(
        request,
        "core/workflow_action_form.html",
        {
            "title": (
                "Submit for Department Review"
            ),
            "form": form,
            "workflow": workflow,
        },
    )


@login_required
def workflow_department_review(
    request,
    document_id,
):
    workflow = _workflow(
        request,
        document_id,
    )

    form = DepartmentReviewForm(
        request.POST or None,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        try:
            department_review(
                workflow_id=workflow.pk,
                actor=request.user,
                decision=(
                    form.cleaned_data[
                        "decision"
                    ]
                ),
                comment=(
                    form.cleaned_data[
                        "comment"
                    ]
                ),
            )

        except ValidationError as exc:
            _add_validation_error(
                form,
                exc,
            )

        else:
            messages.success(
                request,
                "Department review recorded.",
            )

            return redirect(
                "core:document_workflow",
                document_id=document_id,
            )

    return render(
        request,
        "core/workflow_action_form.html",
        {
            "title": "Department Review",
            "form": form,
            "workflow": workflow,
        },
    )


@login_required
def my_work_bucket(
    request,
):
    accessible_documents = (
        filter_documents_for_user(
            request.user,
            SalesOrderVDRLDocument
            .objects
            .all(),
        )
    )

    workflows = (
        DocumentWorkflow
        .objects
        .filter(
            document__in=(
                accessible_documents
            )
        )
        .select_related(
            "document",
            "document__vdrl__sales_order",
            "department",
            "contributor",
        )
    )

    my_contributor_tasks = workflows.filter(
        contributor=request.user,
    ).exclude(
        status__in=[
            DocumentWorkflow.Status.CUSTOMER_APPROVED,
            DocumentWorkflow.Status.CANCELLED,
        ],
    )

    manager_tasks = workflows.filter(
        Q(
            department__manager=request.user
        )
        |
        Q(
            department__employee_profiles__user=(
                request.user
            ),
            department__employee_profiles__user__groups__name=(
                "Department Managers"
            ),
        )
    ).filter(
        status__in=[
            DocumentWorkflow
            .Status
            .WITH_DEPARTMENT_MANAGER,

            DocumentWorkflow
            .Status
            .SUBMITTED_FOR_DEPARTMENT_REVIEW,
        ],
    ).distinct()

    controller_tasks = workflows.filter(
        document__vdrl__sales_order__document_controller=(
            request.user
        ),
        status__in=[
            DocumentWorkflow
            .Status
            .WITH_DOCUMENT_CONTROLLER,

            DocumentWorkflow
            .Status
            .READY_FOR_CUSTOMER_SUBMISSION,
        ],
    )

    ae_open_points = (
        DocumentOpenPoint
        .objects
        .filter(
            workflow__document__in=(
                accessible_documents
            ),
            application_engineer=request.user,
        )
        .exclude(
            status__in=[
                DocumentOpenPoint.Status.CLOSED,
                DocumentOpenPoint.Status.CANCELLED,
            ],
        )
        .select_related(
            "workflow__document",
        )
    )

    return render(
        request,
        "core/work_bucket.html",
        {
            "my_contributor_tasks": (
                my_contributor_tasks
            ),
            "manager_tasks": manager_tasks,
            "controller_tasks": (
                controller_tasks
            ),
            "ae_open_points": ae_open_points,
        },
    )