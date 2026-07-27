from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from .models import (
    CRSComment,
    InAppNotification,
    NotificationLog,
    SalesOrderVDRLDocument,
)


CUSTOMER_STATUSES = {
    SalesOrderVDRLDocument
    .DocumentStatus
    .SUBMITTED,

    SalesOrderVDRLDocument
    .DocumentStatus
    .UNDER_CUSTOMER_REVIEW,

    SalesOrderVDRLDocument
    .DocumentStatus
    .RESUBMITTED,
}


COMPLETED_STATUSES = {
    SalesOrderVDRLDocument
    .DocumentStatus
    .APPROVED,

    SalesOrderVDRLDocument
    .DocumentStatus
    .NOT_APPLICABLE,

    SalesOrderVDRLDocument
    .DocumentStatus
    .CANCELLED,
}


def user_display_name(user):
    if not user:
        return ""

    return (
        user.get_full_name().strip()
        or user.username
    )


def get_user_email(user):
    """
    Return a normalized email address or an empty string.
    """

    if not user:
        return ""

    return (
        user.email
        or ""
    ).strip().lower()


def add_alert_to_user(
    recipients,
    user,
    alert,
):
    """
    Add an alert to one user's daily digest.

    Duplicate alerts are prevented within the same digest.
    """

    email = get_user_email(
        user
    )

    if not email:
        return False

    bucket = recipients[email]

    if not bucket["user"]:
        bucket["user"] = user

    alert_key = alert["key"]

    if (
        alert_key
        in bucket["alert_keys"]
    ):
        return False

    bucket[
        "alert_keys"
    ].add(
        alert_key
    )

    bucket[
        "alerts"
    ].append(
        alert
    )

    return True


def escalation_level(
    overdue_days,
):
    """
    Convert overdue days into an escalation level.
    """

    if (
        overdue_days
        >= settings
        .VDRL_ESCALATION_LEVEL_3_DAYS
    ):
        return "LEVEL_3"

    if (
        overdue_days
        >= settings
        .VDRL_ESCALATION_LEVEL_2_DAYS
    ):
        return "LEVEL_2"

    if overdue_days > 0:
        return "OVERDUE"

    return "DUE_SOON"


def escalation_label(
    level,
):
    labels = {
        "DUE_SOON": "Due Soon",
        "OVERDUE": "Overdue",
        "LEVEL_2": "Level 2 Escalation",
        "LEVEL_3": "Level 3 Escalation",
    }

    return labels.get(
        level,
        level,
    )


def get_document_url(
    document,
):
    return (
        f"{settings.VDRL_BASE_URL}"
        f"/documents/{document.pk}/"
    )


def get_crs_comment_url(
    comment,
):
    return (
        f"{settings.VDRL_BASE_URL}"
        f"/crs-comments/{comment.pk}/edit/"
    )


def get_internal_due_date(
    document,
):
    """
    Before first submission:
        use Planned Submission Date.

    After customer return:
        use Forecast Submission Date.

    Therefore, when a returned document is being revised,
    the project team should enter a Forecast Submission Date.
    """

    if (
        document.first_submission_at
        is None
    ):
        return (
            document
            .planned_submission_date
        )

    return (
        document
        .forecast_submission_date
    )


def get_document_department_manager(
    document,
):
    department = (
        document
        .responsible_department
    )

    if not department:
        return None

    return department.manager


