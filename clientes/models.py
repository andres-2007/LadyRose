"""HU 27: cuentas de cliente y códigos de descuento personalizados.

La cuenta usa el usuario de Django (el correo es el nombre de usuario) y el
modelo Cliente guarda lo que es propio de Ladyrose: el WhatsApp y el
cumpleaños, ambos opcionales.
"""
import secrets
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

DIAS_CUMPLEANOS = 7  # HU 27 CA 4: cumpleaños en los próximos 7 días
LETRAS_CODIGO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O ni 1/I para que no se confundan


def proximo_cumpleanos(cumpleanos, hoy):
    """Fecha del próximo cumpleaños (hoy incluido). El 29 de febrero se celebra el 28 en años no bisiestos."""
    for anio in (hoy.year, hoy.year + 1):
        try:
            fecha = cumpleanos.replace(year=anio)
        except ValueError:
            fecha = date(anio, 2, 28)
        if fecha >= hoy:
            return fecha
    return None


class Cliente(models.Model):
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cliente")
    whatsapp = models.CharField("WhatsApp", max_length=20, blank=True)
    cumpleanos = models.DateField("Fecha de cumpleaños", null=True, blank=True)
    creado = models.DateTimeField("Registrado el", auto_now_add=True)

    class Meta:
        ordering = ["usuario__first_name"]
        verbose_name = "cliente"
        verbose_name_plural = "clientes"

    def __str__(self):
        return f"{self.nombre} ({self.correo})"

    @property
    def nombre(self):
        return self.usuario.first_name or self.usuario.email

    @property
    def primer_nombre(self):
        return self.nombre.split()[0] if self.nombre else ""

    @property
    def correo(self):
        return self.usuario.email

    # ----- HU 27 CA 5: compras del cliente -----
    def pedidos(self):
        """Pedidos hechos con la cuenta y, además, los que hizo antes como invitado con el mismo correo."""
        from pedidos.models import Pedido

        filtro = Q(cliente=self.usuario)
        if self.correo:
            filtro |= Q(correo__iexact=self.correo)
        return Pedido.objects.filter(filtro)

    @property
    def ya_compro(self):
        return self.pedidos().exists()

    @property
    def whatsapp_contacto(self):
        """HU 27: el del registro y, si no lo dejó, el de su último pedido."""
        if self.whatsapp:
            return self.whatsapp
        ultimo = self.pedidos().order_by("-creado").first()
        return (ultimo.whatsapp or ultimo.telefono) if ultimo else ""

    @property
    def whatsapp_internacional(self):
        numero = "".join(c for c in self.whatsapp_contacto if c.isdigit())
        if len(numero) == 10 and numero.startswith("3"):
            numero = "57" + numero
        return numero

    # ----- HU 27 CA 4: cumpleaños -----
    def dias_para_cumpleanos(self, hoy=None):
        if not self.cumpleanos:
            return None
        hoy = hoy or timezone.localdate()
        return (proximo_cumpleanos(self.cumpleanos, hoy) - hoy).days

    def cumple_pronto(self, hoy=None):
        dias = self.dias_para_cumpleanos(hoy)
        return dias is not None and dias <= DIAS_CUMPLEANOS

    def codigos_disponibles(self, hoy=None):
        hoy = hoy or timezone.localdate()
        return self.codigos.filter(usado_en__isnull=True, vence__gte=hoy)


class CodigoInvalido(Exception):
    """El código no se puede usar; el mensaje explica por qué."""


