from functools import partial

from django.core.exceptions import (
    PermissionDenied,
    ValidationError,
)
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .audit import record_audit_event
from .models import (
    AuditLog,
    DocumentAssignmentHistory,
    DocumentOpenPoint,
    DocumentOpenPointTransaction,
    DocumentWorkflow,
    DocumentWorkflowTransaction,
    EmployeeProfile,
    InAppNotification,
)
from .notifications import (
    create_in_app_notification,
)


def _sales_order(workflow):
    return (
        workflow
        .document
        .vdrl
        .sales_order
    )


def _is_global_user(user):
    return bool(
        user.is_superuser
        or user.has_perm(
            "core.view_all_vdrl_data"
        )
    )


def _is_document_controller(
    user,
    workflow,
):
    sales_order = _sales_order(
        workflow
    )

    return bool(
        _is_global_user(user)
        or getattr(
            sales_order,
            "document_controller_id",
            None,
        ) == user.id
    )


def _is_department_manager(
    user,
    workflow,
):
    if _is_global_user(user):
        return True

    if not workflow.department_id:
        return False

    if getattr(
        workflow.department,
        "manager_id",
        None,
    ) == user.id:
        return True

    profile = (
        EmployeeProfile
        .objects
        .filter(
            user=user,
        )
        .first()
    )

    return bool(
        profile
        and profile.department_id
        == workflow.department_id
        and user.groups.filter(
            name="Department Managers",
        ).exists()
    )


def _is_contributor(
    user,
    workflow,
):
    return bool(
        _is_global_user(user)
        or workflow.contributor_id
        == user.id
    )


def _is_application_engineer(
    user,
    workflow,
):
    sales_order = _sales_order(
        workflow
    )

    return bool(
        _is_global_user(user)
        or getattr(
            sales_order,
            "application_engineer_id",
            None,
        ) == user.id
    )


def _validate_contributor_department(
    workflow,
    contributor,
):
    profile = (
        EmployeeProfile
        .objects
        .filter(
            user=contributor,
        )
        .first()
    )

    if not profile:
        raise ValidationError(
            "The selected contributor does not "
            "have an employee profile."
        )

    if (
        profile.department_id
        != workflow.department_id
    ):
        raise ValidationError(
            "The contributor must belong to the "
            "assigned department."
        )


def _authorize_sales_order_user(
    workflow,
    user,
):
    if not user:
        return

    sales_order = _sales_order(
        workflow
    )

    sales_order.authorized_users.add(
        user
    )


def _notify(
    *,
    user,
    title,
    message,
    workflow,
    category,
    priority,
    dedupe_key,
):
    if not user:
        return

    url = reverse(
        "core:document_workflow",
        args=[
            workflow.document_id
        ],
    )

    transaction.on_commit(
        partial(
            create_in_app_notification,
            recipient=user,
            title=title,
            message=message,
            category=category,
            priority=priority,
            url=url,
            dedupe_key=dedupe_key,
            related_document=(
                workflow.document
            ),
        )
    )


def _transition(
    *,
    workflow,
    new_status,
    actor,
    action,
    comment="",
    revision="",
):
    now = timezone.now()

    old_status = workflow.status

    elapsed_seconds = max(
        0,
        int(
            (
                now
                - workflow.current_action_since
            ).total_seconds()
        ),
    )

    workflow.status = new_status
    workflow.current_action_since = now
    workflow.save()

    transaction_record = (
        DocumentWorkflowTransaction
        .objects
        .create(
            workflow=workflow,
            action=action,
            from_status=old_status,
            to_status=new_status,
            actor=actor,
            comment=comment,
            revision=revision,
            elapsed_seconds=elapsed_seconds,
        )
    )

    record_audit_event(
        action=(
            AuditLog.Action.WORKFLOW
        ),
        instance=workflow.document,
        actor=actor,
        description=(
            f"Workflow changed from "
            f"{old_status} to {new_status}."
        ),
        event_data={
            "workflow_transaction_id": (
                transaction_record.pk
            ),
            "from_status": old_status,
            "to_status": new_status,
            "elapsed_seconds": (
                elapsed_seconds
            ),
            "comment": comment,
        },
    )

    return workflow


