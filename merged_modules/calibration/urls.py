from django.urls import path

from . import views

app_name = "calibration"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("instruments/", views.instrument_list, name="instrument_list"),
    path("instruments/add/", views.instrument_create, name="instrument_create"),
    path("instruments/<uuid:pk>/", views.instrument_detail, name="instrument_detail"),
    path("instruments/<uuid:pk>/edit/", views.instrument_update, name="instrument_update"),
    path("instruments/<uuid:instrument_pk>/cycles/add/", views.cycle_create, name="cycle_create"),
    path("cycles/<uuid:pk>/verify/", views.cycle_verify, name="cycle_verify"),
    path("due/", views.due_list, name="due_list"),
    path("master-list/", views.master_list, name="master_list"),
]