def add_internal_document_recipients(
    recipients,
    document,
    alert,
    overdue_days,
):
    """
    Internal document escalation:

    Due soon / 1-2 days overdue:
        Responsible person

    3+ days overdue:
        + Department Manager
        + Project Manager

    7+ days overdue:
        + Document Controller
    """

    primary_added = add_alert_to_user(
        recipients,
        document.responsible_person,
        alert,
    )


    if not primary_added:
        primary_added = add_alert_to_user(
            recipients,
            get_document_department_manager(
                document
            ),
            alert,
        )


    sales_order = (
        document
        .vdrl
        .sales_order
    )


    if not primary_added:
        add_alert_to_user(
            recipients,
            sales_order.document_controller,
            alert,
        )


    if (
        overdue_days
        >= settings
        .VDRL_ESCALATION_LEVEL_2_DAYS
    ):
        add_alert_to_user(
            recipients,
            get_document_department_manager(
                document
            ),
            alert,
        )

        add_alert_to_user(
            recipients,
            sales_order.project_manager,
            alert,
        )


    if (
        overdue_days
        >= settings
        .VDRL_ESCALATION_LEVEL_3_DAYS
    ):
        add_alert_to_user(
            recipients,
            sales_order.document_controller,
            alert,
        )


def add_customer_review_recipients(
    recipients,
    document,
    alert,
):
    """
    Customer review reminders remain internal.

    We do not email the customer automatically.
    """

    sales_order = (
        document
        .vdrl
        .sales_order
    )

    add_alert_to_user(
        recipients,
        sales_order.project_manager,
        alert,
    )

    add_alert_to_user(
        recipients,
        sales_order.document_controller,
        alert,
    )


def add_crs_recipients(
    recipients,
    comment,
    alert,
    overdue_days,
):
    """
    CRS escalation:

    Due soon / 1-2 days overdue:
        Assigned person

    3+ days overdue:
        + Department Manager

    7+ days overdue:
        + Project Manager
        + Document Controller
    """

    assigned_added = add_alert_to_user(
        recipients,
        comment.assigned_person,
        alert,
    )


    department_manager = None

    if comment.assigned_department:
        department_manager = (
            comment
            .assigned_department
            .manager
        )


    if not assigned_added:
        add_alert_to_user(
            recipients,
            department_manager,
            alert,
        )


    document = (
        comment
        .crs
        .document
    )

    sales_order = (
        document
        .vdrl
        .sales_order
    )


    if (
        overdue_days
        >= settings
        .VDRL_ESCALATION_LEVEL_2_DAYS
    ):
        add_alert_to_user(
            recipients,
            department_manager,
            alert,
        )


    if (
        overdue_days
        >= settings
        .VDRL_ESCALATION_LEVEL_3_DAYS
    ):
        add_alert_to_user(
            recipients,
            sales_order.project_manager,
            alert,
        )

        add_alert_to_user(
            recipients,
            sales_order.document_controller,
            alert,
        )


