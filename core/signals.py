from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
)

from django.db.models.signals import (
    post_save,
    pre_delete,
    pre_save,
)

from django.dispatch import receiver

from django.urls import reverse

from .audit import (
    compare_snapshots,
    record_audit_event,
    snapshot_instance,
)

from .models import (
    AuditLog,
    CRSComment,
    CRSRegister,
    Customer,
    CustomerVDRLTemplate,
    CustomerVDRLTemplateItem,
    Department,
    DocumentCategory,
    DocumentFile,
    DocumentMaster,
    DocumentTransaction,
    EmployeeProfile,
    InAppNotification,
    NotificationLog,
    Project,
    SalesOrder,
    SalesOrderVDRL,
    SalesOrderVDRLDocument,
    DocumentAssignmentHistory,
    DocumentOpenPoint,
    DocumentOpenPointTransaction,
    DocumentWorkflow,
    DocumentWorkflowTransaction,
    ProjectTeam,
    SalesOrder,
)

from .notifications import (
    create_in_app_notification,
    notify_users,
)


TRACKED_MODELS = (
    Department,
    EmployeeProfile,
    Customer,
    Project,
    SalesOrder,
    DocumentCategory,
    DocumentMaster,
    CustomerVDRLTemplate,
    CustomerVDRLTemplateItem,
    SalesOrderVDRL,
    SalesOrderVDRLDocument,
    DocumentTransaction,
    DocumentFile,
    CRSRegister,
    CRSComment,
    DocumentAssignmentHistory,
    DocumentOpenPoint,
    DocumentOpenPointTransaction,
    DocumentWorkflow,
    DocumentWorkflowTransaction,
)


def is_tracked_instance(
    instance,
):
    return isinstance(
        instance,
        TRACKED_MODELS,
    )


def instance_actor(
    instance,
):
    for field_name in [
        "updated_by",
        "created_by",
        "uploaded_by",
        "performed_by",
        "prepared_by",
    ]:
        actor = getattr(
            instance,
            field_name,
            None,
        )

        if actor:
            return actor

    return None


@receiver(
    pre_save,
    dispatch_uid=(
        "vdrl_capture_previous_model_state"
    ),
)
def capture_previous_model_state(
    sender,
    instance,
    raw=False,
    **kwargs,
):
    if raw:
        return

    if not is_tracked_instance(
        instance
    ):
        return

    if not instance.pk:
        instance._vdrl_previous_snapshot = (
            None
        )

        return

    previous_instance = (
        sender.objects
        .filter(
            pk=instance.pk
        )
        .first()
    )

    if previous_instance is None:
        instance._vdrl_previous_snapshot = (
            None
        )

        return

    instance._vdrl_previous_snapshot = (
        snapshot_instance(
            previous_instance
        )
    )


@receiver(
    post_save,
    dispatch_uid=(
        "vdrl_record_model_save"
    ),
)
def record_model_save(
    sender,
    instance,
    created,
    raw=False,
    **kwargs,
):
    if raw:
        return

    if not is_tracked_instance(
        instance
    ):
        return

    new_snapshot = snapshot_instance(
        instance
    )

    old_snapshot = getattr(
        instance,
        "_vdrl_previous_snapshot",
        None,
    )

    if created:
        changes = {
            field_name: {
                "old": None,
                "new": field_value,
            }

            for (
                field_name,
                field_value,
            ) in new_snapshot.items()

            if field_value not in [
                None,
                "",
                False,
            ]
        }

        record_audit_event(
            action=(
                AuditLog
                .Action
                .CREATE
            ),

            instance=instance,

            actor=instance_actor(
                instance
            ),

            description=(
                f"Created "
                f"{instance._meta.verbose_name}."
            ),

            changes=changes,
        )

    else:
        changes = compare_snapshots(
            old_snapshot,
            new_snapshot,
        )

        if not changes:
            return

        record_audit_event(
            action=(
                AuditLog
                .Action
                .UPDATE
            ),

            instance=instance,

            actor=instance_actor(
                instance
            ),

            description=(
                f"Updated "
                f"{instance._meta.verbose_name}."
            ),

            changes=changes,
        )

    create_business_notifications(
        instance=instance,
        created=created,
        changes=(
            changes
            if not created
            else {}
        ),
        actor=instance_actor(
            instance
        ),
    )


