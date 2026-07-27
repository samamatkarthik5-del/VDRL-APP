from django.urls import path

from . import views

app_name = "itp"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("itp/upload/", views.upload_itp, name="upload_itp"),
    path("itp/<uuid:pk>/", views.itp_detail, name="itp_detail"),
    path("itp/<uuid:pk>/activate/", views.activate_itp, name="activate_itp"),
    path("clause/<uuid:pk>/edit/", views.edit_clause, name="edit_clause"),
    path("annexure/upload/", views.upload_annexure, name="upload_annexure"),
    path("annexure/<uuid:pk>/", views.annexure_detail, name="annexure_detail"),
    path("annexure/<uuid:pk>/activate/", views.activate_annexure, name="activate_annexure"),
    path("annexure-line/<uuid:pk>/edit/", views.edit_annexure_line, name="edit_annexure_line"),
    path("mapping/generate/", views.generate_mapping, name="generate_mapping"),
    path(
        "mapping/<uuid:itp_pk>/<uuid:annexure_pk>/",
        views.mapping_review,
        name="mapping_review",
    ),
    path("noi/", views.noi_list, name="noi_list"),
    path("noi/create/", views.create_noi_view, name="create_noi"),
    path("noi/<uuid:pk>/", views.noi_detail, name="noi_detail"),
    path("noi/<uuid:pk>/confirm/", views.confirm_noi, name="confirm_noi"),
    path("hold/<uuid:pk>/release/", views.release_hold, name="release_hold"),
    path("activity/internal/", views.record_internal_activity, name="record_internal_activity"),
    path("alerts/", views.alerts, name="alerts"),
    path("alerts/<uuid:pk>/resolve/", views.resolve_alert, name="resolve_alert"),
]
