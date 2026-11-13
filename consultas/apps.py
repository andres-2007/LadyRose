from django.apps import AppConfig


class ConsultasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "consultas"
    verbose_name = "Seguimiento de clientes"

    def ready(self):
        # HU 28: una consulta pasa sola a "Compró" cuando esa persona compra o paga un curso
        from . import senales  # noqa: F401