class CodigoDescuento(models.Model):
    class Tipo(models.TextChoices):
        PORCENTAJE = "porcentaje", "Porcentaje (%)"
        VALOR = "valor", "Valor en pesos"

    class Motivo(models.TextChoices):
        CUMPLEANOS = "cumpleanos", "Cumpleaños"
        GRACIAS = "gracias", "Ya nos compró"
        OTRO = "otro", "Otro"

    codigo = models.CharField(
        "Código", max_length=30, unique=True, blank=True,
        help_text="Es lo que el cliente escribe al pagar. Se propone uno automáticamente; puede cambiarlo. "
                  "Si lo deja vacío se genera al guardar.",
    )
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="codigos", verbose_name="Cliente")
    motivo = models.CharField("Motivo", max_length=20, choices=Motivo.choices, default=Motivo.OTRO,
                              help_text="Se usa para el mensaje que recibe el cliente.")
    tipo = models.CharField("Tipo de descuento", max_length=20, choices=Tipo.choices, default=Tipo.PORCENTAJE)
    valor = models.DecimalField(
        "Descuento", max_digits=10, decimal_places=0, validators=[MinValueValidator(1)],
        help_text="Porcentaje (ej. 10) o valor en pesos (ej. 5000), según el tipo.",
    )
    vence = models.DateField("Válido hasta", help_text="El código se puede usar hasta este día, inclusive.")
    creado = models.DateTimeField("Creado el", auto_now_add=True)
    usado_en = models.DateTimeField("Usado el", null=True, blank=True, editable=False)
    enviado_en = models.DateTimeField("Enviado el", null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-creado"]
        verbose_name = "código de descuento"
        verbose_name_plural = "códigos de descuento"

    def __str__(self):
        return self.codigo

    # ----- Creación -----
    @classmethod
    def proponer_codigo(cls, cliente=None, motivo=None):
        """HU 27: código automático, por ejemplo CUMPLE-PAULA-7K3Q."""
        prefijo = {cls.Motivo.CUMPLEANOS: "CUMPLE", cls.Motivo.GRACIAS: "GRACIAS"}.get(motivo, "LR")
        partes = [prefijo]
        if cliente:
            nombre = slugify(cliente.primer_nombre).upper().replace("-", "")[:10]
            if nombre:
                partes.append(nombre)
        while True:
            codigo = "-".join(partes + ["".join(secrets.choice(LETRAS_CODIGO) for _ in range(4))])
            if not cls.objects.filter(codigo=codigo).exists():
                return codigo

    def clean(self):
        self.codigo = (self.codigo or "").strip().upper().replace(" ", "")
        if self.tipo == self.Tipo.PORCENTAJE and self.valor and self.valor > 100:
            raise ValidationError({"valor": "El porcentaje no puede ser mayor a 100."})
        if self.vence and not self.pk and self.vence < timezone.localdate():
            raise ValidationError({"vence": "La fecha de vencimiento no puede estar en el pasado."})
        if self.codigo and CodigoDescuento.objects.filter(codigo=self.codigo).exclude(pk=self.pk).exists():
            raise ValidationError({"codigo": "Ya existe un código igual. Escriba otro."})

    def save(self, *args, **kwargs):
        self.codigo = (self.codigo or "").strip().upper().replace(" ", "")
        if not self.codigo:
            self.codigo = self.proponer_codigo(self.cliente, self.motivo)
        super().save(*args, **kwargs)

    # ----- Estado -----
    @property
    def usado(self):
        return self.usado_en is not None

    def vencido(self, hoy=None):
        return self.vence < (hoy or timezone.localdate())

    @property
    def estado(self):
        if self.usado:
            return "Usado"
        if self.vencido():
            return "Vencido"
        return "Disponible"

    @property
    def descuento_texto(self):
        if self.tipo == self.Tipo.PORCENTAJE:
            return f"{self.valor:.0f}% de descuento"
        return "$" + f"{self.valor:,.0f}".replace(",", ".") + " de descuento"

    # ----- HU 27 CA 2: validación al pagar -----
    def validar_para(self, usuario, hoy=None):
        """Lanza CodigoInvalido si el código no se puede usar con esa cuenta."""
        cliente = getattr(usuario, "cliente", None) if usuario and usuario.is_authenticated else None
        if cliente is None or cliente.pk != self.cliente_id:
            raise CodigoInvalido("Este código no está asignado a tu cuenta.")
        if self.usado:
            raise CodigoInvalido("Este código ya fue usado.")
        if self.vencido(hoy):
            raise CodigoInvalido(f"Este código venció el {self.vence:%d/%m/%Y}.")

    def calcular(self, subtotal):
        """Valor a descontar sobre el subtotal de productos (nunca más que el subtotal)."""
        subtotal = Decimal(subtotal)
        if self.tipo == self.Tipo.PORCENTAJE:
            descuento = (subtotal * self.valor / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        else:
            descuento = Decimal(self.valor)
        return min(descuento, subtotal)

    @classmethod
    def buscar(cls, texto, usuario, hoy=None):
        """Busca el código que escribió el cliente y lo valida para su cuenta."""
        texto = (texto or "").strip().upper().replace(" ", "")
        if not texto:
            raise CodigoInvalido("Escribe el código de descuento.")
        codigo = cls.objects.filter(codigo=texto).select_related("cliente").first()
        if codigo is None:
            raise CodigoInvalido("Ese código no existe. Revisa que esté bien escrito.")
        codigo.validar_para(usuario, hoy)
        return codigo

    # ----- HU 27 CA 4: mensaje para el cliente -----
    def mensaje(self, url_tienda=""):
        nombre = self.cliente.primer_nombre
        if self.motivo == self.Motivo.CUMPLEANOS:
            saludo = f"¡Hola {nombre}! En Ladyrose queremos celebrar tu cumpleaños contigo."
        elif self.motivo == self.Motivo.GRACIAS:
            saludo = f"¡Hola {nombre}! Gracias por confiar en Ladyrose; queremos consentirte en tu próxima compra."
        else:
            saludo = f"¡Hola {nombre}! En Ladyrose tenemos un regalo para ti."
        partes = [
            saludo,
            f"Usa el código {self.codigo} y obtén {self.descuento_texto} en tus productos.",
            f"Es válido hasta el {self.vence:%d/%m/%Y} y funciona solo con tu cuenta.",
        ]
        if url_tienda:
            partes.append(f"Entra a {url_tienda} e inicia sesión para usarlo.")
        partes.append("Con cariño, Ladyrose. Todo es posible.")
        return "\n\n".join(partes)
