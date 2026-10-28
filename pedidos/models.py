"""Pedidos de la tienda (Sprint 2).

HU 24: datos completos para el despacho.
HU 11: empaque de regalo, nota y envío a otra persona.
HU 01, 03, 04 y 10: panel de producción de la diseñadora de accesorios.
"""
from datetime import timedelta

from django.core.validators import MaxLengthValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from catalogo.models import Producto
from core.models import VisitaOrigen
from cotizaciones.models import SolicitudCotizacion

MAX_NOTA = 200


def sumar_dias_habiles(fecha, dias):
    """Suma días de lunes a viernes (la fecha límite no cae en fin de semana)."""
    while dias > 0:
        fecha += timedelta(days=1)
        if fecha.weekday() < 5:
            dias -= 1
    return fecha


class TipoEmpaque(models.Model):
    """HU 11: empaques de regalo que la dueña administra desde el panel."""

    nombre = models.CharField("Nombre", max_length=100)
    descripcion = models.CharField("Descripción", max_length=200, blank=True)
    costo = models.DecimalField("Costo adicional", max_digits=10, decimal_places=0, default=0,
                                validators=[MinValueValidator(0)])
    activo = models.BooleanField("Disponible", default=True)
    orden = models.PositiveIntegerField("Orden", default=0)

    class Meta:
        ordering = ["orden", "costo"]
        verbose_name = "tipo de empaque"
        verbose_name_plural = "tipos de empaque"

    def __str__(self):
        return self.nombre


