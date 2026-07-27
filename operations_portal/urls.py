from django.urls import path

from . import views

app_name = "operations_portal"

urlpatterns = [
    path("", views.home, name="home"),
]
