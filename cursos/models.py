from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone

from catalogo.models import _slug_unico
from core.imagenes import FotoOptimizadaMixin


class CursoAgotado(Exception):
    """Se lanza cuando ya no quedan cupos para confirmar una inscripción."""


class CursoQuerySet(models.QuerySet):
    def publicados(self):
        return self.filter(publicado=True)


class Curso(models.Model):
    """HU 13 (información del curso) y HU 21 (control de cupos)."""

    class Modalidad(models.TextChoices):
        PRESENCIAL = "presencial", "Presencial"
        VIRTUAL = "virtual", "Virtual"
        AMBAS = "ambas", "Presencial o virtual"

    class TipoClase(models.TextChoices):
        INDIVIDUAL = "individual", "Individual"
        GRUPAL = "grupal", "Grupal"

    nombre = models.CharField("Nombre del curso", max_length=150)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    descripcion = models.TextField("Descripción", blank=True)
    tecnica = models.CharField("Técnica principal", max_length=100, blank=True,
                               help_text="Por ejemplo: tejido Miyuki, engarce, macramé.")
    materiales_incluidos = models.TextField("Materiales incluidos", blank=True)
    modalidad = models.CharField("Modalidad", max_length=20, choices=Modalidad.choices, blank=True)
    tipo_clase = models.CharField("Tipo de curso", max_length=20, choices=TipoClase.choices, blank=True)
    fecha = models.DateField("Fecha", null=True, blank=True)
    horario = models.CharField("Horario", max_length=100, blank=True,
                               help_text="Por ejemplo: 9:00 a.m. a 12:00 m.")
    precio = models.DecimalField("Precio total", max_digits=10, decimal_places=0, null=True, blank=True,
                                 validators=[MinValueValidator(0)])
    # HU 26: enlace que se envía a los inscritos de cursos virtuales cuando pagan
    enlace_conexion = models.URLField(
        "Enlace de conexión", blank=True,
        help_text="Para cursos virtuales (Meet, Zoom...). Se envía solo cuando la inscripción pasa a Pagado.",
    )
    # HU 21: campo numérico obligatorio
    cupos_maximos = models.PositiveIntegerField(
        "Cupos máximos", validators=[MinValueValidator(1, message="Debe haber al menos un cupo.")]
    )
    publicado = models.BooleanField(
        "Publicado", default=False,
        help_text="Solo se puede publicar si tiene todos los datos obligatorios y al menos una foto.",
    )
    creado = models.DateTimeField(auto_now_add=True)

    objects = CursoQuerySet.as_manager()

    CAMPOS_OBLIGATORIOS = ("tecnica", "materiales_incluidos", "modalidad", "tipo_clase",
                           "fecha", "horario", "precio")

    class Meta:
        ordering = ["fecha", "nombre"]
        verbose_name = "curso"
        verbose_name_plural = "cursos"

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _slug_unico(self, self.nombre)
        super().save(*args, **kwargs)

    def campos_faltantes(self):
        return [
            self._meta.get_field(c).verbose_name
            for c in self.CAMPOS_OBLIGATORIOS
            if getattr(self, c) in (None, "")
        ]

    def clean(self):
        # HU 13: no se puede publicar un curso con datos obligatorios vacíos.
        # (La validación de la foto se hace en el panel, ver cursos/admin.py.)
        if self.publicado:
            faltan = self.campos_faltantes()
            if faltan:
                raise ValidationError(
                    "No se puede publicar el curso. Faltan estos datos: " + ", ".join(faltan) + "."
                )

    def get_absolute_url(self):
        return reverse("cursos:detalle", args=[self.slug])

    # ----- HU 21: control de cupos -----
    @property
    def inscritos_pagados(self):
        return self.inscripciones.filter(estado_pago=Inscripcion.EstadoPago.PAGADO).count()

    @property
    def cupos_disponibles(self):
        return max(self.cupos_maximos - self.inscritos_pagados, 0)

    @property
    def agotado(self):
        return self.cupos_disponibles == 0

    @property
    def modalidades_permitidas(self):
        if self.modalidad == self.Modalidad.AMBAS:
            return [self.Modalidad.PRESENCIAL, self.Modalidad.VIRTUAL]
        return [self.modalidad] if self.modalidad else []


