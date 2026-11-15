"""HU 28: seguimiento de clientes potenciales.

Cada pregunta o solicitud de cotización que llega por la página queda como una
Consulta, con su estado, para que la dueña la responda a tiempo y la lleve
hasta la compra.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.festivos import fin_horas_habiles

HORAS_RESPUESTA = 24  # HU 28 CA 3: horas hábiles para responder antes de resaltarla


def solo_digitos(numero):
    """Los últimos 10 dígitos del número (sin +57, espacios ni guiones)."""
    return "".join(c for c in (numero or "") if c.isdigit())[-10:]


class Consulta(models.Model):
    class Origen(models.TextChoices):
        COTIZACION = "cotizacion", "Solicitud de cotización"
        PRODUCTO = "producto", "Pregunta por un producto"
        CURSO = "curso", "Pregunta por un curso"

    class Estado(models.TextChoices):
        NUEVA = "nueva", "Nueva"
        CONTACTADA = "contactada", "Contactada"
        COMPRO = "compro", "Compró"
        DESCARTADA = "descartada", "Descartada"

    origen = models.CharField("Origen", max_length=20, choices=Origen.choices)
    # HU 28 CA 1: nombre, medio de contacto, producto o curso de interés y fecha
    nombre = models.CharField("Nombre", max_length=150)
    whatsapp = models.CharField("WhatsApp", max_length=20, blank=True)
    correo = models.EmailField("Correo", blank=True)
    mensaje = models.TextField("Mensaje", blank=True)
    producto = models.ForeignKey("catalogo.Producto", on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="consultas", verbose_name="Producto de interés")
    curso = models.ForeignKey("cursos.Curso", on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="consultas", verbose_name="Curso de interés")
    cotizacion = models.OneToOneField("cotizaciones.SolicitudCotizacion", on_delete=models.CASCADE, null=True,
                                      blank=True, related_name="consulta", verbose_name="Solicitud de cotización")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="consultas", verbose_name="Cuenta del cliente")
    fecha = models.DateTimeField("Fecha", default=timezone.now)

    # HU 28 CA 2: estado de la consulta
    estado = models.CharField("Estado", max_length=20, choices=Estado.choices, default=Estado.NUEVA)
    contactada_en = models.DateTimeField("Contactada el", null=True, blank=True)
    compro_en = models.DateTimeField("Compró el", null=True, blank=True)
    pedido = models.ForeignKey("pedidos.Pedido", on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="consultas", verbose_name="Pedido con el que compró")

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "consulta"
        verbose_name_plural = "consultas"

    def __str__(self):
        return f"{self.nombre}: {self.interes}"

    @property
    def interes(self):
        """Producto o curso por el que preguntó."""
        if self.producto_id:
            return self.producto.nombre
        if self.curso_id:
            return self.curso.nombre
        if self.cotizacion_id:
            return self.cotizacion.get_tipo_display()
        return "Consulta general"

    @property
    def interes_mensaje(self):
        """Cómo se nombra el interés en el mensaje de WhatsApp (HU 28 CA 4)."""
        if self.producto_id:
            return f"el producto {self.producto.nombre}"
        if self.curso_id:
            return f"el curso {self.curso.nombre}"
        if self.cotizacion_id:
            return "la pieza personalizada que nos pediste cotizar"
        return "tu consulta"

    @property
    def whatsapp_internacional(self):
        numero = "".join(c for c in self.whatsapp if c.isdigit())
        if len(numero) == 10 and numero.startswith("3"):
            numero = "57" + numero
        return numero

    # ----- HU 28 CA 3: más de 24 horas hábiles sin respuesta -----
    @property
    def limite_respuesta(self):
        return fin_horas_habiles(self.fecha, HORAS_RESPUESTA)

    def sin_respuesta(self, ahora=None):
        return self.estado == self.Estado.NUEVA and (ahora or timezone.now()) >= self.limite_respuesta

    # ----- Cambios de estado -----
    def cambiar_estado(self, estado, pedido=None):
        self.estado = estado
        ahora = timezone.now()
        if estado == self.Estado.CONTACTADA and not self.contactada_en:
            self.contactada_en = ahora
        if estado == self.Estado.COMPRO:
            self.compro_en = self.compro_en or ahora
            self.pedido = pedido or self.pedido
        self.save()

    def mensaje_whatsapp(self):
        """HU 28 CA 4: mensaje que menciona el producto que le interesó."""
        nombre = self.nombre.split()[0] if self.nombre else ""
        return (
            f"¡Hola {nombre}! Te escribimos de Ladyrose por tu consulta sobre {self.interes_mensaje}. "
            "¿Te podemos ayudar con algo más para que te lo llevemos?"
        )

    # ----- Búsqueda de la misma persona -----
    @classmethod
    def de_la_persona(cls, usuario=None, correo="", numeros=()):
        """Consultas abiertas (Nueva o Contactada) de la misma persona: misma cuenta, correo o WhatsApp."""
        filtro = Q()
        if usuario is not None and getattr(usuario, "pk", None):
            filtro |= Q(usuario=usuario)
        if correo:
            filtro |= Q(correo__iexact=correo)
        digitos = {solo_digitos(n) for n in numeros if len(solo_digitos(n)) >= 7}
        abiertas = cls.objects.filter(estado__in=[cls.Estado.NUEVA, cls.Estado.CONTACTADA])
        if digitos:
            # El WhatsApp se guarda como lo escribió el cliente, así que se compara en Python
            por_numero = [c.pk for c in abiertas.exclude(whatsapp="") if solo_digitos(c.whatsapp) in digitos]
            filtro |= Q(pk__in=por_numero)
        if not filtro:
            return cls.objects.none()
        return abiertas.filter(filtro)


def registrar_cotizacion(solicitud):
    """HU 28 CA 1: cada solicitud de cotización queda registrada como consulta."""
    return Consulta.objects.create(
        origen=Consulta.Origen.COTIZACION, cotizacion=solicitud, producto=solicitud.producto,
        nombre=solicitud.nombre, whatsapp=solicitud.whatsapp, correo=solicitud.correo,
        mensaje=solicitud.descripcion or solicitud.motivo, fecha=solicitud.fecha or timezone.now(),
    )
