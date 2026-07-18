from collections import Counter
from datetime import date
from decimal import Decimal

from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)
from django.db.models import (
    Avg,
    Count,
    Q,
    Sum,
)
from django.shortcuts import render
from django.utils import timezone

from .access import (
    filter_documents_for_user,
    filter_sales_orders_for_user,
)

from .models import (
    CRSComment,
    Customer,
    Department,
    DocumentTransaction,
    SalesOrder,
    SalesOrderVDRLDocument,
)


CUSTOMER_STATUSES = [
    SalesOrderVDRLDocument
    .DocumentStatus
    .SUBMITTED,

    SalesOrderVDRLDocument
    .DocumentStatus
    .UNDER_CUSTOMER_REVIEW,

    SalesOrderVDRLDocument
    .DocumentStatus
    .RESUBMITTED,
]


COMPLETED_STATUSES = [
    SalesOrderVDRLDocument
    .DocumentStatus
    .APPROVED,

    SalesOrderVDRLDocument
    .DocumentStatus
    .NOT_APPLICABLE,

    SalesOrderVDRLDocument
    .DocumentStatus
    .CANCELLED,
]


INTERNAL_EXCLUDED_STATUSES = (
    CUSTOMER_STATUSES
    + COMPLETED_STATUSES
    + [
        SalesOrderVDRLDocument
        .DocumentStatus
        .ON_HOLD
    ]
)


def parse_optional_date(
    value,
):
    """
    Convert YYYY-MM-DD text into a date.

    Invalid values are ignored instead of causing
    the dashboard to fail.
    """

    if not value:
        return None

    try:
        return date.fromisoformat(
            value
        )

    except ValueError:
        return None


def get_analytics_filters(
    request,
):
    return {
        "customer": (
            request.GET
            .get(
                "customer",
                "",
            )
            .strip()
        ),

        "sales_order": (
            request.GET
            .get(
                "sales_order",
                "",
            )
            .strip()
        ),

        "department": (
            request.GET
            .get(
                "department",
                "",
            )
            .strip()
        ),

        "date_from": (
            request.GET
            .get(
                "date_from",
                "",
            )
            .strip()
        ),

        "date_to": (
            request.GET
            .get(
                "date_to",
                "",
            )
            .strip()
        ),
    }


def get_base_documents(
    request,
):
    """
    Return only active documents that the logged-in
    user is permitted to see.
    """

    documents = (
        SalesOrderVDRLDocument
        .objects
        .filter(
            is_active=True,
            vdrl__is_current=True,
            vdrl__sales_order__is_active=True,
        )
        .select_related(
            "vdrl",
            "vdrl__sales_order",
            "vdrl__sales_order__customer",
            "vdrl__sales_order__project",
            "responsible_department",
            "responsible_person",
        )
    )

    return (
        filter_documents_for_user(
            request.user,
            documents,
        )
    )


def apply_analytics_filters(
    documents,
    filters,
):
    """
    Apply the dashboard filters.
    """

    if (
        filters["customer"]
        .isdigit()
    ):
        documents = (
            documents
            .filter(
                vdrl__sales_order__customer_id=(
                    filters[
                        "customer"
                    ]
                )
            )
        )

    if (
        filters["sales_order"]
        .isdigit()
    ):
        documents = (
            documents
            .filter(
                vdrl__sales_order_id=(
                    filters[
                        "sales_order"
                    ]
                )
            )
        )

    if (
        filters["department"]
        .isdigit()
    ):
        documents = (
            documents
            .filter(
                responsible_department_id=(
                    filters[
                        "department"
                    ]
                )
            )
        )

    date_from = (
        parse_optional_date(
            filters[
                "date_from"
            ]
        )
    )

    date_to = (
        parse_optional_date(
            filters[
                "date_to"
            ]
        )
    )

    if date_from:
        documents = (
            documents
            .filter(
                vdrl__sales_order__order_date__gte=(
                    date_from
                )
            )
        )

    if date_to:
        documents = (
            documents
            .filter(
                vdrl__sales_order__order_date__lte=(
                    date_to
                )
            )
        )

    return documents