def build_daily_alerts(
    run_date=None,
):
    """
    Build one collection of reminder items per email recipient.
    """

    today = (
        run_date
        or timezone.localdate()
    )

    due_soon_limit = (
        today
        + timedelta(
            days=(
                settings
                .VDRL_REMINDER_DUE_SOON_DAYS
            )
        )
    )


    recipients = defaultdict(
        lambda: {
            "user": None,
            "alerts": [],
            "alert_keys": set(),
        }
    )


    # -----------------------------------------------------
    # INTERNAL VDRL DOCUMENT ACTIONS
    # -----------------------------------------------------

    internal_documents = (
        SalesOrderVDRLDocument.objects
        .filter(
            is_active=True,
            vdrl__is_current=True,
            vdrl__sales_order__is_active=True,
            applicability_status=(
                SalesOrderVDRLDocument
                .ApplicabilityStatus
                .REQUIRED
            ),
        )
        .exclude(
            status__in=(
                list(
                    CUSTOMER_STATUSES
                )
                +
                list(
                    COMPLETED_STATUSES
                )
                +
                [
                    SalesOrderVDRLDocument
                    .DocumentStatus
                    .ON_HOLD
                ]
            )
        )
        .select_related(
            "vdrl",
            "vdrl__sales_order",
            "vdrl__sales_order__customer",
            "vdrl__sales_order__project_manager",
            "vdrl__sales_order__document_controller",
            "responsible_department",
            "responsible_department__manager",
            "responsible_person",
        )
    )


    for document in internal_documents:
        due_date = get_internal_due_date(
            document
        )

        if not due_date:
            continue


        days_to_due = (
            due_date
            - today
        ).days


        if (
            days_to_due
            > settings
            .VDRL_REMINDER_DUE_SOON_DAYS
        ):
            continue


        if days_to_due >= 0:
            overdue_days = 0

            level = "DUE_SOON"

            timing_text = (
                f"Due in "
                f"{days_to_due} day(s)"
            )

        else:
            overdue_days = abs(
                days_to_due
            )

            level = escalation_level(
                overdue_days
            )

            timing_text = (
                f"{overdue_days} "
                f"day(s) overdue"
            )


        alert = {
            "key": (
                f"DOCUMENT:"
                f"{document.pk}:"
                f"INTERNAL:"
                f"{today}"
            ),

            "category": (
                "Internal Document Action"
            ),

            "severity": level,

            "severity_label": (
                escalation_label(
                    level
                )
            ),

            "sales_order": (
                document
                .vdrl
                .sales_order
                .sales_order_number
            ),

            "customer": (
                document
                .vdrl
                .sales_order
                .customer
                .name
            ),

            "title": (
                document
                .document_title
            ),

            "reference": (
                document
                .customer_document_code
                or
                document
                .document
                .internal_document_code
            ),

            "status": (
                document
                .get_status_display()
            ),

            "due_date": due_date,

            "timing_text": timing_text,

            "link": (
                get_document_url(
                    document
                )
            ),
        }


        add_internal_document_recipients(
            recipients,
            document,
            alert,
            overdue_days,
        )


    # -----------------------------------------------------
    # CUSTOMER REVIEW ACTIONS
    # -----------------------------------------------------

    customer_documents = (
        SalesOrderVDRLDocument.objects
        .filter(
            is_active=True,
            vdrl__is_current=True,
            vdrl__sales_order__is_active=True,
            status__in=CUSTOMER_STATUSES,
            customer_review_due_date__isnull=False,
        )
        .select_related(
            "vdrl",
            "vdrl__sales_order",
            "vdrl__sales_order__customer",
            "vdrl__sales_order__project_manager",
            "vdrl__sales_order__document_controller",
            "document",
        )
    )


    for document in customer_documents:
        due_date = (
            document
            .customer_review_due_date
        )

        days_to_due = (
            due_date
            - today
        ).days


        if (
            days_to_due
            > settings
            .VDRL_REMINDER_DUE_SOON_DAYS
        ):
            continue


        if days_to_due >= 0:
            overdue_days = 0

            level = "DUE_SOON"

            timing_text = (
                f"Customer review due in "
                f"{days_to_due} day(s)"
            )

        else:
            overdue_days = abs(
                days_to_due
            )

            level = escalation_level(
                overdue_days
            )

            timing_text = (
                f"Customer review "
                f"{overdue_days} "
                f"day(s) overdue"
            )


        alert = {
            "key": (
                f"DOCUMENT:"
                f"{document.pk}:"
                f"CUSTOMER:"
                f"{today}"
            ),

            "category": (
                "Customer Review Follow-up"
            ),

            "severity": level,

            "severity_label": (
                escalation_label(
                    level
                )
            ),

            "sales_order": (
                document
                .vdrl
                .sales_order
                .sales_order_number
            ),

            "customer": (
                document
                .vdrl
                .sales_order
                .customer
                .name
            ),

            "title": (
                document
                .document_title
            ),

            "reference": (
                document
                .customer_document_code
                or
                document
                .document
                .internal_document_code
            ),

            "status": (
                document
                .get_status_display()
            ),

            "due_date": due_date,

            "timing_text": timing_text,

            "link": (
                get_document_url(
                    document
                )
            ),
        }


        add_customer_review_recipients(
            recipients,
            document,
            alert,
        )


    # -----------------------------------------------------
    # CRS COMMENT ACTIONS
    # -----------------------------------------------------

    open_crs_comments = (
        CRSComment.objects
        .exclude(
            status=(
                CRSComment
                .Status
                .CLOSED
            )
        )
        .filter(
            target_response_date__isnull=False,
            crs__document__is_active=True,
            crs__document__vdrl__is_current=True,
            crs__document__vdrl__sales_order__is_active=True,
        )
        .select_related(
            "crs",
            "crs__document",
            "crs__document__vdrl",
            "crs__document__vdrl__sales_order",
            "crs__document__vdrl__sales_order__customer",
            "crs__document__vdrl__sales_order__project_manager",
            "crs__document__vdrl__sales_order__document_controller",
            "assigned_department",
            "assigned_department__manager",
            "assigned_person",
        )
    )


    for comment in open_crs_comments:
        due_date = (
            comment
            .target_response_date
        )

        days_to_due = (
            due_date
            - today
        ).days


        if (
            days_to_due
            > settings
            .VDRL_REMINDER_DUE_SOON_DAYS
        ):
            continue


        if days_to_due >= 0:
            overdue_days = 0

            level = "DUE_SOON"

            timing_text = (
                f"Response due in "
                f"{days_to_due} day(s)"
            )

        else:
            overdue_days = abs(
                days_to_due
            )

            level = escalation_level(
                overdue_days
            )

            timing_text = (
                f"{overdue_days} "
                f"day(s) overdue"
            )


        document = (
            comment
            .crs
            .document
        )


        alert = {
            "key": (
                f"CRS_COMMENT:"
                f"{comment.pk}:"
                f"{today}"
            ),

            "category": (
                "CRS Comment"
            ),

            "severity": level,

            "severity_label": (
                escalation_label(
                    level
                )
            ),

            "sales_order": (
                document
                .vdrl
                .sales_order
                .sales_order_number
            ),

            "customer": (
                document
                .vdrl
                .sales_order
                .customer
                .name
            ),

            "title": (
                f"{document.document_title} "
                f"— Comment "
                f"{comment.comment_number}"
            ),

            "reference": (
                comment
                .crs
                .crs_reference
                or
                f"Cycle "
                f"{comment.crs.cycle_number}"
            ),

            "status": (
                comment
                .get_status_display()
            ),

            "due_date": due_date,

            "timing_text": timing_text,

            "link": (
                get_crs_comment_url(
                    comment
                )
            ),
        }


        add_crs_recipients(
            recipients,
            comment,
            alert,
            overdue_days,
        )


    # -----------------------------------------------------
    # SORT ALERTS BY PRIORITY
    # -----------------------------------------------------

    priority = {
        "LEVEL_3": 1,
        "LEVEL_2": 2,
        "OVERDUE": 3,
        "DUE_SOON": 4,
    }


    for bucket in recipients.values():
        bucket["alerts"].sort(
            key=lambda item: (
                priority.get(
                    item["severity"],
                    99,
                ),
                item["due_date"],
                item["sales_order"],
            )
        )


    return recipients