@receiver(
    pre_delete,
    dispatch_uid=(
        "vdrl_record_model_delete"
    ),
)
def record_model_delete(
    sender,
    instance,
    **kwargs,
):
    if not is_tracked_instance(
        instance
    ):
        return

    record_audit_event(
        action=(
            AuditLog
            .Action
            .DELETE
        ),

        instance=instance,

        actor=instance_actor(
            instance
        ),

        description=(
            f"Deleted "
            f"{instance._meta.verbose_name}."
        ),

        changes={
            "deleted_record": (
                snapshot_instance(
                    instance
                )
            )
        },
    )


@receiver(
    user_logged_in,
    dispatch_uid=(
        "vdrl_record_user_login"
    ),
)
def record_user_login(
    sender,
    request,
    user,
    **kwargs,
):
    record_audit_event(
        action=(
            AuditLog
            .Action
            .LOGIN
        ),

        actor=user,

        request=request,

        model_label="auth.User",

        object_id=str(
            user.pk
        ),

        object_repr=(
            user.get_full_name().strip()
            or user.username
        ),

        description=(
            "User logged into the "
            "VDRL application."
        ),
    )


@receiver(
    user_logged_out,
    dispatch_uid=(
        "vdrl_record_user_logout"
    ),
)
def record_user_logout(
    sender,
    request,
    user,
    **kwargs,
):
    record_audit_event(
        action=(
            AuditLog
            .Action
            .LOGOUT
        ),

        actor=user,

        request=request,

        model_label="auth.User",

        object_id=(
            str(
                user.pk
            )
            if user
            else ""
        ),

        object_repr=(
            (
                user.get_full_name().strip()
                or user.username
            )
            if user
            else "Unknown User"
        ),

        description=(
            "User logged out of the "
            "VDRL application."
        ),
    )


def create_business_notifications(
    *,
    instance,
    created,
    changes,
    actor,
):
    """
    Create immediate in-app notifications for
    assignments and important workflow events.
    """

    if isinstance(
        instance,
        SalesOrderVDRLDocument,
    ):
        create_document_notifications(
            document=instance,
            created=created,
            changes=changes,
            actor=actor,
        )

    elif isinstance(
        instance,
        CRSComment,
    ):
        create_crs_comment_notifications(
            comment=instance,
            created=created,
            changes=changes,
            actor=actor,
        )


