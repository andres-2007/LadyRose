from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _crear_roles(sender, **kwargs):
    from .roles import crear_roles

    crear_roles()


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Sitio"

    def ready(self):
        # Los grupos se crean (o actualizan) solos cada vez que se corre migrate.
        # Se conecta sin "sender" para que corra después de que existan los
        # permisos de todas las apps.
        post_migrate.connect(_crear_roles, dispatch_uid="ladyrose_crear_roles")
