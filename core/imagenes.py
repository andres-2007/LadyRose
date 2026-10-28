"""Optimización de las fotos que se suben (HU 23).

Las fotos del celular suelen pesar varios MB. Antes de guardarlas se reducen
a un lado máximo de 1600 px y se comprimen, para que la página cargue rápido
con datos móviles. Junto con loading="lazy" en las plantillas, las fotos que
no se ven en pantalla no se descargan hasta que la persona baja.
"""
import io

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

LADO_MAXIMO = 1600
CALIDAD_JPEG = 82


def optimizar(campo, lado_maximo=LADO_MAXIMO):
    """Reduce y comprime la imagen de un ImageField antes de guardarla."""
    if not campo or getattr(campo, "_committed", True):
        return  # no hay foto nueva
    campo.seek(0)
    with Image.open(campo) as original:
        formato = (original.format or "JPEG").upper()
        imagen = ImageOps.exif_transpose(original)  # respeta la orientación del celular
        if max(imagen.size) <= lado_maximo and formato in ("JPEG", "PNG"):
            campo.seek(0)
            return  # ya es liviana
        imagen.thumbnail((lado_maximo, lado_maximo))
        salida = io.BytesIO()
        if formato == "PNG":
            imagen.save(salida, format="PNG", optimize=True)
            extension = "png"
        else:
            imagen.convert("RGB").save(salida, format="JPEG", quality=CALIDAD_JPEG, optimize=True)
            extension = "jpg"
    nombre = campo.name.rsplit("/", 1)[-1].rsplit(".", 1)[0] + "." + extension
    campo.save(nombre, ContentFile(salida.getvalue()), save=False)


class FotoOptimizadaMixin:
    """Se agrega a los modelos de fotos para optimizar el campo `imagen`."""

    def save(self, *args, **kwargs):
        optimizar(self.imagen)
        super().save(*args, **kwargs)
