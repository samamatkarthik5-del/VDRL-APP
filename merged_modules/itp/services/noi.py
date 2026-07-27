from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Iterable

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from itp.models import (
    AlertSeverity,
    AlertType,
    CompletionStatus,
    CompletionTaskStatus,
    CoverageResult,
    DocumentStatus,
    ExecutionSource,
    ExecutionStatus,
    HoldReleaseMode,
    ITPActivityExecution,
    ITPLineClauseMapping,
    MappingReviewStatus,
    NOICoverage,
    NOICompletionTask,
    NOINumberSequence,
    NOIStatus,
    NoticeOfInspection,
    WorkflowAlert,
)

from .sequence import check_previous_activity


class HoldPointBlocked(ValueError):
    def __init__(self, blocked_items: list[dict]):
        self.blocked_items = blocked_items
        message = "; ".join(
            f"Line {item['line']} blocked by {item['previous_clause']}"
            for item in blocked_items
        )
        super().__init__(message)


@transaction.atomic
def next_noi_number() -> str:
    year = timezone.localdate().year
    sequence, _ = NOINumberSequence.objects.select_for_update().get_or_create(year=year)
    sequence.last_number += 1
    sequence.save(update_fields=["last_number"])
    prefix = getattr(settings, "ITP_NOI_PREFIX", "NOI")
    return f"{prefix}-{year}-{sequence.last_number:05d}"


def _completion_due(scheduled_end, followup_days: int = 1):
    local_end = timezone.localtime(scheduled_end)
    hour = int(getattr(settings, "ITP_COMPLETION_FOLLOWUP_HOUR", 8))
    due_date = local_end.date() + timedelta(days=followup_days)
    naive = datetime.combine(due_date, time(hour=hour))
    return timezone.make_aware(naive, timezone.get_current_timezone())


@transaction.atomic
def create_noi(*, form_data: dict, coverage_rows: list[dict], user) -> NoticeOfInspection:
    itp = form_data["itp"]
    annexure = form_data["annexure"]
    if itp.status != DocumentStatus.ACTIVE or annexure.status != DocumentStatus.ACTIVE:
        raise ValueError("Only active ITP and annexure revisions can be used.")
    if itp.sales_order_id != annexure.sales_order_id:
        raise ValueError("ITP and annexure belong to different Sales Orders.")

    checked_rows: list[dict] = []
    blocked_items: list[dict] = []
    max_followup_days = 1
    seen_combinations: set[tuple[str, str]] = set()

    for row in coverage_rows:
        clause = row["clause"]
        line = row["annexure_line"]
        combination = (str(clause.pk), str(line.pk))
        if combination in seen_combinations:
            raise ValueError(
                f"Duplicate NOI coverage row for clause {clause.clause_code} and annexure line {line.po_line_no}."
            )
        seen_combinations.add(combination)
        offered_quantity = Decimal(row["offered_quantity"])
        mapping = ITPLineClauseMapping.objects.filter(
            clause=clause,
            annexure_line=line,
            is_applicable=True,
            review_status=MappingReviewStatus.APPROVED,
        ).first()
        if not mapping:
            raise ValueError(
                f"Clause {clause.clause_code} is not approved as applicable to line {line.po_line_no}."
            )
        if offered_quantity > line.quantity:
            raise ValueError(f"Offered quantity exceeds line {line.po_line_no} quantity.")

        already_notified = NOICoverage.objects.filter(
            clause=clause,
            annexure_line=line,
            noi__status__in=[
                NOIStatus.SUBMITTED,
                NOIStatus.ACCEPTED,
                NOIStatus.WAIVED,
                NOIStatus.RESCHEDULED,
                NOIStatus.ATTENDED,
                NOIStatus.COMPLETED,
                NOIStatus.CLOSED,
            ],
            result__in=[
                CoverageResult.PENDING,
                CoverageResult.ACCEPTED,
                CoverageResult.WAIVED,
            ],
        ).aggregate(total=Coalesce(Sum("offered_quantity"), Decimal("0")))["total"]
        notifiable_limit = mapping.effective_required_quantity
        if already_notified + offered_quantity > notifiable_limit:
            remaining = max(Decimal("0"), notifiable_limit - already_notified)
            raise ValueError(
                f"Clause {clause.clause_code}, line {line.po_line_no}: only {remaining} quantity remains available for notification."
            )

        previous_states = check_previous_activity(clause, line, offered_quantity)
        for state in previous_states:
            if state["blocked"]:
                blocked_items.append(
                    {
                        "line": line.po_line_no,
                        "current_clause": clause.clause_code,
                        "previous_clause": state["clause_code"],
                        "previous_activity": state["activity"],
                        "state": state["state"],
                    }
                )
        checked_rows.append({**row, "mapping": mapping, "previous_states": previous_states})
        max_followup_days = max(max_followup_days, clause.completion_followup_days)

    if blocked_items:
        raise HoldPointBlocked(blocked_items)

    noi = NoticeOfInspection(
        number=next_noi_number(),
        itp=itp,
        annexure=annexure,
        scheduled_start=form_data["scheduled_start"],
        scheduled_end=form_data["scheduled_end"],
        location=form_data.get("location", ""),
        responsible_user=form_data["responsible_user"],
        status=NOIStatus.SUBMITTED,
        completion_confirmation_due_at=_completion_due(
            form_data["scheduled_end"], max_followup_days
        ),
        created_by=user,
    )
    noi.full_clean()
    noi.save()

    for row in checked_rows:
        coverage = NOICoverage(
            noi=noi,
            clause=row["clause"],
            annexure_line=row["annexure_line"],
            offered_quantity=row["offered_quantity"],
            heat_numbers=row.get("heat_numbers", ""),
            serial_numbers=row.get("serial_numbers", ""),
            previous_activity_state=row["previous_states"],
        )
        coverage.full_clean()
        coverage.save()

    NOICompletionTask.objects.create(
        noi=noi,
        assigned_to=noi.responsible_user,
        due_at=noi.completion_confirmation_due_at,
    )
    return noi