def _open_point_event(
    *,
    open_point,
    action,
    actor,
    responsible_party,
    from_status,
    to_status,
    comment="",
    attachment=None,
):
    previous_event = (
        open_point
        .transactions
        .order_by(
            "-created_at",
            "-id",
        )
        .first()
    )

    now = timezone.now()

    period_start = (
        previous_event.created_at
        if previous_event
        else open_point.opened_at
    )

    elapsed_seconds = max(
        0,
        int(
            (
                now
                - period_start
            ).total_seconds()
        ),
    )

    return (
        DocumentOpenPointTransaction
        .objects
        .create(
            open_point=open_point,
            action=action,
            from_status=from_status,
            to_status=to_status,
            performed_by=actor,
            responsible_party=(
                responsible_party
            ),
            comment=comment,
            attachment=attachment,
            elapsed_since_previous_seconds=(
                elapsed_seconds
            ),
        )
    )


def _refresh_workflow_open_point_status(
    workflow,
    actor,
):
    active_points = (
        workflow
        .open_points
        .exclude(
            status__in=[
                DocumentOpenPoint
                .Status
                .CLOSED,

                DocumentOpenPoint
                .Status
                .CANCELLED,
            ],
        )
    )

    if not active_points.exists():
        resume_status = (
            workflow.resume_status
            or DocumentWorkflow
            .Status
            .WITH_CONTRIBUTOR
        )

        workflow.resume_status = ""

        _transition(
            workflow=workflow,
            new_status=resume_status,
            actor=actor,
            action=(
                DocumentWorkflowTransaction
                .Action
                .OPEN_POINT_CLOSED
            ),
            comment=(
                "All blocking open points "
                "are closed."
            ),
        )

        return

    awaiting_ae = active_points.filter(
        status__in=[
            DocumentOpenPoint
            .Status
            .OPEN,

            DocumentOpenPoint
            .Status
            .MORE_INFORMATION_REQUIRED,
        ],
    ).exists()

    new_status = (
        DocumentWorkflow
        .Status
        .AWAITING_APPLICATION_ENGINEER
        if awaiting_ae
        else DocumentWorkflow
        .Status
        .CONTRIBUTOR_REVIEWING_RESPONSE
    )

    if workflow.status != new_status:
        _transition(
            workflow=workflow,
            new_status=new_status,
            actor=actor,
            action=(
                DocumentWorkflowTransaction
                .Action
                .OPEN_POINT_RESPONDED
            ),
        )


@transaction.atomic
def assign_department(
    *,
    workflow_id,
    department,
    actor,
    comment="",
):
    workflow = (
        DocumentWorkflow
        .objects
        .select_for_update()
        .select_related(
            "document__vdrl__sales_order",
            "department",
        )
        .get(
            pk=workflow_id
        )
    )

    if not _is_document_controller(
        actor,
        workflow,
    ):
        raise PermissionDenied(
            "Only the assigned Document "
            "Controller can select the department."
        )

    previous_department = (
        workflow.department
    )

    workflow.department = department
    workflow.contributor = None
    workflow.planned_submission_date = None
    workflow.department_assigned_by = actor
    workflow.department_assigned_at = (
        timezone.now()
    )

    _transition(
        workflow=workflow,
        new_status=(
            DocumentWorkflow
            .Status
            .WITH_DEPARTMENT_MANAGER
        ),
        actor=actor,
        action=(
            DocumentWorkflowTransaction
            .Action
            .DEPARTMENT_ASSIGNED
        ),
        comment=comment,
    )

    DocumentAssignmentHistory.objects.create(
        workflow=workflow,
        action=(
            DocumentAssignmentHistory
            .Action
            .DEPARTMENT_ASSIGNED
        ),
        previous_department=(
            previous_department
        ),
        new_department=department,
        performed_by=actor,
        reason=comment,
    )

    department_manager = getattr(
        department,
        "manager",
        None,
    )

    _authorize_sales_order_user(
        workflow,
        department_manager,
    )

    _notify(
        user=department_manager,
        title="VDRL document sent to your department",
        message=(
            f"{workflow.document} requires "
            f"contributor assignment."
        ),
        workflow=workflow,
        category=(
            InAppNotification
            .Category
            .ASSIGNMENT
        ),
        priority=(
            InAppNotification
            .Priority
            .NORMAL
        ),
        dedupe_key=(
            f"department-assignment:"
            f"{workflow.pk}:"
            f"{workflow.updated_at.isoformat()}"
        ),
    )

    return workflow