def send_daily_vdrl_reminders(
    run_date=None,
    dry_run=False,
    force=False,
):
    """
    Build and send one daily digest per recipient.

    Duplicate emails for the same recipient and date are
    prevented unless force=True.
    """

    today = (
        run_date
        or timezone.localdate()
    )


    recipient_data = (
        build_daily_alerts(
            run_date=today
        )
    )


    result = {
        "recipient_count": (
            len(
                recipient_data
            )
        ),

        "sent": 0,

        "skipped": 0,

        "failed": 0,

        "previews": [],
    }


    for (
        recipient_email,
        bucket,
    ) in recipient_data.items():

        user = bucket["user"]

        alerts = bucket["alerts"]


        existing_log = (
            NotificationLog.objects
            .filter(
                recipient_email=(
                    recipient_email
                ),
                notification_date=(
                    today
                ),
                digest_key=(
                    NotificationLog
                    .DAILY_DIGEST
                ),
                delivery_status=(
                    NotificationLog
                    .DeliveryStatus
                    .SENT
                ),
            )
            .first()
        )


        if (
            existing_log
            and not force
        ):
            result["skipped"] += 1

            continue


        recipient_name = (
            user_display_name(
                user
            )
            or recipient_email
        )


        context = {
            "recipient_name": (
                recipient_name
            ),

            "notification_date": (
                today
            ),

            "alerts": alerts,

            "item_count": (
                len(
                    alerts
                )
            ),

            "dashboard_url": (
                settings
                .VDRL_BASE_URL
            ),
        }


        subject = (
            "[VDRL] Daily Action Digest - "
            f"{today:%d-%b-%Y} - "
            f"{len(alerts)} Action(s)"
        )


        text_body = render_to_string(
            (
                "core/emails/"
                "vdrl_daily_digest.txt"
            ),
            context,
        )


        html_body = render_to_string(
            (
                "core/emails/"
                "vdrl_daily_digest.html"
            ),
            context,
        )


        if dry_run:
            result[
                "previews"
            ].append(
                {
                    "recipient_email": (
                        recipient_email
                    ),

                    "recipient_name": (
                        recipient_name
                    ),

                    "subject": subject,

                    "item_count": (
                        len(
                            alerts
                        )
                    ),

                    "alerts": alerts,
                }
            )

            continue


        try:
            email_message = (
                EmailMultiAlternatives(
                    subject=subject,
                    body=text_body,
                    from_email=(
                        settings
                        .DEFAULT_FROM_EMAIL
                    ),
                    to=[
                        recipient_email
                    ],
                )
            )


            email_message.attach_alternative(
                html_body,
                "text/html",
            )


            sent_count = (
                email_message
                .send(
                    fail_silently=False
                )
            )


            if sent_count != 1:
                raise RuntimeError(
                    (
                        "Email backend reported "
                        f"{sent_count} sent messages."
                    )
                )


            NotificationLog.objects.update_or_create(
                recipient_email=(
                    recipient_email
                ),

                notification_date=(
                    today
                ),

                digest_key=(
                    NotificationLog
                    .DAILY_DIGEST
                ),

                defaults={
                    "recipient_user": user,

                    "subject": subject,

                    "item_count": (
                        len(
                            alerts
                        )
                    ),

                    "delivery_status": (
                        NotificationLog
                        .DeliveryStatus
                        .SENT
                    ),

                    "sent_at": (
                        timezone.now()
                    ),

                    "error_message": "",
                },
            )


            result["sent"] += 1


        except Exception as exc:
            NotificationLog.objects.update_or_create(
                recipient_email=(
                    recipient_email
                ),

                notification_date=(
                    today
                ),

                digest_key=(
                    NotificationLog
                    .DAILY_DIGEST
                ),

                defaults={
                    "recipient_user": user,

                    "subject": subject,

                    "item_count": (
                        len(
                            alerts
                        )
                    ),

                    "delivery_status": (
                        NotificationLog
                        .DeliveryStatus
                        .FAILED
                    ),

                    "sent_at": None,

                    "error_message": (
                        str(
                            exc
                        )
                    ),
                },
            )


            result["failed"] += 1


    return result

