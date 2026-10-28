from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from core.imagenes import FotoOptimizadaMixin, optimizar

# HU 02: aviso de cuidados que se muestra por defecto en todas las fichas
AVISO_CUIDADOS = (
    "No apliques lociones ni perfumes sobre el accesorio y no te bañes con él puesto."
)
TEXTO_PH = (
    "El pH de cada piel es diferente y puede influir en la durabilidad y el color del metal."
)


def _slug_unico(instancia, texto):
    base = slugify(texto)[:180] or "item"
    slug, n = base, 2
    Modelo = type(instancia)
    while Modelo.objects.filter(slug=slug).exclude(pk=instancia.pk).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


class Categoria(models.Model):
    nombre = models.CharField("Nombre", max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "categoría"
        verbose_name_plural = "categorías"

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _slug_unico(self, self.nombre)
        super().save(*args, **kwargs)


class Coleccion(models.Model):
    """HU 16: colección temática o de temporada (ej. "Verano", "Día de la madre")."""

    nombre = models.CharField("Nombre", max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    descripcion = models.TextField("Descripción", blank=True)
    portada = models.ImageField("Imagen de portada", upload_to="colecciones/")
    visible = models.BooleanField("Visible en la página", default=True)
    orden = models.PositiveIntegerField("Orden", default=0)

    class Meta:
        ordering = ["orden", "nombre"]
        verbose_name = "colección"
        verbose_name_plural = "colecciones"

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _slug_unico(self, self.nombre)
        optimizar(self.portada)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("catalogo:lista") + f"?coleccion={self.slug}"


class ProductoQuerySet(models.QuerySet):
    def visibles(self):
        return self.filter(visible=True)

    def en_venta(self):
        """Lo que se puede comprar: visible y sin vender (HU 08)."""
        return self.filter(visible=True, vendida=False)

    def galeria(self):
        """HU 08: piezas únicas que ya se vendieron."""
        return self.filter(visible=True, pieza_unica=True, vendida=True)


class Producto(models.Model):
    """Producto del catálogo al detal (HU 15)."""

    nombre = models.CharField("Nombre", max_length=150)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    categoria = models.ForeignKey(
        Categoria, on_delete=models.PROTECT, related_name="productos", verbose_name="Categoría"
    )
    descripcion = models.TextField("Descripción", blank=True)
    precio = models.DecimalField(
        "Precio", max_digits=10, decimal_places=0, validators=[MinValueValidator(0)]
    )
    # Ofertas con fecha de inicio y fin (HU 15)
    precio_oferta = models.DecimalField(
        "Precio de oferta", max_digits=10, decimal_places=0, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    oferta_inicio = models.DateField("Inicio de la oferta", null=True, blank=True)
    oferta_fin = models.DateField("Fin de la oferta", null=True, blank=True)
    # HU 02: instrucciones de cuidado del accesorio
    instrucciones_cuidado = models.TextField(
        "Instrucciones de cuidado", blank=True,
        help_text="Se muestran en la ficha del producto junto al aviso de cuidados general.",
    )
    # HU 03 y HU 19: datos que la diseñadora necesita para fabricar
    material = models.CharField("Material", max_length=150, blank=True,
                                help_text="Por ejemplo: alambre de cobre, mostacillas Miyuki, resina.")
    colores = models.CharField(
        "Colores disponibles", max_length=200, blank=True,
        help_text="Separados por coma, por ejemplo: Dorado, Plateado, Rosa. Déjelo vacío si es un solo color.",
    )
    # HU 01: técnica y tiempo de elaboración para organizar los pedidos
    tecnica = models.CharField("Técnica", max_length=100, blank=True,
                               help_text="Por ejemplo: alambrismo, resina, tejido Miyuki, macramé.")
    dias_elaboracion = models.PositiveSmallIntegerField(
        "Días de elaboración", default=3,
        help_text="Días hábiles que toma hacer la pieza. Se usa para la fecha límite del pedido.",
    )
    # HU 16: un producto puede estar en varias colecciones
    colecciones = models.ManyToManyField(Coleccion, blank=True, related_name="productos",
                                         verbose_name="Colecciones")
    # HU 08: piezas únicas que pasan a la galería cuando se venden
    pieza_unica = models.BooleanField(
        "Pieza única", default=False,
        help_text="Marque si solo existe una. Cuando se venda pasará sola a la Galería de piezas vendidas.",
    )
    vendida = models.BooleanField("Vendida", default=False)
    # HU 15: ocultar un producto agotado sin borrarlo
    visible = models.BooleanField(
        "Visible en la página", default=True,
        help_text="Desmárquelo para ocultar el producto (por ejemplo, si está agotado) sin borrarlo.",
    )
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    objects = ProductoQuerySet.as_manager()

    class Meta:
        ordering = ["-creado"]
        verbose_name = "producto"
        verbose_name_plural = "productos"

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _slug_unico(self, self.nombre)
        super().save(*args, **kwargs)

    def clean(self):
        if self.precio_oferta is not None:
            if not (self.oferta_inicio and self.oferta_fin):
                raise ValidationError("Para crear una oferta indique la fecha de inicio y la de fin.")
            if self.oferta_fin < self.oferta_inicio:
                raise ValidationError({"oferta_fin": "La fecha de fin no puede ser anterior a la de inicio."})
            if self.precio is not None and self.precio_oferta >= self.precio:
                raise ValidationError({"precio_oferta": "El precio de oferta debe ser menor al precio normal."})

    def get_absolute_url(self):
        return reverse("catalogo:detalle", args=[self.slug])

    @property
    def en_oferta(self):
        if self.precio_oferta is None or not self.oferta_inicio or not self.oferta_fin:
            return False
        hoy = timezone.localdate()
        return self.oferta_inicio <= hoy <= self.oferta_fin

    @property
    def precio_actual(self):
        return self.precio_oferta if self.en_oferta else self.precio

    @property
    def foto_principal(self):
        fotos = list(self.fotos.all())  # usa el prefetch si lo hay
        return fotos[0] if fotos else None

    @property
    def foto_secundaria(self):
        fotos = list(self.fotos.all())
        return fotos[1] if len(fotos) > 1 else None

    @property
    def lista_colores(self):
        return [c.strip() for c in self.colores.split(",") if c.strip()]

    @property
    def tallas_disponibles(self):
        """HU 19: solo las tallas marcadas como disponibles."""
        return [t for t in self.tallas.all() if t.disponible]

    @property
    def en_galeria(self):
        return self.pieza_unica and self.vendida

    @property
    def se_puede_comprar(self):
        return self.visible and not self.vendida


class FotoProducto(FotoOptimizadaMixin, models.Model):
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name="fotos")
    imagen = models.ImageField("Foto", upload_to="productos/")
    orden = models.PositiveIntegerField("Orden", default=0)

    class Meta:
        ordering = ["orden", "id"]
        verbose_name = "foto"
        verbose_name_plural = "fotos"

    def __str__(self):
        return f"Foto de {self.producto}"


class TallaProducto(models.Model):
    """HU 02: cada talla se registra con su nombre y su medida."""

    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name="tallas")
    # HU 19: admite tallas que no son estándar en el comercio (ej. XS o 13 cm)
    nombre = models.CharField("Talla", max_length=50, help_text="Por ejemplo: XS, S, M, 13 cm o Único.")
    medida = models.CharField("Medida", max_length=50, help_text="Por ejemplo: 16 cm o 45 cm de largo.")
    disponible = models.BooleanField("Disponible", default=True,
                                     help_text="Desmárquela si esa talla se agotó.")
    orden = models.PositiveIntegerField("Orden", default=0)

    class Meta:
        ordering = ["orden", "id"]
        verbose_name = "talla disponible"
        verbose_name_plural = "tallas disponibles"

    def __str__(self):
        return f"{self.nombre} ({self.medida})"