@transaction.atomic
def assign_contributor(
    *,
    workflow_id,
    contributor,
    planned_submission_date,
    actor,
    comment="",
):
    workflow = (
        DocumentWorkflow
        .objects
        .select_for_update()
        .select_related(
            "document__vdrl__sales_order",
            "department",
        )
        .get(
            pk=workflow_id
        )
    )

    if not _is_department_manager(
        actor,
        workflow,
    ):
        raise PermissionDenied(
            "Only the assigned Department "
            "Manager can select the contributor."
        )

    if not workflow.department_id:
        raise ValidationError(
            "The Document Controller must select "
            "a department first."
        )

    _validate_contributor_department(
        workflow,
        contributor,
    )

    workflow.contributor = contributor
    workflow.planned_submission_date = (
        planned_submission_date
    )
    workflow.contributor_assigned_by = actor
    workflow.contributor_assigned_at = (
        timezone.now()
    )

    _transition(
        workflow=workflow,
        new_status=(
            DocumentWorkflow
            .Status
            .WITH_CONTRIBUTOR
        ),
        actor=actor,
        action=(
            DocumentWorkflowTransaction
            .Action
            .CONTRIBUTOR_ASSIGNED
        ),
        comment=comment,
    )

    DocumentAssignmentHistory.objects.create(
        workflow=workflow,
        action=(
            DocumentAssignmentHistory
            .Action
            .CONTRIBUTOR_ASSIGNED
        ),
        new_department=workflow.department,
        new_contributor=contributor,
        new_planned_date=(
            planned_submission_date
        ),
        performed_by=actor,
        reason=comment,
    )

    _authorize_sales_order_user(
        workflow,
        contributor,
    )

    _notify(
        user=contributor,
        title="VDRL document assigned to you",
        message=(
            f"{workflow.document} is due on "
            f"{planned_submission_date:%d-%b-%Y}."
        ),
        workflow=workflow,
        category=(
            InAppNotification
            .Category
            .ASSIGNMENT
        ),
        priority=(
            InAppNotification
            .Priority
            .NORMAL
        ),
        dedupe_key=(
            f"contributor-assignment:"
            f"{workflow.pk}:"
            f"{workflow.updated_at.isoformat()}"
        ),
    )

    return workflow


