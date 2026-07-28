# Add imports to vdrl_project/urls.py:
from django.urls import include, path
from operations_portal.views import home as operations_home

# Put these entries BEFORE the existing core URL entries.
urlpatterns = [
    path("", operations_home, name="home"),
    path("itp/", include("itp.urls")),
    path("calibration/", include("calibration.urls")),

    # Keep every existing admin, accounts, media and core/VDRL URL below.
]
