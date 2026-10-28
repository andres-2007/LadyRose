"""Crea los usuarios del panel para la dueña y la diseñadora de accesorios (HU 15).

Uso:
    python manage.py crear_usuarios --clave-duena "ClaveSegura1" --clave-disenadora "ClaveSegura2"
"""
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand

from core.roles import GRUPO_DISENADORA, GRUPO_DUENA, crear_roles


class Command(BaseCommand):
    help = "Crea los usuarios 'duena' y 'disenadora' con acceso al panel."

    def add_arguments(self, parser):
        parser.add_argument("--clave-duena", required=True)
        parser.add_argument("--clave-disenadora", required=True)

    def handle(self, *args, **opciones):
        crear_roles()
        datos = [
            ("duena", "Lady", "Riomaña", GRUPO_DUENA, opciones["clave_duena"]),
            ("disenadora", "Liliana", "Velasquez", GRUPO_DISENADORA, opciones["clave_disenadora"]),
        ]
        for usuario, nombre, apellido, grupo, clave in datos:
            user, creado = User.objects.get_or_create(username=usuario)
            user.first_name, user.last_name = nombre, apellido
            user.is_staff = True  # puede entrar al panel /admin
            user.set_password(clave)
            user.save()
            user.groups.set([Group.objects.get(name=grupo)])
            estado = "creado" if creado else "actualizado"
            self.stdout.write(self.style.SUCCESS(f"Usuario '{usuario}' {estado} ({grupo})."))