class FotoCurso(FotoOptimizadaMixin, models.Model):
    """HU 13: galería con fotos del accesorio que se aprende a hacer."""

    curso = models.ForeignKey(Curso, on_delete=models.CASCADE, related_name="fotos")
    imagen = models.ImageField("Foto", upload_to="cursos/")
    orden = models.PositiveIntegerField("Orden", default=0)

    class Meta:
        ordering = ["orden", "id"]
        verbose_name = "foto del curso"
        verbose_name_plural = "fotos del curso"

    def __str__(self):
        return f"Foto de {self.curso}"


class Inscripcion(models.Model):
    """HU 21 y HU 26: inscripción de una persona a un curso."""

    class EstadoPago(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        PAGADO = "pagado", "Pagado"

    class Modalidad(models.TextChoices):
        PRESENCIAL = "presencial", "Presencial"
        VIRTUAL = "virtual", "Virtual"

    curso = models.ForeignKey(Curso, on_delete=models.CASCADE, related_name="inscripciones")
    nombre = models.CharField("Nombre completo", max_length=150)
    whatsapp = models.CharField("WhatsApp", max_length=20)
    correo = models.EmailField("Correo electrónico")
    modalidad = models.CharField("Modalidad", max_length=20, choices=Modalidad.choices, blank=True)
    estado_pago = models.CharField("Estado de pago", max_length=20, choices=EstadoPago.choices,
                                   default=EstadoPago.PENDIENTE)
    fecha = models.DateTimeField("Fecha de inscripción", auto_now_add=True)
    enlace_enviado = models.DateTimeField("Enlace enviado", null=True, blank=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "inscripción"
        verbose_name_plural = "inscripciones"

    def __str__(self):
        return f"{self.nombre} - {self.curso}"

    def clean(self):
        # Si se marca como pagada desde el panel, se revisa que todavía haya cupo.
        if self.estado_pago == self.EstadoPago.PAGADO and self.curso_id:
            ya_pagada = (self.pk and Inscripcion.objects.filter(
                pk=self.pk, estado_pago=self.EstadoPago.PAGADO).exists())
            if not ya_pagada and self.curso.agotado:
                raise ValidationError("El curso ya no tiene cupos disponibles.")

    def save(self, *args, **kwargs):
        if not self.modalidad and self.curso_id and self.curso.modalidad != Curso.Modalidad.AMBAS:
            self.modalidad = self.curso.modalidad
        antes = None
        if self.pk:
            antes = Inscripcion.objects.filter(pk=self.pk).values_list("estado_pago", flat=True).first()
        super().save(*args, **kwargs)
        if self.estado_pago == self.EstadoPago.PAGADO and antes != self.EstadoPago.PAGADO:
            self.enviar_enlace()

    def enviar_enlace(self):
        """HU 26 CA 5: en los cursos virtuales se envía el enlace al confirmar el pago."""
        if self.modalidad != self.Modalidad.VIRTUAL or not self.curso.enlace_conexion or self.enlace_enviado:
            return False
        fecha = self.curso.fecha.strftime("%d/%m/%Y") if self.curso.fecha else ""
        send_mail(
            f"Tu enlace para el curso {self.curso.nombre}",
            f"Hola {self.nombre.split()[0]},\n\n"
            f"Ya confirmamos tu pago. Este es el enlace para conectarte al curso "
            f"{self.curso.nombre} el {fecha} ({self.curso.horario}):\n\n"
            f"{self.curso.enlace_conexion}\n\n"
            "Nos vemos en clase.\nLadyrose",
            None, [self.correo],
        )
        self.enlace_enviado = timezone.now()
        Inscripcion.objects.filter(pk=self.pk).update(enlace_enviado=self.enlace_enviado)
        return True

    def confirmar_pago(self):
        """Confirma el pago y descuenta un cupo.

        Se bloquea el registro del curso mientras se cuenta, para que dos
        confirmaciones al mismo tiempo no tomen el último cupo dos veces.
        """
        with transaction.atomic():
            curso = Curso.objects.select_for_update().get(pk=self.curso_id)
            if self.estado_pago == self.EstadoPago.PAGADO:
                return
            if curso.agotado:
                raise CursoAgotado("El curso ya no tiene cupos disponibles.")
            self.estado_pago = self.EstadoPago.PAGADO
            self.save(update_fields=["estado_pago"])