def get_month_buckets(
    today,
    month_count=12,
):
    """
    Build month keys and labels for the last
    12 months, including the current month.
    """

    buckets = []

    current_month_index = (
        today.year
        * 12
        + (
            today.month
            - 1
        )
    )

    for offset in reversed(
        range(
            month_count
        )
    ):
        month_index = (
            current_month_index
            - offset
        )

        year = (
            month_index
            // 12
        )

        month = (
            month_index
            % 12
            + 1
        )

        month_date = date(
            year,
            month,
            1,
        )

        buckets.append(
            {
                "key": (
                    f"{year:04d}-"
                    f"{month:02d}"
                ),

                "label": (
                    month_date
                    .strftime(
                        "%b %Y"
                    )
                ),

                "year": year,

                "month": month,
            }
        )

    return buckets


def get_user_display_name_from_row(
    row,
    prefix,
):
    """
    Build an employee display name from a
    values()/annotate() result row.
    """

    first_name = (
        row.get(
            f"{prefix}__first_name"
        )
        or ""
    ).strip()

    last_name = (
        row.get(
            f"{prefix}__last_name"
        )
        or ""
    ).strip()

    full_name = (
        f"{first_name} "
        f"{last_name}"
    ).strip()

    if full_name:
        return full_name

    return (
        row.get(
            f"{prefix}__username"
        )
        or "Unknown"
    )