def create_in_app_notification(
    *,
    recipient,
    title,
    message="",
    category=None,
    priority=None,
    url="",
    dedupe_key="",
    related_document=None,
    related_crs_comment=None,
    created_by=None,
):
    """
    Create or refresh one in-app notification.
    """

    if (
        not recipient
        or not recipient.is_active
    ):
        return None

    if category is None:
        category = (
            InAppNotification
            .Category
            .SYSTEM
        )

    if priority is None:
        priority = (
            InAppNotification
            .Priority
            .NORMAL
        )

    defaults = {
        "title": title[:250],

        "message": message,

        "category": category,

        "priority": priority,

        "url": url[:500],

        "related_document": (
            related_document
        ),

        "related_crs_comment": (
            related_crs_comment
        ),

        "created_by": created_by,

        "is_read": False,

        "read_at": None,

        "created_at": timezone.now(),
    }

    if dedupe_key:
        notification, _ = (
            InAppNotification
            .objects
            .update_or_create(
                recipient=recipient,
                dedupe_key=(
                    dedupe_key[:250]
                ),
                defaults=defaults,
            )
        )

        return notification

    return (
        InAppNotification
        .objects
        .create(
            recipient=recipient,
            dedupe_key="",
            **defaults,
        )
    )


def notify_users(
    users,
    *,
    title,
    message="",
    category=None,
    priority=None,
    url="",
    dedupe_key="",
    related_document=None,
    related_crs_comment=None,
    created_by=None,
):
    """
    Send the same notification to multiple users
    without duplicating recipients.
    """

    notified_user_ids = set()

    notifications = []

    for user in users:
        if (
            not user
            or user.pk in notified_user_ids
        ):
            continue

        notified_user_ids.add(
            user.pk
        )

        user_dedupe_key = (
            f"{dedupe_key}:user:{user.pk}"
            if dedupe_key
            else ""
        )

        notification = (
            create_in_app_notification(
                recipient=user,
                title=title,
                message=message,
                category=category,
                priority=priority,
                url=url,
                dedupe_key=(
                    user_dedupe_key
                ),
                related_document=(
                    related_document
                ),
                related_crs_comment=(
                    related_crs_comment
                ),
                created_by=created_by,
            )
        )

        if notification:
            notifications.append(
                notification
            )

    return notifications