@transaction.atomic
def reassign_contributor(
    *,
    workflow_id,
    contributor,
    actor,
    reason,
    planned_submission_date=None,
):
    workflow = (
        DocumentWorkflow
        .objects
        .select_for_update()
        .select_related(
            "document__vdrl__sales_order",
            "department",
            "contributor",
        )
        .get(
            pk=workflow_id
        )
    )

    if not _is_department_manager(
        actor,
        workflow,
    ):
        raise PermissionDenied(
            "Only the Department Manager can "
            "reassign this task."
        )

    if not reason.strip():
        raise ValidationError(
            "A reassignment reason is required."
        )

    _validate_contributor_department(
        workflow,
        contributor,
    )

    previous_contributor = (
        workflow.contributor
    )

    previous_planned_date = (
        workflow.planned_submission_date
    )

    workflow.contributor = contributor
    workflow.last_reassigned_at = (
        timezone.now()
    )

    if planned_submission_date:
        workflow.planned_submission_date = (
            planned_submission_date
        )

    if workflow.has_blocking_open_points:
        new_status = (
            DocumentWorkflow
            .Status
            .AWAITING_APPLICATION_ENGINEER
        )
    else:
        new_status = (
            DocumentWorkflow
            .Status
            .WITH_CONTRIBUTOR
        )

    _transition(
        workflow=workflow,
        new_status=new_status,
        actor=actor,
        action=(
            DocumentWorkflowTransaction
            .Action
            .CONTRIBUTOR_REASSIGNED
        ),
        comment=reason,
    )

    DocumentAssignmentHistory.objects.create(
        workflow=workflow,
        action=(
            DocumentAssignmentHistory
            .Action
            .CONTRIBUTOR_REASSIGNED
        ),
        previous_department=(
            workflow.department
        ),
        new_department=workflow.department,
        previous_contributor=(
            previous_contributor
        ),
        new_contributor=contributor,
        previous_planned_date=(
            previous_planned_date
        ),
        new_planned_date=(
            workflow.planned_submission_date
        ),
        performed_by=actor,
        reason=reason,
    )

    for open_point in (
        workflow.open_points.exclude(
            status__in=[
                DocumentOpenPoint.Status.CLOSED,
                DocumentOpenPoint.Status.CANCELLED,
            ]
        )
    ):
        _open_point_event(
            open_point=open_point,
            action=(
                DocumentOpenPointTransaction
                .Action
                .CONTRIBUTOR_REASSIGNED
            ),
            actor=actor,
            responsible_party=(
                DocumentOpenPointTransaction
                .ResponsibleParty
                .DEPARTMENT_MANAGER
            ),
            from_status=open_point.status,
            to_status=open_point.status,
            comment=(
                f"Contributor changed from "
                f"{previous_contributor} to "
                f"{contributor}. Reason: {reason}"
            ),
        )

        _notify(
            user=open_point.application_engineer,
            title="Open-point contributor changed",
            message=(
                f"{open_point.reference_number}: "
                f"new contributor is {contributor}."
            ),
            workflow=workflow,
            category=(
                InAppNotification
                .Category
                .WORKFLOW
            ),
            priority=(
                InAppNotification
                .Priority
                .NORMAL
            ),
            dedupe_key=(
                f"open-point-reassignment:"
                f"{open_point.pk}:"
                f"{workflow.updated_at.isoformat()}"
            ),
        )

    _authorize_sales_order_user(
        workflow,
        contributor,
    )

    _notify(
        user=previous_contributor,
        title="VDRL task reassigned",
        message=(
            f"{workflow.document} was reassigned "
            f"to {contributor}."
        ),
        workflow=workflow,
        category=(
            InAppNotification
            .Category
            .ASSIGNMENT
        ),
        priority=(
            InAppNotification
            .Priority
            .NORMAL
        ),
        dedupe_key=(
            f"reassigned-from:"
            f"{workflow.pk}:"
            f"{workflow.updated_at.isoformat()}"
        ),
    )

    _notify(
        user=contributor,
        title="VDRL task reassigned to you",
        message=(
            f"{workflow.document}. "
            f"Reason: {reason}"
        ),
        workflow=workflow,
        category=(
            InAppNotification
            .Category
            .ASSIGNMENT
        ),
        priority=(
            InAppNotification
            .Priority
            .HIGH
        ),
        dedupe_key=(
            f"reassigned-to:"
            f"{workflow.pk}:"
            f"{workflow.updated_at.isoformat()}"
        ),
    )

    return workflow