@login_required
@permission_required(
    "core.view_management_reports",
    raise_exception=True,
)
def advanced_dashboard(
    request,
):
    today = (
        timezone.localdate()
    )

    filters = (
        get_analytics_filters(
            request
        )
    )

    documents = (
        apply_analytics_filters(
            get_base_documents(
                request
            ),
            filters,
        )
        .distinct()
    )


    # =====================================================
    # APPLICABLE DOCUMENTS
    # =====================================================

    applicable_documents = (
        documents
        .filter(
            applicability_status=(
                SalesOrderVDRLDocument
                .ApplicabilityStatus
                .REQUIRED
            )
        )
        .exclude(
            status__in=[
                SalesOrderVDRLDocument
                .DocumentStatus
                .NOT_APPLICABLE,

                SalesOrderVDRLDocument
                .DocumentStatus
                .CANCELLED,
            ]
        )
    )


    total_documents = (
        documents.count()
    )

    total_applicable = (
        applicable_documents
        .count()
    )

    approved_documents = (
        applicable_documents
        .filter(
            status=(
                SalesOrderVDRLDocument
                .DocumentStatus
                .APPROVED
            )
        )
        .count()
    )


    approval_rate = (
        round(
            approved_documents
            * 100
            / total_applicable,
            1,
        )

        if total_applicable

        else 0
    )


    # =====================================================
    # OVERDUE DOCUMENTS
    # =====================================================

    overdue_internal_documents = (
        applicable_documents
        .exclude(
            status__in=(
                INTERNAL_EXCLUDED_STATUSES
            )
        )
        .filter(
            Q(
                first_submission_at__isnull=True,
                planned_submission_date__lt=(
                    today
                ),
            )
            |
            Q(
                first_submission_at__isnull=False,
                forecast_submission_date__lt=(
                    today
                ),
            )
        )
    )


    overdue_customer_documents = (
        applicable_documents
        .filter(
            status__in=(
                CUSTOMER_STATUSES
            ),
            customer_review_due_date__lt=(
                today
            ),
        )
    )


    overdue_document_ids = set(
        overdue_internal_documents
        .values_list(
            "id",
            flat=True,
        )
    )

    overdue_document_ids.update(
        overdue_customer_documents
        .values_list(
            "id",
            flat=True,
        )
    )


    overdue_documents = len(
        overdue_document_ids
    )


    # =====================================================
    # ON-TIME FIRST SUBMISSION RATE
    # =====================================================
    submission_records = list(
    applicable_documents
    .filter(
        first_submission_at__isnull=False,
        planned_submission_date__isnull=False,
    )
    .select_related(None)
    .only(
        "first_submission_at",
        "planned_submission_date",
    )
)


    on_time_first_submissions = 0

    for document in (
        submission_records
    ):
        if (
            document
            .first_submission_at
            .date()
            <=
            document
            .planned_submission_date
        ):
            on_time_first_submissions += 1


    on_time_submission_rate = (
        round(
            on_time_first_submissions
            * 100
            / len(
                submission_records
            ),
            1,
        )

        if submission_records

        else 0
    )


    # =====================================================
    # TRANSACTION PERFORMANCE
    # =====================================================

    document_transactions = (
        DocumentTransaction
        .objects
        .filter(
            document__in=(
                documents
            )
        )
    )


    average_internal_days = (
        document_transactions
        .filter(
            elapsed_holder_type=(
                DocumentTransaction
                .HolderType
                .INTERNAL
            )
        )
        .aggregate(
            average=Avg(
                "elapsed_calendar_days"
            )
        )[
            "average"
        ]
        or Decimal(
            "0.00"
        )
    )


    average_customer_days = (
        document_transactions
        .filter(
            elapsed_holder_type=(
                DocumentTransaction
                .HolderType
                .CUSTOMER
            )
        )
        .aggregate(
            average=Avg(
                "elapsed_calendar_days"
            )
        )[
            "average"
        ]
        or Decimal(
            "0.00"
        )
    )


    average_review_cycles = (
        applicable_documents
        .filter(
            current_cycle__gt=0
        )
        .aggregate(
            average=Avg(
                "current_cycle"
            )
        )[
            "average"
        ]
        or 0
    )


    # =====================================================
    # CRS PERFORMANCE
    # =====================================================

    all_crs_comments = (
        CRSComment
        .objects
        .filter(
            crs__document__in=(
                documents
            )
        )
    )


    open_crs_comments = (
        all_crs_comments
        .exclude(
            status=(
                CRSComment
                .Status
                .CLOSED
            )
        )
    )


    open_crs_comment_count = (
        open_crs_comments
        .count()
    )


    overdue_crs_comment_count = (
        open_crs_comments
        .filter(
            target_response_date__lt=(
                today
            )
        )
        .count()
    )


    # =====================================================
    # KPI SUMMARY
    # =====================================================

    summary = {
        "total_documents": (
            total_documents
        ),

        "approval_rate": (
            approval_rate
        ),

        "approved_documents": (
            approved_documents
        ),

        "on_time_submission_rate": (
            on_time_submission_rate
        ),

        "average_internal_days": (
            round(
                float(
                    average_internal_days
                ),
                2,
            )
        ),

        "average_customer_days": (
            round(
                float(
                    average_customer_days
                ),
                2,
            )
        ),

        "average_review_cycles": (
            round(
                float(
                    average_review_cycles
                ),
                2,
            )
        ),

        "overdue_documents": (
            overdue_documents
        ),

        "open_crs_comments": (
            open_crs_comment_count
        ),

        "overdue_crs_comments": (
            overdue_crs_comment_count
        ),
    }


    # =====================================================
    # CHART 1 — DOCUMENT STATUS DISTRIBUTION
    # =====================================================

    status_rows = (
        documents
        .values(
            "status"
        )
        .annotate(
            total=Count(
                "id"
            )
        )
        .order_by(
            "status"
        )
    )


    status_labels = (
        dict(
            SalesOrderVDRLDocument
            .DocumentStatus
            .choices
        )
    )


    document_status_chart = {
        "labels": [
            status_labels.get(
                row[
                    "status"
                ],
                row[
                    "status"
                ],
            )

            for row in (
                status_rows
            )
        ],

        "values": [
            row[
                "total"
            ]

            for row in (
                status_rows
            )
        ],
    }


    # =====================================================
    # CHART 2 — APPROVAL TREND
    # =====================================================

    month_buckets = (
        get_month_buckets(
            today,
            12,
        )
    )


    approval_counter = Counter()


    approval_dates = (
        documents
        .filter(
            final_approval_at__isnull=False
        )
        .values_list(
            "final_approval_at",
            flat=True,
        )
    )


    for approval_datetime in (
        approval_dates
    ):
        if timezone.is_aware(
            approval_datetime
        ):
            approval_datetime = (
                timezone.localtime(
                    approval_datetime
                )
            )

        month_key = (
            f"{approval_datetime.year:04d}-"
            f"{approval_datetime.month:02d}"
        )

        approval_counter[
            month_key
        ] += 1


    approval_trend_chart = {
        "labels": [
            bucket[
                "label"
            ]
            for bucket
            in month_buckets
        ],

        "values": [
            approval_counter.get(
                bucket[
                    "key"
                ],
                0,
            )
            for bucket
            in month_buckets
        ],
    }


    # =====================================================
    # CHART 3 — DEPARTMENT WORKLOAD
    # =====================================================

    internal_pending_documents = (
        documents
        .exclude(
            status__in=(
                INTERNAL_EXCLUDED_STATUSES
            )
        )
    )


    department_pending_rows = (
        internal_pending_documents
        .values(
            "responsible_department__name"
        )
        .annotate(
            total=Count(
                "id"
            )
        )
    )


    department_overdue_rows = (
        overdue_internal_documents
        .values(
            "responsible_department__name"
        )
        .annotate(
            total=Count(
                "id"
            )
        )
    )


    pending_by_department = {
        (
            row[
                "responsible_department__name"
            ]
            or "Unassigned"
        ): row[
            "total"
        ]

        for row in (
            department_pending_rows
        )
    }


    overdue_by_department = {
        (
            row[
                "responsible_department__name"
            ]
            or "Unassigned"
        ): row[
            "total"
        ]

        for row in (
            department_overdue_rows
        )
    }


    department_names = sorted(
        set(
            pending_by_department
        )
        |
        set(
            overdue_by_department
        )
    )


    department_workload_chart = {
        "labels": (
            department_names
        ),

        "pending": [
            pending_by_department.get(
                department,
                0,
            )
            for department
            in department_names
        ],

        "overdue": [
            overdue_by_department.get(
                department,
                0,
            )
            for department
            in department_names
        ],
    }


    # =====================================================
    # CHART 4 — INTERNAL VS CUSTOMER HOLDING TIME
    # =====================================================

    holding_rows = (
        document_transactions
        .exclude(
            elapsed_holder_type=""
        )
        .values(
            "elapsed_holder_type"
        )
        .annotate(
            total_days=Sum(
                "elapsed_calendar_days"
            )
        )
    )


    holding_totals = {
        row[
            "elapsed_holder_type"
        ]: (
            row[
                "total_days"
            ]
            or Decimal(
                "0.00"
            )
        )

        for row in (
            holding_rows
        )
    }


    # Add the currently open holding period.
    active_documents = (
    documents
    .exclude(
        status__in=(
            COMPLETED_STATUSES
        )
    )
    .select_related(None)
    .only(
        "status",
        "current_action_since",
    )
)


    for document in (
        active_documents
    ):
        aging = (
            document
            .current_aging_days
        )

        if (
            document.current_holder
            == "Internal"
        ):
            holding_totals[
                DocumentTransaction
                .HolderType
                .INTERNAL
            ] = (
                holding_totals.get(
                    DocumentTransaction
                    .HolderType
                    .INTERNAL,
                    Decimal(
                        "0.00"
                    ),
                )
                +
                aging
            )

        elif (
            document.current_holder
            == "Customer"
        ):
            holding_totals[
                DocumentTransaction
                .HolderType
                .CUSTOMER
            ] = (
                holding_totals.get(
                    DocumentTransaction
                    .HolderType
                    .CUSTOMER,
                    Decimal(
                        "0.00"
                    ),
                )
                +
                aging
            )

        elif (
            document.current_holder
            == "On Hold"
        ):
            holding_totals[
                DocumentTransaction
                .HolderType
                .ON_HOLD
            ] = (
                holding_totals.get(
                    DocumentTransaction
                    .HolderType
                    .ON_HOLD,
                    Decimal(
                        "0.00"
                    ),
                )
                +
                aging
            )


    delay_ownership_chart = {
        "labels": [
            "Internal",
            "Customer",
            "On Hold",
        ],

        "values": [
            round(
                float(
                    holding_totals.get(
                        DocumentTransaction
                        .HolderType
                        .INTERNAL,
                        Decimal(
                            "0.00"
                        ),
                    )
                ),
                2,
            ),

            round(
                float(
                    holding_totals.get(
                        DocumentTransaction
                        .HolderType
                        .CUSTOMER,
                        Decimal(
                            "0.00"
                        ),
                    )
                ),
                2,
            ),

            round(
                float(
                    holding_totals.get(
                        DocumentTransaction
                        .HolderType
                        .ON_HOLD,
                        Decimal(
                            "0.00"
                        ),
                    )
                ),
                2,
            ),
        ],
    }


    # =====================================================
    # CHART 5 — REVIEW CYCLE DISTRIBUTION
    # =====================================================

    review_cycle_counter = {
        "1 Cycle": 0,
        "2 Cycles": 0,
        "3 Cycles": 0,
        "4+ Cycles": 0,
    }


    cycle_values = (
        applicable_documents
        .filter(
            current_cycle__gt=0
        )
        .values_list(
            "current_cycle",
            flat=True,
        )
    )


    for cycle_number in (
        cycle_values
    ):
        if cycle_number == 1:
            review_cycle_counter[
                "1 Cycle"
            ] += 1

        elif cycle_number == 2:
            review_cycle_counter[
                "2 Cycles"
            ] += 1

        elif cycle_number == 3:
            review_cycle_counter[
                "3 Cycles"
            ] += 1

        else:
            review_cycle_counter[
                "4+ Cycles"
            ] += 1


    review_cycle_chart = {
        "labels": list(
            review_cycle_counter
            .keys()
        ),

        "values": list(
            review_cycle_counter
            .values()
        ),
    }


    # =====================================================
    # CHART 6 — CRS COMMENT STATUS DISTRIBUTION
    # =====================================================

    crs_status_rows = (
        all_crs_comments
        .values(
            "status"
        )
        .annotate(
            total=Count(
                "id"
            )
        )
        .order_by(
            "status"
        )
    )


    crs_status_labels = dict(
        CRSComment
        .Status
        .choices
    )


    crs_status_chart = {
        "labels": [
            crs_status_labels.get(
                row[
                    "status"
                ],
                row[
                    "status"
                ],
            )
            for row
            in crs_status_rows
        ],

        "values": [
            row[
                "total"
            ]
            for row
            in crs_status_rows
        ],
    }


    # =====================================================
    # CRS COUNTS BY DOCUMENT
    # =====================================================

    crs_document_rows = (
        all_crs_comments
        .values(
            "crs__document_id"
        )
        .annotate(
            open_count=Count(
                "id",
                filter=(
                    ~Q(
                        status=(
                            CRSComment
                            .Status
                            .CLOSED
                        )
                    )
                ),
            ),

            overdue_count=Count(
                "id",
                filter=(
                    ~Q(
                        status=(
                            CRSComment
                            .Status
                            .CLOSED
                        )
                    )
                    &
                    Q(
                        target_response_date__lt=(
                            today
                        )
                    )
                ),
            ),
        )
    )


    crs_by_document = {
        row[
            "crs__document_id"
        ]: {
            "open": (
                row[
                    "open_count"
                ]
            ),

            "overdue": (
                row[
                    "overdue_count"
                ]
            ),
        }

        for row in (
            crs_document_rows
        )
    }


    # =====================================================
    # SALES ORDERS AT RISK
    # =====================================================

    sales_order_metrics = {}


    for document in (
        documents
    ):
        sales_order = (
            document
            .vdrl
            .sales_order
        )

        if (
            sales_order.pk
            not in sales_order_metrics
        ):
            sales_order_metrics[
                sales_order.pk
            ] = {
                "sales_order": (
                    sales_order
                ),

                "total_documents": 0,

                "approved_documents": 0,

                "overdue_documents": 0,

                "customer_pending": 0,

                "internal_pending": 0,

                "open_crs_comments": 0,

                "overdue_crs_comments": 0,
            }


        row = (
            sales_order_metrics[
                sales_order.pk
            ]
        )


        row[
            "total_documents"
        ] += 1


        if (
            document.status
            ==
            SalesOrderVDRLDocument
            .DocumentStatus
            .APPROVED
        ):
            row[
                "approved_documents"
            ] += 1


        if (
            document.pk
            in overdue_document_ids
        ):
            row[
                "overdue_documents"
            ] += 1


        if (
            document.status
            in CUSTOMER_STATUSES
        ):
            row[
                "customer_pending"
            ] += 1


        if (
            document.status
            not in
            INTERNAL_EXCLUDED_STATUSES
        ):
            row[
                "internal_pending"
            ] += 1


        document_crs = (
            crs_by_document.get(
                document.pk,
                {
                    "open": 0,
                    "overdue": 0,
                },
            )
        )


        row[
            "open_crs_comments"
        ] += (
            document_crs[
                "open"
            ]
        )


        row[
            "overdue_crs_comments"
        ] += (
            document_crs[
                "overdue"
            ]
        )


    project_risk_rows = []


    for row in (
        sales_order_metrics
        .values()
    ):
        total_documents = (
            row[
                "total_documents"
            ]
        )

        approved_documents = (
            row[
                "approved_documents"
            ]
        )


        row[
            "approval_percent"
        ] = (
            round(
                approved_documents
                * 100
                / total_documents
            )

            if total_documents

            else 0
        )


        # Transparent operational risk score:
        #
        # Overdue Document     = 3 points
        # Overdue CRS Comment  = 2 points
        # Open CRS Comment     = 1 point
        # Internal Pending     = 1 point

        row[
            "risk_score"
        ] = (
            row[
                "overdue_documents"
            ]
            * 3
            +
            row[
                "overdue_crs_comments"
            ]
            * 2
            +
            row[
                "open_crs_comments"
            ]
            +
            row[
                "internal_pending"
            ]
        )


        if (
            row[
                "risk_score"
            ]
            >= 10
        ):
            row[
                "risk_level"
            ] = "High"

        elif (
            row[
                "risk_score"
            ]
            >= 4
        ):
            row[
                "risk_level"
            ] = "Medium"

        else:
            row[
                "risk_level"
            ] = "Low"


        project_risk_rows.append(
            row
        )


    project_risk_rows.sort(
        key=lambda row: (
            -row[
                "risk_score"
            ],
            -row[
                "overdue_documents"
            ],
            (
                row[
                    "sales_order"
                ]
                .sales_order_number
            ),
        )
    )


    project_risk_rows = (
        project_risk_rows[
            :10
        ]
    )


    # =====================================================
    # EMPLOYEE WORKLOAD
    # =====================================================

    employee_data = {}


    internal_employee_rows = (
        internal_pending_documents
        .filter(
            responsible_person__isnull=False
        )
        .values(
            "responsible_person_id",
            "responsible_person__first_name",
            "responsible_person__last_name",
            "responsible_person__username",
            (
                "responsible_person__"
                "employee_profile__"
                "department__name"
            ),
        )
        .annotate(
            pending_documents=Count(
                "id"
            )
        )
    )


    for row in (
        internal_employee_rows
    ):
        user_id = (
            row[
                "responsible_person_id"
            ]
        )

        employee_data[
            user_id
        ] = {
            "user_id": user_id,

            "name": (
                get_user_display_name_from_row(
                    row,
                    "responsible_person",
                )
            ),

            "department": (
                row.get(
                    (
                        "responsible_person__"
                        "employee_profile__"
                        "department__name"
                    )
                )
                or "-"
            ),

            "pending_documents": (
                row[
                    "pending_documents"
                ]
            ),

            "overdue_documents": 0,

            "open_crs_comments": 0,

            "overdue_crs_comments": 0,
        }


    overdue_employee_rows = (
        overdue_internal_documents
        .filter(
            responsible_person__isnull=False
        )
        .values(
            "responsible_person_id"
        )
        .annotate(
            overdue_documents=Count(
                "id"
            )
        )
    )


    for row in (
        overdue_employee_rows
    ):
        user_id = (
            row[
                "responsible_person_id"
            ]
        )

        if user_id in (
            employee_data
        ):
            employee_data[
                user_id
            ][
                "overdue_documents"
            ] = (
                row[
                    "overdue_documents"
                ]
            )


    crs_employee_rows = (
        open_crs_comments
        .filter(
            assigned_person__isnull=False
        )
        .values(
            "assigned_person_id",
            "assigned_person__first_name",
            "assigned_person__last_name",
            "assigned_person__username",
            (
                "assigned_person__"
                "employee_profile__"
                "department__name"
            ),
        )
        .annotate(
            open_crs_comments=Count(
                "id"
            ),

            overdue_crs_comments=Count(
                "id",
                filter=Q(
                    target_response_date__lt=(
                        today
                    )
                ),
            ),
        )
    )


    for row in (
        crs_employee_rows
    ):
        user_id = (
            row[
                "assigned_person_id"
            ]
        )


        if (
            user_id
            not in employee_data
        ):
            employee_data[
                user_id
            ] = {
                "user_id": user_id,

                "name": (
                    get_user_display_name_from_row(
                        row,
                        "assigned_person",
                    )
                ),

                "department": (
                    row.get(
                        (
                            "assigned_person__"
                            "employee_profile__"
                            "department__name"
                        )
                    )
                    or "-"
                ),

                "pending_documents": 0,

                "overdue_documents": 0,

                "open_crs_comments": 0,

                "overdue_crs_comments": 0,
            }


        employee_data[
            user_id
        ][
            "open_crs_comments"
        ] = (
            row[
                "open_crs_comments"
            ]
        )


        employee_data[
            user_id
        ][
            "overdue_crs_comments"
        ] = (
            row[
                "overdue_crs_comments"
            ]
        )


    employee_workload_rows = list(
        employee_data.values()
    )


    for row in (
        employee_workload_rows
    ):
        row[
            "total_open_actions"
        ] = (
            row[
                "pending_documents"
            ]
            +
            row[
                "open_crs_comments"
            ]
        )


        row[
            "total_overdue_actions"
        ] = (
            row[
                "overdue_documents"
            ]
            +
            row[
                "overdue_crs_comments"
            ]
        )


    employee_workload_rows.sort(
        key=lambda row: (
            -row[
                "total_overdue_actions"
            ],
            -row[
                "total_open_actions"
            ],
            row[
                "name"
            ],
        )
    )


    employee_workload_rows = (
        employee_workload_rows[
            :15
        ]
    )


    # =====================================================
    # CHART DATA
    # =====================================================

    chart_data = {
        "document_status": (
            document_status_chart
        ),

        "approval_trend": (
            approval_trend_chart
        ),

        "department_workload": (
            department_workload_chart
        ),

        "delay_ownership": (
            delay_ownership_chart
        ),

        "review_cycles": (
            review_cycle_chart
        ),

        "crs_status": (
            crs_status_chart
        ),
    }


    # =====================================================
    # FILTER OPTIONS
    # =====================================================

    accessible_sales_orders = (
        filter_sales_orders_for_user(
            request.user,
            (
                SalesOrder
                .objects
                .filter(
                    is_active=True
                )
                .select_related(
                    "customer",
                    "project",
                )
            ),
        )
        .order_by(
            "-order_date",
            "sales_order_number",
        )
    )


    accessible_customers = (
        Customer
        .objects
        .filter(
            sales_orders__in=(
                accessible_sales_orders
            )
        )
        .distinct()
        .order_by(
            "name"
        )
    )


    context = {
        "today": today,

        "filters": filters,

        "summary": summary,

        "chart_data": (
            chart_data
        ),

        "project_risk_rows": (
            project_risk_rows
        ),

        "employee_workload_rows": (
            employee_workload_rows
        ),

        "customers": (
            accessible_customers
        ),

        "sales_orders": (
            accessible_sales_orders
        ),

        "departments": (
            Department
            .objects
            .filter(
                is_active=True
            )
            .order_by(
                "name"
            )
        ),
    }


    return render(
        request,
        "core/advanced_dashboard.html",
        context,
    )