def create_document_notifications(
    *,
    document,
    created,
    changes,
    actor,
):
    sales_order = (
        document
        .vdrl
        .sales_order
    )

    document_url = reverse(
        "core:document_detail",
        args=[
            document.pk
        ],
    )

    assignment_changed = (
        created
        and document.responsible_person_id
    ) or (
        "responsible_person"
        in changes
    )

    if (
        assignment_changed
        and document.responsible_person
    ):
        create_in_app_notification(
            recipient=(
                document
                .responsible_person
            ),

            title=(
                "VDRL document assigned to you"
            ),

            message=(
                f"{sales_order.sales_order_number} | "
                f"{document.document_title}"
            ),

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

            url=document_url,

            dedupe_key=(
                f"document-assignment:"
                f"{document.pk}:"
                f"{document.updated_at.isoformat()}"
            ),

            related_document=document,

            created_by=actor,
        )

    if (
        "status"
        not in changes
    ):
        return

    new_status = (
        changes[
            "status"
        ][
            "new"
        ]
    )

    important_statuses = {
        (
            SalesOrderVDRLDocument
            .DocumentStatus
            .RETURNED_WITH_COMMENTS
        ): {
            "title": (
                "Document returned with comments"
            ),

            "priority": (
                InAppNotification
                .Priority
                .HIGH
            ),

            "category": (
                InAppNotification
                .Category
                .WORKFLOW
            ),
        },

        (
            SalesOrderVDRLDocument
            .DocumentStatus
            .APPROVED_WITH_COMMENTS
        ): {
            "title": (
                "Document approved with comments"
            ),

            "priority": (
                InAppNotification
                .Priority
                .HIGH
            ),

            "category": (
                InAppNotification
                .Category
                .WORKFLOW
            ),
        },

        (
            SalesOrderVDRLDocument
            .DocumentStatus
            .APPROVED
        ): {
            "title": (
                "Document approved"
            ),

            "priority": (
                InAppNotification
                .Priority
                .NORMAL
            ),

            "category": (
                InAppNotification
                .Category
                .APPROVAL
            ),
        },

        (
            SalesOrderVDRLDocument
            .DocumentStatus
            .ON_HOLD
        ): {
            "title": (
                "Document placed on hold"
            ),

            "priority": (
                InAppNotification
                .Priority
                .HIGH
            ),

            "category": (
                InAppNotification
                .Category
                .WORKFLOW
            ),
        },
    }

    notification_data = (
        important_statuses.get(
            new_status
        )
    )

    if not notification_data:
        return

    notify_users(
        [
            document.responsible_person,
            sales_order.project_manager,
            sales_order.document_controller,
        ],

        title=(
            notification_data[
                "title"
            ]
        ),

        message=(
            f"{sales_order.sales_order_number} | "
            f"{document.document_title} | "
            f"{document.get_status_display()}"
        ),

        category=(
            notification_data[
                "category"
            ]
        ),

        priority=(
            notification_data[
                "priority"
            ]
        ),

        url=document_url,

        dedupe_key=(
            f"document-status:"
            f"{document.pk}:"
            f"{new_status}:"
            f"{document.updated_at.isoformat()}"
        ),

        related_document=document,

        created_by=actor,
    )


def create_crs_comment_notifications(
    *,
    comment,
    created,
    changes,
    actor,
):
    assignment_changed = (
        created
        and comment.assigned_person_id
    ) or (
        "assigned_person"
        in changes
    )

    if (
        not assignment_changed
        or not comment.assigned_person
    ):
        return

    comment_url = reverse(
        "core:crs_comment_edit",
        args=[
            comment.pk
        ],
    )

    document = (
        comment
        .crs
        .document
    )

    create_in_app_notification(
        recipient=(
            comment
            .assigned_person
        ),

        title=(
            "CRS comment assigned to you"
        ),

        message=(
            f"{document.vdrl.sales_order.sales_order_number} | "
            f"{document.document_title} | "
            f"Comment {comment.comment_number}"
        ),

        category=(
            InAppNotification
            .Category
            .CRS
        ),

        priority=(
            InAppNotification
            .Priority
            .NORMAL
        ),

        url=comment_url,

        dedupe_key=(
            f"crs-assignment:"
            f"{comment.pk}:"
            f"{comment.updated_at.isoformat()}"
        ),

        related_document=document,

        related_crs_comment=comment,

        created_by=actor,
    )

@receiver(
    post_save,
    sender=SalesOrderVDRLDocument,
    dispatch_uid="create_document_workflow",
)
def create_document_workflow(
    sender,
    instance,
    created,
    **kwargs,
):
    DocumentWorkflow.objects.get_or_create(
        document=instance,
    )

@receiver(
    post_save,
    sender=ProjectTeam,
    dispatch_uid=(
        "sync_project_team_manager_to_sales_orders"
    ),
)
def sync_project_team_manager_to_sales_orders(
    sender,
    instance,
    **kwargs,
):
    SalesOrder.objects.filter(
        project_team=instance,
    ).exclude(
        project_manager=(
            instance.project_manager
        ),
    ).update(
        project_manager=(
            instance.project_manager
        ),
    )