@transaction.atomic
def raise_open_point(
    *,
    workflow_id,
    actor,
    subject,
    description,
    priority,
    required_by=None,
    is_blocking=True,
    attachment=None,
):
    workflow = (
        DocumentWorkflow
        .objects
        .select_for_update()
        .select_related(
            "document__vdrl__sales_order",
            "contributor",
        )
        .get(
            pk=workflow_id
        )
    )

    if not _is_contributor(
        actor,
        workflow,
    ):
        raise PermissionDenied(
            "Only the currently assigned "
            "contributor can raise an open point."
        )

    allowed_statuses = {
        DocumentWorkflow.Status.WITH_CONTRIBUTOR,
        DocumentWorkflow.Status.RETURNED_FOR_REWORK,
        DocumentWorkflow.Status.CUSTOMER_RETURNED,
    }

    if workflow.status not in allowed_statuses:
        raise ValidationError(
            "An open point cannot be raised in "
            "the current workflow status."
        )

    sales_order = _sales_order(
        workflow
    )

    application_engineer = getattr(
        sales_order,
        "application_engineer",
        None,
    )

    if not application_engineer:
        raise ValidationError(
            "No Application Engineer is assigned "
            "to this Sales Order."
        )

    next_number = (
        workflow.open_points.count()
        + 1
    )

    reference_number = (
        f"OP-{next_number:03d}"
    )

    if is_blocking and not workflow.resume_status:
        workflow.resume_status = (
            workflow.status
        )
        workflow.save(
            update_fields=[
                "resume_status",
                "updated_at",
            ]
        )

    open_point = (
        DocumentOpenPoint
        .objects
        .create(
            workflow=workflow,
            reference_number=(
                reference_number
            ),
            subject=subject,
            description=description,
            priority=priority,
            is_blocking=is_blocking,
            application_engineer=(
                application_engineer
            ),
            raised_by=actor,
            required_by=required_by,
        )
    )

    _open_point_event(
        open_point=open_point,
        action=(
            DocumentOpenPointTransaction
            .Action
            .RAISED
        ),
        actor=actor,
        responsible_party=(
            DocumentOpenPointTransaction
            .ResponsibleParty
            .APPLICATION_ENGINEER
        ),
        from_status="",
        to_status=(
            DocumentOpenPoint
            .Status
            .OPEN
        ),
        comment=description,
        attachment=attachment,
    )

    if is_blocking:
        _transition(
            workflow=workflow,
            new_status=(
                DocumentWorkflow
                .Status
                .AWAITING_APPLICATION_ENGINEER
            ),
            actor=actor,
            action=(
                DocumentWorkflowTransaction
                .Action
                .OPEN_POINT_RAISED
            ),
            comment=(
                f"{reference_number}: {subject}"
            ),
        )

    _authorize_sales_order_user(
        workflow,
        application_engineer,
    )

    _notify(
        user=application_engineer,
        title="Missing information requested",
        message=(
            f"{reference_number}: {subject} "
            f"for {workflow.document}."
        ),
        workflow=workflow,
        category=(
            InAppNotification
            .Category
            .WORKFLOW
        ),
        priority=(
            InAppNotification
            .Priority
            .HIGH
            if priority in [
                DocumentOpenPoint
                .Priority
                .HIGH,

                DocumentOpenPoint
                .Priority
                .URGENT,
            ]
            else InAppNotification
            .Priority
            .NORMAL
        ),
        dedupe_key=(
            f"open-point-raised:"
            f"{open_point.pk}"
        ),
    )

    return open_point


@transaction.atomic
def respond_open_point(
    *,
    open_point_id,
    actor,
    response,
    attachment=None,
):
    open_point = (
        DocumentOpenPoint
        .objects
        .select_for_update()
        .select_related(
            "workflow__document__vdrl__sales_order",
            "workflow__contributor",
        )
        .get(
            pk=open_point_id
        )
    )

    workflow = open_point.workflow

    if not _is_application_engineer(
        actor,
        workflow,
    ):
        raise PermissionDenied(
            "Only the assigned Application "
            "Engineer can respond."
        )

    if open_point.status not in [
        DocumentOpenPoint.Status.OPEN,
        DocumentOpenPoint
        .Status
        .MORE_INFORMATION_REQUIRED,
    ]:
        raise ValidationError(
            "This open point is not waiting "
            "for an Application Engineer response."
        )

    old_status = open_point.status
    now = timezone.now()

    open_point.status = (
        DocumentOpenPoint
        .Status
        .RESPONDED
    )

    if not open_point.first_response_at:
        open_point.first_response_at = now

    open_point.latest_response_at = now
    open_point.response_cycle += 1

    open_point.save()

    _open_point_event(
        open_point=open_point,
        action=(
            DocumentOpenPointTransaction
            .Action
            .RESPONDED
        ),
        actor=actor,
        responsible_party=(
            DocumentOpenPointTransaction
            .ResponsibleParty
            .APPLICATION_ENGINEER
        ),
        from_status=old_status,
        to_status=open_point.status,
        comment=response,
        attachment=attachment,
    )

    _refresh_workflow_open_point_status(
        workflow,
        actor,
    )

    _notify(
        user=workflow.contributor,
        title="Application Engineer responded",
        message=(
            f"{open_point.reference_number}: "
            f"{open_point.subject}. "
            f"Please verify the response."
        ),
        workflow=workflow,
        category=(
            InAppNotification
            .Category
            .WORKFLOW
        ),
        priority=(
            InAppNotification
            .Priority
            .HIGH
        ),
        dedupe_key=(
            f"open-point-response:"
            f"{open_point.pk}:"
            f"{open_point.response_cycle}"
        ),
    )

    return open_point


