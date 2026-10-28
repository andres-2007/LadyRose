from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from .imagenes import FotoOptimizadaMixin


class ModeloUnico(models.Model):
    """Modelo del que solo existe un registro (configuraciones del sitio)."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # No se permite borrar la configuración, solo editarla.
        return

    @classmethod
    def obtener(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ConfiguracionTienda(ModeloUnico):
    """HU 25: monto mínimo de compra mayorista configurable por la dueña."""

    monto_minimo_mayorista = models.DecimalField(
        "Monto mínimo de compra mayorista",
        max_digits=12,
        decimal_places=0,
        default=Decimal("200000"),
        validators=[MinValueValidator(Decimal("1"), message="El monto debe ser mayor a cero.")],
        help_text="Valor en pesos. Aplica a los pedidos mayoristas que se creen después de guardarlo.",
    )
    actualizado = models.DateTimeField("Última actualización", auto_now=True)

    class Meta:
        verbose_name = "configuración de la tienda"
        verbose_name_plural = "configuración de la tienda"

    def __str__(self):
        return "Configuración de la tienda"


class ContenidoHistoria(ModeloUnico):
    """HU 18: contenido editable de la sección "Nuestra historia"."""

    LEMA = "Todo es posible"

    titulo = models.CharField("Título", max_length=150, default="Nuestra historia")
    texto = models.TextField("Texto", blank=True)
    video_url = models.URLField(
        "Video (enlace de YouTube)", blank=True,
        help_text="Pegue el enlace del video, por ejemplo https://www.youtube.com/watch?v=...",
    )

    class Meta:
        verbose_name = "sección Nuestra historia"
        verbose_name_plural = "sección Nuestra historia"

    def __str__(self):
        return self.titulo

    @property
    def video_embed(self):
        """Convierte un enlace normal de YouTube en uno que se puede incrustar."""
        url = self.video_url or ""
        if "watch?v=" in url:
            return "https://www.youtube.com/embed/" + url.split("watch?v=")[1].split("&")[0]
        if "youtu.be/" in url:
            return "https://www.youtube.com/embed/" + url.split("youtu.be/")[1].split("?")[0]
        return url


class FotoTaller(FotoOptimizadaMixin, models.Model):
    historia = models.ForeignKey(ContenidoHistoria, on_delete=models.CASCADE, related_name="fotos")
    imagen = models.ImageField("Foto", upload_to="historia/")
    descripcion = models.CharField("Descripción", max_length=150, blank=True)
    orden = models.PositiveIntegerField("Orden", default=0)

    class Meta:
        ordering = ["orden", "id"]
        verbose_name = "foto del taller"
        verbose_name_plural = "fotos del taller"

    def __str__(self):
        return self.descripcion or f"Foto {self.pk}"


class VisitaOrigen(models.Model):
    """HU 31: registro del canal desde el que llega cada visita."""

    class Canal(models.TextChoices):
        INSTAGRAM = "instagram", "Instagram"
        FACEBOOK = "facebook", "Facebook"
        TIKTOK = "tiktok", "TikTok"
        WHATSAPP = "whatsapp", "WhatsApp"
        DIRECTO = "directo", "Entrada directa"
        OTRO = "otro", "Otro"

    canal = models.CharField("Canal", max_length=20, choices=Canal.choices)
    pagina = models.CharField("Página de llegada", max_length=300)
    fecha = models.DateTimeField("Fecha", auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "visita por canal"
        verbose_name_plural = "visitas por canal"

    def __str__(self):
        return f"{self.get_canal_display()} - {self.fecha:%Y-%m-%d %H:%M}"
