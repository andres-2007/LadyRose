"""Utilidades compartidas por las pruebas."""
import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

MEDIA_PRUEBAS = tempfile.mkdtemp(prefix="ladyrose_media_")


def imagen(nombre="foto.jpg", formato="JPEG", tipo="image/jpeg", tamano=(50, 50)):
    buffer = io.BytesIO()
    Image.new("RGB", tamano, "pink").save(buffer, format=formato)
    return SimpleUploadedFile(nombre, buffer.getvalue(), content_type=tipo)


@override_settings(MEDIA_ROOT=MEDIA_PRUEBAS)
class PruebaConArchivos(TestCase):
    """Las imágenes que se suben en las pruebas van a una carpeta temporal."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_PRUEBAS, ignore_errors=True)


def iniciar_sesion_cliente(prueba, correo="cliente@correo.com", nombre="Cliente Prueba", **datos):
    """HU 27: para comprar y para inscribirse a un curso hay que tener cuenta de cliente."""
    from django.contrib.auth import get_user_model

    from clientes.models import Cliente

    usuario = get_user_model().objects.create_user(username=correo, email=correo, password="ClaveSegura123*",
                                                   first_name=nombre)
    cliente = Cliente.objects.create(usuario=usuario, **datos)
    prueba.client.force_login(usuario)
    return cliente