@transaction.atomic
def review_open_point_response(
    *,
    open_point_id,
    actor,
    decision,
    comment,
):
    open_point = (
        DocumentOpenPoint
        .objects
        .select_for_update()
        .select_related(
            "workflow__document__vdrl__sales_order",
            "workflow__contributor",
            "application_engineer",
        )
        .get(
            pk=open_point_id
        )
    )

    workflow = open_point.workflow

    if not _is_contributor(
        actor,
        workflow,
    ):
        raise PermissionDenied(
            "Only the current contributor can "
            "accept or reject this response."
        )

    if (
        open_point.status
        != DocumentOpenPoint.Status.RESPONDED
    ):
        raise ValidationError(
            "This open point has not received "
            "a response awaiting verification."
        )

    old_status = open_point.status

    if decision == "CLOSE":
        if not comment.strip():
            raise ValidationError(
                "A closure remark is required."
            )

        open_point.status = (
            DocumentOpenPoint
            .Status
            .CLOSED
        )
        open_point.closed_at = timezone.now()
        open_point.closed_by = actor
        open_point.closure_remark = comment
        open_point.save()

        _open_point_event(
            open_point=open_point,
            action=(
                DocumentOpenPointTransaction
                .Action
                .CLOSED
            ),
            actor=actor,
            responsible_party=(
                DocumentOpenPointTransaction
                .ResponsibleParty
                .CONTRIBUTOR
            ),
            from_status=old_status,
            to_status=open_point.status,
            comment=comment,
        )

        notification_title = (
            "Open point closed"
        )

    elif decision == "MORE_INFORMATION":
        if not comment.strip():
            raise ValidationError(
                "Explain what information "
                "is still required."
            )

        open_point.status = (
            DocumentOpenPoint
            .Status
            .MORE_INFORMATION_REQUIRED
        )
        open_point.save(
            update_fields=[
                "status",
            ]
        )

        _open_point_event(
            open_point=open_point,
            action=(
                DocumentOpenPointTransaction
                .Action
                .MORE_INFORMATION_REQUIRED
            ),
            actor=actor,
            responsible_party=(
                DocumentOpenPointTransaction
                .ResponsibleParty
                .CONTRIBUTOR
            ),
            from_status=old_status,
            to_status=open_point.status,
            comment=comment,
        )

        notification_title = (
            "More information required"
        )

    else:
        raise ValidationError(
            "Invalid open-point decision."
        )

    _refresh_workflow_open_point_status(
        workflow,
        actor,
    )

    _notify(
        user=open_point.application_engineer,
        title=notification_title,
        message=(
            f"{open_point.reference_number}: "
            f"{comment}"
        ),
        workflow=workflow,
        category=(
            InAppNotification
            .Category
            .WORKFLOW
        ),
        priority=(
            InAppNotification
            .Priority
            .HIGH
        ),
        dedupe_key=(
            f"open-point-review:"
            f"{open_point.pk}:"
            f"{open_point.status}:"
            f"{timezone.now().isoformat()}"
        ),
    )

    return open_point