@transaction.atomic
def confirm_noi_completion(
    *,
    noi: NoticeOfInspection,
    overall_status: str,
    comment: str,
    coverage_updates: list[dict],
    user,
) -> NoticeOfInspection:
    now = timezone.now()
    if overall_status not in {CompletionStatus.COMPLETED, CompletionStatus.NOT_COMPLETED}:
        raise ValueError("Invalid completion status.")

    update_by_id = {str(item["coverage_id"]): item for item in coverage_updates}

    for coverage in noi.coverages.select_related("clause", "annexure_line"):
        update = update_by_id.get(str(coverage.pk), {})
        mapping = ITPLineClauseMapping.objects.get(
            clause=coverage.clause,
            annexure_line=coverage.annexure_line,
            is_applicable=True,
            review_status=MappingReviewStatus.APPROVED,
        )

        if overall_status == CompletionStatus.COMPLETED:
            completed_quantity = Decimal(
                update.get("completed_quantity") or coverage.offered_quantity
            )
            if completed_quantity <= 0 or completed_quantity > coverage.offered_quantity:
                raise ValueError(
                    f"Invalid completed quantity for line {coverage.annexure_line.po_line_no}."
                )
            coverage.completed_quantity = completed_quantity
            coverage.actual_completion_at = update.get("actual_completion_at") or now
            coverage.report_reference = update.get("report_reference", "")
            coverage_result = update.get("result") or CoverageResult.ACCEPTED
            coverage.result = coverage_result
            coverage.save(
                update_fields=[
                    "completed_quantity",
                    "actual_completion_at",
                    "report_reference",
                    "result",
                ]
            )

            released_at = None
            released_by = None
            if coverage_result == CoverageResult.REJECTED:
                execution_status = ExecutionStatus.REJECTED
                if coverage.clause.is_hold_point:
                    WorkflowAlert.objects.create(
                        alert_type=AlertType.HOLD_INCOMPLETE,
                        severity=AlertSeverity.CRITICAL,
                        title=f"Hold Point inspection rejected - {coverage.clause.clause_code}",
                        message=(
                            f"{noi.number} was completed but rejected for annexure line "
                            f"{coverage.annexure_line.po_line_no}. The Hold Point is not released and dependent operations remain blocked."
                        ),
                        assigned_to=noi.responsible_user,
                        noi=noi,
                        coverage=coverage,
                    )
            elif coverage.clause.is_hold_point:
                if coverage_result == CoverageResult.WAIVED:
                    execution_status = ExecutionStatus.WAIVED
                    released_at = now
                    released_by = user
                elif coverage.clause.hold_release_mode == HoldReleaseMode.AUTO:
                    execution_status = ExecutionStatus.RELEASED
                    released_at = now
                    released_by = user
                else:
                    execution_status = ExecutionStatus.COMPLETED
                    WorkflowAlert.objects.create(
                        alert_type=AlertType.HOLD_AWAITING_RELEASE,
                        severity=AlertSeverity.WARNING,
                        title=f"Hold Point awaiting release - {coverage.clause.clause_code}",
                        message=(
                            f"{noi.number} is completed for annexure line "
                            f"{coverage.annexure_line.po_line_no}, but the Hold Point requires manual release."
                        ),
                        assigned_to=noi.responsible_user,
                        noi=noi,
                        coverage=coverage,
                    )
            else:
                execution_status = ExecutionStatus.COMPLETED

            ITPActivityExecution.objects.create(
                mapping=mapping,
                noi_coverage=coverage,
                source=ExecutionSource.NOI,
                quantity=completed_quantity,
                status=execution_status,
                scheduled_end=noi.scheduled_end,
                completed_at=coverage.actual_completion_at,
                released_at=released_at,
                completed_by=user,
                released_by=released_by,
                release_reference=coverage.report_reference,
                remarks=comment,
            )
        else:
            coverage.completed_quantity = Decimal("0")
            coverage.result = CoverageResult.NOT_COMPLETED
            coverage.save(update_fields=["completed_quantity", "result"])

            ITPActivityExecution.objects.create(
                mapping=mapping,
                noi_coverage=coverage,
                source=ExecutionSource.NOI,
                quantity=coverage.offered_quantity,
                status=ExecutionStatus.NOT_COMPLETED,
                scheduled_end=noi.scheduled_end,
                completed_by=user,
                remarks=comment,
            )
            if coverage.clause.is_hold_point:
                WorkflowAlert.objects.create(
                    alert_type=AlertType.HOLD_INCOMPLETE,
                    severity=AlertSeverity.CRITICAL,
                    title=f"Hold Point not completed - {coverage.clause.clause_code}",
                    message=(
                        f"{noi.number} was scheduled up to {timezone.localtime(noi.scheduled_end):%d-%b-%Y %H:%M}, "
                        f"but Hold Point {coverage.clause.clause_code} is not completed for annexure line "
                        f"{coverage.annexure_line.po_line_no}. Dependent operations remain blocked."
                    ),
                    assigned_to=noi.responsible_user,
                    noi=noi,
                    coverage=coverage,
                )

    noi.completion_status = overall_status
    noi.completion_confirmed_at = now
    noi.completion_comment = comment
    noi.status = (
        NOIStatus.COMPLETED
        if overall_status == CompletionStatus.COMPLETED
        else NOIStatus.NOT_COMPLETED
    )
    noi.save(
        update_fields=[
            "completion_status",
            "completion_confirmed_at",
            "completion_comment",
            "status",
            "updated_at",
        ]
    )

    task, _ = NOICompletionTask.objects.get_or_create(
        noi=noi,
        defaults={
            "assigned_to": noi.responsible_user,
            "due_at": noi.completion_confirmation_due_at or now,
        },
    )
    task.status = CompletionTaskStatus.COMPLETED
    task.completed_at = now
    task.save(update_fields=["status", "completed_at"])

    WorkflowAlert.objects.filter(
        noi=noi,
        alert_type__in=[AlertType.COMPLETION_DUE, AlertType.COMPLETION_OVERDUE],
        is_resolved=False,
    ).update(is_resolved=True, resolved_by=user, resolved_at=now)

    return noi


@transaction.atomic
def release_hold_execution(*, execution: ITPActivityExecution, user, reference: str, remarks: str = ""):
    if not execution.mapping.clause.is_hold_point:
        raise ValueError("This activity is not a Hold Point.")
    if execution.status != ExecutionStatus.COMPLETED:
        raise ValueError("Only a completed and accepted Hold Point can be released.")

    now = timezone.now()
    execution.status = ExecutionStatus.RELEASED
    execution.released_at = now
    execution.released_by = user
    execution.release_reference = reference
    execution.remarks = f"{execution.remarks}\n{remarks}".strip()
    execution.save(
        update_fields=[
            "status",
            "released_at",
            "released_by",
            "release_reference",
            "remarks",
            "updated_at",
        ]
    )
    if execution.noi_coverage_id:
        WorkflowAlert.objects.filter(
            coverage=execution.noi_coverage,
            alert_type=AlertType.HOLD_AWAITING_RELEASE,
            is_resolved=False,
        ).update(is_resolved=True, resolved_by=user, resolved_at=now)
    return execution
