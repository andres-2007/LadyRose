from django.db import models

from catalogo.models import Producto
from core.imagenes import FotoOptimizadaMixin

# HU 20: texto del aviso que el cliente debe aceptar antes de enviar la solicitud
AVISO_PIEZA_UNICA = (
    "Entiendo que, por la naturaleza de los insumos y el estilo de la diseñadora de accesorios, "
    "cada pieza es única e irrepetible: la pieza final seguirá el estilo de la imagen de "
    "referencia, pero no será una copia exacta."
)

MAX_IMAGENES = 5


class SolicitudCotizacion(models.Model):
    """Solicitud de una pieza personalizada (HU 09 y HU 20) o de cambios sobre
    un producto del catálogo (HU 34)."""

    class Tipo(models.TextChoices):
        PERSONALIZADA = "personalizada", "Pieza personalizada"
        CAMBIOS_PRODUCTO = "cambios", "Cambios sobre un producto del catálogo"
        # HU 08: pieza inspirada en una de la galería de piezas vendidas
        INSPIRADA = "inspirada", "Inspirada en una pieza de la galería"

    class Estado(models.TextChoices):
        NUEVA = "nueva", "Nueva"
        RESPONDIDA = "respondida", "Respondida"

    tipo = models.CharField("Tipo", max_length=20, choices=Tipo.choices, default=Tipo.PERSONALIZADA)
    nombre = models.CharField("Nombre", max_length=150)
    whatsapp = models.CharField("WhatsApp", max_length=20)
    correo = models.EmailField("Correo electrónico", blank=True)
    descripcion = models.TextField("¿Qué pieza quieres?", blank=True)
    # HU 09: historia o motivo detrás del accesorio (opcional)
    motivo = models.TextField(
        "¿Para quién es o qué historia la inspira? (opcional)", blank=True,
    )
    # HU 34: solicitud ligada a un producto del catálogo
    producto = models.ForeignKey(
        Producto, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="solicitudes", verbose_name="Producto original",
    )
    cambio_color = models.CharField("Color", max_length=100, blank=True)
    cambio_talla = models.CharField("Talla", max_length=100, blank=True)
    cambio_material = models.CharField("Material", max_length=100, blank=True)
    cambio_otro = models.TextField("Otro cambio", blank=True)
    # HU 20: aceptación del aviso de pieza única
    acepta_pieza_unica = models.BooleanField("Aceptó el aviso de pieza única", default=False)
    fecha_aceptacion = models.DateTimeField("Fecha de aceptación del aviso", null=True, blank=True)

    estado = models.CharField("Estado", max_length=20, choices=Estado.choices, default=Estado.NUEVA)
    fecha = models.DateTimeField("Fecha", auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "solicitud de cotización"
        verbose_name_plural = "solicitudes de cotización"

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.nombre}"


class ImagenReferencia(FotoOptimizadaMixin, models.Model):
    solicitud = models.ForeignKey(SolicitudCotizacion, on_delete=models.CASCADE, related_name="imagenes")
    imagen = models.ImageField("Imagen", upload_to="cotizaciones/")

    class Meta:
        verbose_name = "imagen de referencia"
        verbose_name_plural = "imágenes de referencia"

    def __str__(self):
        return f"Imagen {self.pk}"