def sync_in_app_notifications(
    run_date=None,
):
    """
    Convert the Stage 10 reminder calculation into
    in-app due and overdue notifications.
    """

    recipient_data = (
        build_daily_alerts(
            run_date=run_date
        )
    )

    created_or_updated = 0

    priority_map = {
        "DUE_SOON": (
            InAppNotification
            .Priority
            .NORMAL
        ),

        "OVERDUE": (
            InAppNotification
            .Priority
            .HIGH
        ),

        "LEVEL_2": (
            InAppNotification
            .Priority
            .HIGH
        ),

        "LEVEL_3": (
            InAppNotification
            .Priority
            .URGENT
        ),
    }

    for bucket in (
        recipient_data.values()
    ):
        recipient = bucket[
            "user"
        ]

        if not recipient:
            continue

        for alert in (
            bucket["alerts"]
        ):
            alert_key = (
                alert[
                    "key"
                ]
            )

            # Stage 10 adds today's date to its key.
            # Remove it so the same active action updates
            # instead of generating one new notification
            # every day.

            key_parts = (
                alert_key.split(":")
            )

            if len(
                key_parts
            ) > 1:
                persistent_key = ":".join(
                    key_parts[:-1]
                )

            else:
                persistent_key = (
                    alert_key
                )

            create_in_app_notification(
                recipient=recipient,

                title=(
                    f"{alert['severity_label']}: "
                    f"{alert['title']}"
                ),

                message=(
                    f"{alert['category']} | "
                    f"Sales Order "
                    f"{alert['sales_order']} | "
                    f"{alert['timing_text']}"
                ),

                category=(
                    InAppNotification
                    .Category
                    .DUE_DATE
                ),

                priority=(
                    priority_map.get(
                        alert[
                            "severity"
                        ],
                        (
                            InAppNotification
                            .Priority
                            .NORMAL
                        ),
                    )
                ),

                url=alert[
                    "link"
                ],

                dedupe_key=(
                    f"due-alert:"
                    f"{persistent_key}"
                ),
            )

            created_or_updated += 1

    return {
        "recipients": len(
            recipient_data
        ),

        "notifications": (
            created_or_updated
        ),
    }