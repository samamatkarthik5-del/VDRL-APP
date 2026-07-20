from django.urls import path

from . import activity_views
from . import dashboard_views
from . import report_views
from . import views
from . import import_views
from . import workflow_views

app_name = "core"


urlpatterns = [
    path(
        "",
        views.dashboard,
        name="dashboard",
    ),

    path(
    "analytics/",
    dashboard_views.advanced_dashboard,
    name="advanced_dashboard",
    ),
    
    path(
        "sales-orders/<int:pk>/",
        views.sales_order_vdrl,
        name="sales_order_vdrl",
    ),

    path(
        "documents/<int:pk>/",
        views.document_detail,
        name="document_detail",
    ),

    path(
        "documents/<int:pk>/edit/",
        views.document_edit,
        name="document_edit",
    ),

    path(
        (
            "documents/<int:pk>/"
            "action/<str:action_type>/"
        ),
        views.document_action,
        name="document_action",
    ),

        path(
        "documents/<int:pk>/files/upload/",
        views.document_file_upload,
        name="document_file_upload",
    ),

    path(
        "files/<int:pk>/open/",
        views.document_file_open,
        name="document_file_open",
    ),

    path(
        "files/<int:pk>/download/",
        views.document_file_download,
        name="document_file_download",
    ),

    path(
        "files/<int:pk>/set-current/",
        views.document_file_set_current,
        name="document_file_set_current",
    ),

    path(
        "documents/<int:document_pk>/crs/create/",
        views.crs_create,
        name="crs_create",
    ),

    path(
        "crs/<int:pk>/",
        views.crs_detail,
        name="crs_detail",
    ),

    path(
        "crs/<int:pk>/edit/",
        views.crs_edit,
        name="crs_edit",
    ),

    path(
        "crs/<int:crs_pk>/comments/add/",
        views.crs_comment_create,
        name="crs_comment_create",
    ),

    path(
        "crs-comments/<int:pk>/edit/",
        views.crs_comment_edit,
        name="crs_comment_edit",
    ),

    path(
    "reports/",
    report_views.management_reports,
    name="management_reports",
    ),

    path(
    "reports/export/xlsx/",
    report_views.export_management_reports_xlsx,
    name="export_management_reports_xlsx",
    ),

    path(
    "imports/",
    import_views.import_center,
    name="import_center",
),

path(
    "imports/customer-template/",
    import_views.import_customer_template,
    name="import_customer_template",
),

path(
    "imports/sales-order-vdrl/",
    import_views.import_sales_order_vdrl,
    name="import_sales_order_vdrl",
),

path(
    "imports/crs-comments/",
    import_views.import_crs_comment_rows,
    name="import_crs_comments",
),

path(
    (
        "imports/templates/"
        "<str:import_type>/"
    ),
    (
        import_views
        .download_excel_import_template
    ),
    name="download_excel_import_template",
),
path(
    "notifications/",
    activity_views.notification_list,
    name="notification_list",
),

path(
    "notifications/<int:pk>/read/",
    activity_views.notification_mark_read,
    name="notification_mark_read",
),

path(
    "notifications/read-all/",
    activity_views.notification_mark_all_read,
    name="notification_mark_all_read",
),

path(
    "audit/",
    activity_views.audit_log_list,
    name="audit_log_list",
),

path(
    "audit/<int:pk>/",
    activity_views.audit_log_detail,
    name="audit_log_detail",
),

path(
    "work-bucket/",
    workflow_views.my_work_bucket,
    name="my_work_bucket",
),

path(
    "documents/<int:document_id>/workflow/",
    workflow_views.document_workflow,
    name="document_workflow",
),

path(
    "documents/<int:document_id>/workflow/assign-department/",
    workflow_views.workflow_assign_department,
    name="workflow_assign_department",
),

path(
    "documents/<int:document_id>/workflow/assign-contributor/",
    workflow_views.workflow_assign_contributor,
    name="workflow_assign_contributor",
),

path(
    "documents/<int:document_id>/workflow/reassign-contributor/",
    workflow_views.workflow_reassign_contributor,
    name="workflow_reassign_contributor",
),

path(
    "documents/<int:document_id>/workflow/raise-open-point/",
    workflow_views.workflow_raise_open_point,
    name="workflow_raise_open_point",
),

path(
    "open-points/<int:open_point_id>/respond/",
    workflow_views.open_point_respond,
    name="open_point_respond",
),

path(
    "open-points/<int:open_point_id>/decide/",
    workflow_views.open_point_decide,
    name="open_point_decide",
),

path(
    "documents/<int:document_id>/workflow/submit-review/",
    workflow_views.workflow_submit_for_review,
    name="workflow_submit_for_review",
),

path(
    "documents/<int:document_id>/workflow/department-review/",
    workflow_views.workflow_department_review,
    name="workflow_department_review",
),

]