from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)

from django.db.models import Q

from django.http import (
    HttpResponseBadRequest,
)

from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)

from django.utils import timezone

from django.views.decorators.http import (
    require_POST,
)

from django.core.paginator import (
    Paginator,
)

from .access import (
    filter_documents_for_user,
    filter_sales_orders_for_user,
    user_has_global_vdrl_access,
)

from .models import (
    AuditLog,
    InAppNotification,
)


@login_required
def notification_list(
    request,
):
    notifications = (
        request
        .user
        .in_app_notifications
        .select_related(
            "related_document",
            "related_crs_comment",
            "created_by",
        )
    )

    selected_filter = (
        request.GET.get(
            "filter",
            "all",
        )
    )

    if selected_filter == "unread":
        notifications = (
            notifications
            .filter(
                is_read=False
            )
        )

    elif selected_filter == "read":
        notifications = (
            notifications
            .filter(
                is_read=True
            )
        )

    paginator = Paginator(
        notifications,
        30,
    )

    page_obj = (
        paginator
        .get_page(
            request.GET.get(
                "page"
            )
        )
    )

    context = {
        "page_obj": page_obj,

        "selected_filter": (
            selected_filter
        ),

        "unread_count": (
            request
            .user
            .in_app_notifications
            .filter(
                is_read=False
            )
            .count()
        ),
    }

    return render(
        request,
        "core/notifications.html",
        context,
    )


@login_required
@require_POST
def notification_mark_read(
    request,
    pk,
):
    notification = (
        get_object_or_404(
            InAppNotification,
            pk=pk,
            recipient=request.user,
        )
    )

    notification.mark_as_read()

    if notification.url:
        return redirect(
            notification.url
        )

    return redirect(
        "core:notification_list"
    )


@login_required
@require_POST
def notification_mark_all_read(
    request,
):
    (
        request
        .user
        .in_app_notifications
        .filter(
            is_read=False
        )
        .update(
            is_read=True,
            read_at=timezone.now(),
        )
    )

    return redirect(
        "core:notification_list"
    )


def filter_audit_logs_for_user(
    user,
    queryset,
):
    if user_has_global_vdrl_access(
        user
    ):
        return queryset

    document_ids = (
        filter_documents_for_user(
            user
        )
        .values_list(
            "id",
            flat=True,
        )
    )

    sales_order_ids = (
        filter_sales_orders_for_user(
            user
        )
        .values_list(
            "id",
            flat=True,
        )
    )

    return (
        queryset
        .filter(
            Q(
                document_id__in=(
                    document_ids
                )
            )
            |
            Q(
                sales_order_id__in=(
                    sales_order_ids
                )
            )
            |
            Q(
                actor=user
            )
        )
        .distinct()
    )


@login_required
@permission_required(
    "core.view_audit_log",
    raise_exception=True,
)
def audit_log_list(
    request,
):
    audit_logs = (
        AuditLog
        .objects
        .select_related(
            "actor",
            "sales_order",
            "document",
            "crs",
        )
    )

    audit_logs = (
        filter_audit_logs_for_user(
            request.user,
            audit_logs,
        )
    )

    search_text = (
        request.GET.get(
            "search",
            "",
        ).strip()
    )

    action = (
        request.GET.get(
            "action",
            "",
        ).strip()
    )

    model_label = (
        request.GET.get(
            "model",
            "",
        ).strip()
    )

    actor_id = (
        request.GET.get(
            "actor",
            "",
        ).strip()
    )

    date_from = (
        request.GET.get(
            "date_from",
            "",
        ).strip()
    )

    date_to = (
        request.GET.get(
            "date_to",
            "",
        ).strip()
    )

    if search_text:
        audit_logs = (
            audit_logs
            .filter(
                Q(
                    object_repr__icontains=(
                        search_text
                    )
                )
                |
                Q(
                    description__icontains=(
                        search_text
                    )
                )
                |
                Q(
                    model_label__icontains=(
                        search_text
                    )
                )
                |
                Q(
                    sales_order__sales_order_number__icontains=(
                        search_text
                    )
                )
            )
        )

    if action:
        audit_logs = (
            audit_logs
            .filter(
                action=action
            )
        )

    if model_label:
        audit_logs = (
            audit_logs
            .filter(
                model_label=model_label
            )
        )

    if actor_id.isdigit():
        audit_logs = (
            audit_logs
            .filter(
                actor_id=actor_id
            )
        )

    if date_from:
        audit_logs = (
            audit_logs
            .filter(
                created_at__date__gte=(
                    date_from
                )
            )
        )

    if date_to:
        audit_logs = (
            audit_logs
            .filter(
                created_at__date__lte=(
                    date_to
                )
            )
        )

    actor_options = (
        AuditLog
        .objects
        .filter(
            actor__isnull=False
        )
        .values(
            "actor_id",
            "actor__first_name",
            "actor__last_name",
            "actor__username",
        )
        .distinct()
        .order_by(
            "actor__first_name",
            "actor__last_name",
            "actor__username",
        )
    )

    model_options = (
        AuditLog
        .objects
        .exclude(
            model_label=""
        )
        .values_list(
            "model_label",
            flat=True,
        )
        .distinct()
        .order_by(
            "model_label"
        )
    )

    paginator = Paginator(
        audit_logs,
        50,
    )

    page_obj = (
        paginator
        .get_page(
            request.GET.get(
                "page"
            )
        )
    )

    context = {
        "page_obj": page_obj,

        "action_choices": (
            AuditLog
            .Action
            .choices
        ),

        "actor_options": (
            actor_options
        ),

        "model_options": (
            model_options
        ),

        "filters": {
            "search": search_text,
            "action": action,
            "model": model_label,
            "actor": actor_id,
            "date_from": date_from,
            "date_to": date_to,
        },
    }

    return render(
        request,
        "core/audit_log.html",
        context,
    )


@login_required
@permission_required(
    "core.view_audit_log",
    raise_exception=True,
)
def audit_log_detail(
    request,
    pk,
):
    audit_log = (
        get_object_or_404(
            AuditLog.objects
            .select_related(
                "actor",
                "sales_order",
                "document",
                "crs",
            ),
            pk=pk,
        )
    )

    permitted_queryset = (
        filter_audit_logs_for_user(
            request.user,
            AuditLog.objects.filter(
                pk=audit_log.pk
            ),
        )
    )

    if not permitted_queryset.exists():
        return HttpResponseBadRequest(
            "You cannot access this audit record."
        )

    return render(
        request,
        "core/audit_log_detail.html",
        {
            "audit_log": audit_log,
        },
    )