@transaction.atomic
def submit_for_department_review(
    *,
    workflow_id,
    actor,
    comment="",
):
    workflow = (
        DocumentWorkflow
        .objects
        .select_for_update()
        .select_related(
            "document__vdrl__sales_order",
            "department",
            "contributor",
        )
        .get(
            pk=workflow_id
        )
    )

    if not _is_contributor(
        actor,
        workflow,
    ):
        raise PermissionDenied(
            "Only the assigned contributor can "
            "submit this document."
        )

    if workflow.has_blocking_open_points:
        raise ValidationError(
            "The document cannot be submitted "
            "while blocking open points remain open."
        )

    allowed_statuses = {
        DocumentWorkflow.Status.WITH_CONTRIBUTOR,
        DocumentWorkflow.Status.RETURNED_FOR_REWORK,
        DocumentWorkflow.Status.CUSTOMER_RETURNED,
    }

    if workflow.status not in allowed_statuses:
        raise ValidationError(
            "This document cannot be submitted "
            "from its current workflow status."
        )

    _transition(
        workflow=workflow,
        new_status=(
            DocumentWorkflow
            .Status
            .SUBMITTED_FOR_DEPARTMENT_REVIEW
        ),
        actor=actor,
        action=(
            DocumentWorkflowTransaction
            .Action
            .SUBMITTED_FOR_REVIEW
        ),
        comment=comment,
    )

    manager = getattr(
        workflow.department,
        "manager",
        None,
    )

    _notify(
        user=manager,
        title="Document submitted for review",
        message=str(
            workflow.document
        ),
        workflow=workflow,
        category=(
            InAppNotification
            .Category
            .WORKFLOW
        ),
        priority=(
            InAppNotification
            .Priority
            .HIGH
        ),
        dedupe_key=(
            f"department-review:"
            f"{workflow.pk}:"
            f"{workflow.updated_at.isoformat()}"
        ),
    )

    return workflow


@transaction.atomic
def department_review(
    *,
    workflow_id,
    actor,
    decision,
    comment,
):
    workflow = (
        DocumentWorkflow
        .objects
        .select_for_update()
        .select_related(
            "document__vdrl__sales_order",
            "department",
            "contributor",
        )
        .get(
            pk=workflow_id
        )
    )

    if not _is_department_manager(
        actor,
        workflow,
    ):
        raise PermissionDenied(
            "Only the assigned Department "
            "Manager can review this document."
        )

    if (
        workflow.status
        != DocumentWorkflow
        .Status
        .SUBMITTED_FOR_DEPARTMENT_REVIEW
    ):
        raise ValidationError(
            "The document is not awaiting "
            "department review."
        )

    if not comment.strip():
        raise ValidationError(
            "A review comment is required."
        )

    if decision == "APPROVE":
        new_status = (
            DocumentWorkflow
            .Status
            .READY_FOR_CUSTOMER_SUBMISSION
        )

        action = (
            DocumentWorkflowTransaction
            .Action
            .INTERNALLY_APPROVED
        )

        recipient = getattr(
            _sales_order(workflow),
            "document_controller",
            None,
        )

        title = (
            "Document ready for customer submission"
        )

    elif decision == "RETURN":
        new_status = (
            DocumentWorkflow
            .Status
            .RETURNED_FOR_REWORK
        )

        action = (
            DocumentWorkflowTransaction
            .Action
            .RETURNED_FOR_REWORK
        )

        recipient = workflow.contributor

        title = (
            "Document returned for rework"
        )

    else:
        raise ValidationError(
            "Invalid department review decision."
        )

    _transition(
        workflow=workflow,
        new_status=new_status,
        actor=actor,
        action=action,
        comment=comment,
    )

    _notify(
        user=recipient,
        title=title,
        message=(
            f"{workflow.document}: {comment}"
        ),
        workflow=workflow,
        category=(
            InAppNotification
            .Category
            .WORKFLOW
        ),
        priority=(
            InAppNotification
            .Priority
            .HIGH
        ),
        dedupe_key=(
            f"department-decision:"
            f"{workflow.pk}:"
            f"{new_status}:"
            f"{workflow.updated_at.isoformat()}"
        ),
    )

    return workflow