class Pedido(models.Model):
    class EstadoProduccion(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        EN_CURSO = "en_curso", "En curso"
        # HU 10: el pedido queda en pausa mientras el cliente responde
        EN_PAUSA = "en_pausa", "En pausa - Esperando respuesta del cliente"
        TERMINADO = "terminado", "Terminado"

    class EstadoEnvio(models.TextChoices):
        POR_DESPACHAR = "por_despachar", "Por despachar"
        DESPACHADO = "despachado", "Despachado"
        ENTREGADO = "entregado", "Entregado"

    class MetodoPago(models.TextChoices):
        CONTRA_ENTREGA = "contra_entrega", "Pago contra entrega"
        TRANSFERENCIA = "transferencia", "Transferencia antes del envío"

    class EstadoPago(models.TextChoices):
        PENDIENTE = "pendiente", "Por verificar"
        VERIFICADO = "verificado", "Verificado"

    creado = models.DateTimeField("Fecha del pedido", default=timezone.now)

    # ----- Quien compra -----
    nombre = models.CharField("Nombre completo", max_length=150)
    correo = models.EmailField("Correo electrónico", blank=True)
    telefono = models.CharField("Teléfono para llamadas", max_length=20)
    whatsapp = models.CharField("WhatsApp", max_length=20, blank=True)
    whatsapp_igual = models.BooleanField("Es el mismo número de llamadas", default=True)

    # ----- Entrega (HU 24) -----
    enviar_a_otra_persona = models.BooleanField("Enviar a otra persona", default=False)
    nombre_recibe = models.CharField("Nombre de quien recibe", max_length=150)
    telefono_recibe = models.CharField("Teléfono de quien recibe", max_length=20)
    direccion = models.CharField("Dirección", max_length=200)
    barrio = models.CharField("Barrio", max_length=100)
    ciudad = models.CharField("Ciudad", max_length=100)
    indicaciones = models.CharField("Indicaciones de entrega", max_length=200, blank=True,
                                    help_text="Apartamento, torre, portería o un punto de referencia.")

    # ----- Regalo (HU 11) -----
    empaque = models.ForeignKey(TipoEmpaque, on_delete=models.SET_NULL, null=True, blank=True,
                                verbose_name="Empaque de regalo")
    costo_empaque = models.DecimalField("Costo del empaque", max_digits=10, decimal_places=0, default=0)
    nota = models.TextField("Nota personalizada", blank=True, max_length=MAX_NOTA,
                            validators=[MaxLengthValidator(MAX_NOTA)])
    # HU 03: historia o motivo de la pieza (o el de la cotización)
    motivo = models.TextField("Historia o motivo", blank=True)
    cotizacion = models.ForeignKey(
        SolicitudCotizacion, on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos",
        verbose_name="Cotización de origen",
        help_text="Si el pedido es una pieza personalizada, elija la solicitud de cotización.",
    )

    # ----- Pago (HU 24) -----
    metodo_pago = models.CharField("Forma de pago", max_length=20, choices=MetodoPago.choices)
    comprobante = models.FileField("Comprobante de transferencia", upload_to="comprobantes/", blank=True)
    estado_pago = models.CharField("Estado del pago", max_length=20, choices=EstadoPago.choices,
                                   default=EstadoPago.PENDIENTE)
    subtotal = models.DecimalField("Subtotal", max_digits=12, decimal_places=0, default=0)
    total = models.DecimalField("Total", max_digits=12, decimal_places=0, default=0)

    # ----- Producción (HU 01, 04 y 10) -----
    tecnica = models.CharField("Técnica a emplear", max_length=150, blank=True)
    dias_elaboracion = models.PositiveSmallIntegerField("Días de elaboración", default=3)
    fecha_limite = models.DateField("Fecha límite de entrega", null=True, blank=True)
    estado_produccion = models.CharField("Estado de producción", max_length=20,
                                         choices=EstadoProduccion.choices, default=EstadoProduccion.PENDIENTE)
    estado_actualizado = models.DateTimeField("Último cambio de estado", null=True, blank=True)
    estado_envio = models.CharField("Envío", max_length=20, choices=EstadoEnvio.choices,
                                    default=EstadoEnvio.POR_DESPACHAR)

    # HU 31: red social desde la que llegó la persona que compró
    canal_origen = models.CharField("Canal de origen", max_length=20, choices=VisitaOrigen.Canal.choices,
                                    blank=True)

    class Meta:
        ordering = ["-creado"]
        verbose_name = "pedido"
        verbose_name_plural = "pedidos"

    def __str__(self):
        return f"Pedido {self.numero}"

    @property
    def numero(self):
        return f"LR-{self.pk:04d}" if self.pk else "Nuevo"

    def get_absolute_url(self):
        return reverse("pedidos:panel_detalle", args=[self.pk])

    def save(self, *args, **kwargs):
        if not self.fecha_limite:
            self.fecha_limite = sumar_dias_habiles(timezone.localdate(), self.dias_elaboracion or 3)
        if not self.enviar_a_otra_persona:
            self.nombre_recibe = self.nombre_recibe or self.nombre
            self.telefono_recibe = self.telefono_recibe or self.telefono
        if self.whatsapp_igual:
            self.whatsapp = self.telefono
        super().save(*args, **kwargs)

    # ----- HU 01 -----
    @property
    def pendiente_de_produccion(self):
        return self.estado_produccion != self.EstadoProduccion.TERMINADO

    @property
    def primer_detalle(self):
        detalles = list(self.detalles.all())
        return detalles[0] if detalles else None

    @property
    def nombre_accesorio(self):
        detalles = list(self.detalles.all())
        if not detalles:
            return "Pieza personalizada" if self.cotizacion_id else "Pedido"
        nombre = detalles[0].referencia
        return nombre + (f" y {len(detalles) - 1} más" if len(detalles) > 1 else "")

    @property
    def foto(self):
        detalle = self.primer_detalle
        if detalle and detalle.producto:
            foto = detalle.producto.foto_principal
            if foto:
                return foto.imagen
        if self.cotizacion_id:
            imagen = self.cotizacion.imagenes.first()
            if imagen:
                return imagen.imagen
        return None

    @property
    def dias_restantes(self):
        if not self.fecha_limite:
            return None
        return (self.fecha_limite - timezone.localdate()).days

    @property
    def tiene_regalo(self):
        return bool(self.empaque_id or self.nota.strip())

    @property
    def whatsapp_internacional(self):
        numero = "".join(c for c in (self.whatsapp or self.telefono) if c.isdigit())
        if len(numero) == 10 and numero.startswith("3"):
            numero = "57" + numero
        return numero

    def cambiar_estado(self, estado):
        self.estado_produccion = estado
        self.estado_actualizado = timezone.now()
        self.save(update_fields=["estado_produccion", "estado_actualizado"])

    def calcular_produccion(self):
        """Técnica y fecha límite a partir de los productos del pedido."""
        productos = [d.producto for d in self.detalles.select_related("producto") if d.producto]
        tecnicas = []
        for p in productos:
            if p.tecnica and p.tecnica not in tecnicas:
                tecnicas.append(p.tecnica)
        self.tecnica = ", ".join(tecnicas)
        self.dias_elaboracion = max([p.dias_elaboracion for p in productos] or [3])
        self.fecha_limite = sumar_dias_habiles(timezone.localdate(self.creado), self.dias_elaboracion)


class DetallePedido(models.Model):
    """HU 24: detalle exacto de cada producto (referencia, talla, color y cantidad)."""

    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="detalles")
    producto = models.ForeignKey(Producto, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="ventas")
    referencia = models.CharField("Referencia", max_length=150)
    talla = models.CharField("Talla", max_length=100, blank=True)
    color = models.CharField("Color", max_length=60, blank=True)
    material = models.CharField("Material", max_length=150, blank=True)
    cantidad = models.PositiveIntegerField("Cantidad", default=1, validators=[MinValueValidator(1)])
    precio_unitario = models.DecimalField("Precio unitario", max_digits=10, decimal_places=0)

    class Meta:
        verbose_name = "producto del pedido"
        verbose_name_plural = "productos del pedido"

    def __str__(self):
        return f"{self.cantidad} x {self.referencia}"

    @property
    def subtotal(self):
        return self.precio_unitario * self.cantidad
