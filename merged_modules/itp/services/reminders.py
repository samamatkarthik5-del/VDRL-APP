from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from itp.models import (
    AlertSeverity,
    AlertType,
    CompletionStatus,
    CompletionTaskStatus,
    NOICompletionTask,
    NOIStatus,
    NoticeOfInspection,
    WorkflowAlert,
)


def _send(user, subject: str, message: str) -> None:
    if not user or not user.email:
        return
    send_mail(
        subject,
        message,
        getattr(settings, "DEFAULT_FROM_EMAIL", None),
        [user.email],
        fail_silently=True,
    )


def _escalation_users():
    group_names = getattr(settings, "ITP_ESCALATION_GROUPS", ["QC Manager", "Project Manager"])
    return get_user_model().objects.filter(groups__name__in=group_names, is_active=True).distinct()


@transaction.atomic
def process_noi_followups(now=None) -> dict[str, int]:
    now = now or timezone.now()
    prompted = 0
    overdue = 0
    escalated = 0

    nois = NoticeOfInspection.objects.filter(
        completion_status=CompletionStatus.PENDING,
        completion_confirmation_due_at__lte=now,
    ).exclude(status__in=[NOIStatus.CANCELLED, NOIStatus.CLOSED])

    for noi in nois.select_related("responsible_user"):
        task, _ = NOICompletionTask.objects.get_or_create(
            noi=noi,
            defaults={
                "assigned_to": noi.responsible_user,
                "due_at": noi.completion_confirmation_due_at,
            },
        )
        if task.status == CompletionTaskStatus.COMPLETED:
            continue

        if not noi.completion_prompt_sent_at:
            title = f"Activity completion confirmation required - {noi.number}"
            message = (
                f"NOI {noi.number} was scheduled until "
                f"{timezone.localtime(noi.scheduled_end):%d-%b-%Y %H:%M}. "
                "Confirm whether the scheduled activity was completed."
            )
            WorkflowAlert.objects.get_or_create(
                noi=noi,
                alert_type=AlertType.COMPLETION_DUE,
                assigned_to=noi.responsible_user,
                is_resolved=False,
                defaults={
                    "severity": AlertSeverity.WARNING,
                    "title": title,
                    "message": message,
                },
            )
            _send(noi.responsible_user, title, message)
            noi.completion_prompt_sent_at = now
            noi.save(update_fields=["completion_prompt_sent_at", "updated_at"])
            task.last_sent_at = now
            task.reminder_count += 1
            task.save(update_fields=["last_sent_at", "reminder_count"])
            prompted += 1
            continue

        if now >= task.due_at + timedelta(days=1):
            task.status = CompletionTaskStatus.OVERDUE
            task.last_sent_at = now
            task.reminder_count += 1
            task.save(update_fields=["status", "last_sent_at", "reminder_count"])
            title = f"Overdue completion confirmation - {noi.number}"
            message = (
                f"Completion confirmation for NOI {noi.number} is overdue. "
                "Until confirmation is recorded, any related Hold Point remains incomplete and dependent operations may be blocked."
            )
            WorkflowAlert.objects.get_or_create(
                noi=noi,
                alert_type=AlertType.COMPLETION_OVERDUE,
                assigned_to=noi.responsible_user,
                is_resolved=False,
                defaults={
                    "severity": AlertSeverity.CRITICAL,
                    "title": title,
                    "message": message,
                },
            )
            _send(noi.responsible_user, title, message)
            overdue += 1

        if now >= task.due_at + timedelta(days=2) and not task.escalated_at:
            for user in _escalation_users():
                title = f"Escalation: NOI completion not confirmed - {noi.number}"
                message = (
                    f"The responsible user has not confirmed completion of NOI {noi.number}. "
                    "Please review the affected ITP activities and Hold Points."
                )
                WorkflowAlert.objects.create(
                    noi=noi,
                    alert_type=AlertType.COMPLETION_OVERDUE,
                    severity=AlertSeverity.CRITICAL,
                    title=title,
                    message=message,
                    assigned_to=user,
                )
                _send(user, title, message)
            task.escalated_at = now
            task.save(update_fields=["escalated_at"])
            escalated += 1

    return {"prompted": prompted, "overdue": overdue, "escalated": escalated}
