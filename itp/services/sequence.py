from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import Coalesce

from itp.models import (
    ExecutionStatus,
    ITPActivityExecution,
    ITPClause,
    ITPClauseDependency,
    ITPLineClauseMapping,
    MappingReviewStatus,
)


COMPLETION_STATUSES = [
    ExecutionStatus.COMPLETED,
    ExecutionStatus.RELEASED,
    ExecutionStatus.WAIVED,
    ExecutionStatus.OVERRIDDEN,
]
RELEASE_STATUSES = [
    ExecutionStatus.RELEASED,
    ExecutionStatus.WAIVED,
    ExecutionStatus.OVERRIDDEN,
]


def _approved_mapping(clause: ITPClause, line):
    return ITPLineClauseMapping.objects.filter(
        clause=clause,
        annexure_line=line,
        is_applicable=True,
        review_status=MappingReviewStatus.APPROVED,
    ).first()


def previous_applicable_clauses(clause: ITPClause, line) -> list[ITPClause]:
    explicit_links = ITPClauseDependency.objects.filter(
        successor=clause,
        mandatory=True,
    ).select_related("predecessor")
    explicit = [
        link.predecessor
        for link in explicit_links
        if _approved_mapping(link.predecessor, line)
    ]
    if explicit:
        return explicit

    mapping = (
        ITPLineClauseMapping.objects.filter(
            annexure_line=line,
            clause__itp=clause.itp,
            clause__sequence_order__lt=clause.sequence_order,
            clause__is_active=True,
            is_applicable=True,
            review_status=MappingReviewStatus.APPROVED,
        )
        .select_related("clause")
        .order_by("-clause__sequence_order")
        .first()
    )
    return [mapping.clause] if mapping else []


def progress_for_mapping(mapping: ITPLineClauseMapping) -> dict[str, Decimal]:
    completed = ITPActivityExecution.objects.filter(
        mapping=mapping, status__in=COMPLETION_STATUSES
    ).aggregate(total=Coalesce(Sum("quantity"), Decimal("0")))["total"]
    released = ITPActivityExecution.objects.filter(
        mapping=mapping, status__in=RELEASE_STATUSES
    ).aggregate(total=Coalesce(Sum("quantity"), Decimal("0")))["total"]
    not_completed = ITPActivityExecution.objects.filter(
        mapping=mapping, status=ExecutionStatus.NOT_COMPLETED
    ).aggregate(total=Coalesce(Sum("quantity"), Decimal("0")))["total"]
    return {
        "completed": completed or Decimal("0"),
        "released": released or Decimal("0"),
        "not_completed": not_completed or Decimal("0"),
    }


def check_previous_activity(clause: ITPClause, line, required_quantity: Decimal) -> list[dict]:
    states: list[dict] = []
    for previous in previous_applicable_clauses(clause, line):
        mapping = _approved_mapping(previous, line)
        if not mapping:
            continue
        progress = progress_for_mapping(mapping)
        if previous.is_hold_point:
            satisfied = progress["released"] >= required_quantity
            state = "RELEASED" if satisfied else (
                "COMPLETED_AWAITING_RELEASE"
                if progress["completed"] >= required_quantity
                else "NOT_COMPLETED"
            )
        else:
            satisfied = progress["completed"] >= required_quantity
            state = "COMPLETED" if satisfied else "NOT_COMPLETED"

        states.append(
            {
                "clause_id": str(previous.pk),
                "clause_code": previous.clause_code,
                "activity": previous.activity,
                "is_hold_point": previous.is_hold_point,
                "required_quantity": str(required_quantity),
                "completed_quantity": str(progress["completed"]),
                "released_quantity": str(progress["released"]),
                "state": state,
                "blocked": bool(previous.is_hold_point and not satisfied),
            }
        )
    return states
