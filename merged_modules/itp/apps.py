from django.apps import AppConfig


class ITPConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "itp"
    verbose_name = "ITP and NOI Management"

    def ready(self) -> None:
        from . import signals  # noqa: F401
