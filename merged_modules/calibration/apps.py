from django.apps import AppConfig


class CalibrationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "calibration"
    verbose_name = "Calibration Management"

    def ready(self):
        from . import signals  # noqa: F401
