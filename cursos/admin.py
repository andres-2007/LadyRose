from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from django.http import HttpResponse
from django.urls import reverse
from django.utils.html import format_html

from .excel import libro_inscritos

from .models import Curso, CursoAgotado, FotoCurso, Inscripcion


class FotoCursoFormSet(BaseInlineFormSet):
    """HU 13: un curso publicado debe tener al menos una foto."""

    def clean(self):
        super().clean()
        if not getattr(self.instance, "publicado", False):
            return
        fotos = 0
        for form in self.forms:
            datos = getattr(form, "cleaned_data", None) or {}
            if datos.get("DELETE"):
                continue
            if datos.get("imagen") or (form.instance.pk and form.instance.imagen):
                fotos += 1
        if fotos == 0:
            raise ValidationError("No se puede publicar el curso sin al menos una foto.")


class FotoCursoInline(admin.TabularInline):
    model = FotoCurso
    formset = FotoCursoFormSet
    extra = 1
    fields = ("imagen", "vista_previa", "orden")
    readonly_fields = ("vista_previa",)

    @admin.display(description="Vista previa")
    def vista_previa(self, obj):
        if obj.pk and obj.imagen:
            return format_html('<img src="{}" style="height:60px;border-radius:4px">', obj.imagen.url)
        return "-"


class InscripcionInline(admin.TabularInline):
    """HU 26 CA 2 y 3: inscritos del curso con su estado de pago, que la dueña cambia a mano."""

    model = Inscripcion
    extra = 0
    fields = ("nombre", "whatsapp", "correo", "modalidad", "estado_pago", "fecha", "enlace_enviado")
    readonly_fields = ("fecha", "enlace_enviado")


def _respuesta_excel(cursos, nombre):
    respuesta = HttpResponse(
        libro_inscritos(cursos),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}.xlsx"'
    return respuesta


@admin.register(Curso)
class CursoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "fecha", "modalidad", "tipo_clase", "cupos_maximos",
                    "inscritos", "cupos_libres", "publicado", "excel")
    list_filter = ("publicado", "modalidad", "tipo_clase")
    search_fields = ("nombre", "tecnica")
    exclude = ("slug",)
    readonly_fields = ("resumen_cupos", "excel")
    inlines = [FotoCursoInline, InscripcionInline]
    actions = ["descargar_excel"]
    fieldsets = (
        (None, {"fields": ("nombre", "descripcion", "tecnica", "materiales_incluidos")}),
        ("Fecha y modalidad", {"fields": ("modalidad", "tipo_clase", "fecha", "horario", "enlace_conexion")}),
        ("Precio y cupos", {"fields": ("precio", "cupos_maximos", "resumen_cupos", "excel")}),
        ("Publicación", {"fields": ("publicado",)}),
    )

    @admin.display(description="Inscritos")
    def inscritos(self, obj):
        return obj.inscripciones.count()

    @admin.display(description="Cupos")
    def resumen_cupos(self, obj):
        if not obj.pk:
            return "-"
        return f"{obj.inscritos_pagados} pagados de {obj.cupos_maximos}. Quedan {obj.cupos_disponibles}."

    @admin.display(description="Lista en Excel")
    def excel(self, obj):
        if not obj.pk:
            return "-"
        return format_html('<a href="{}">Descargar</a>', reverse("cursos:inscritos_excel", args=[obj.pk]))

    @admin.action(description="Descargar en Excel los inscritos de los cursos seleccionados")
    def descargar_excel(self, request, queryset):
        return _respuesta_excel(list(queryset), "inscritos-ladyrose")

    @admin.display(description="Cupos disponibles")
    def cupos_libres(self, obj):
        return "Agotado" if obj.agotado else obj.cupos_disponibles


@admin.register(Inscripcion)
class InscripcionAdmin(admin.ModelAdmin):
    list_display = ("nombre", "curso", "modalidad", "whatsapp", "correo", "estado_pago", "fecha", "enlace_enviado")
    list_editable = ("estado_pago",)
    list_filter = ("estado_pago", "curso", "modalidad")
    search_fields = ("nombre", "correo", "whatsapp")
    actions = ["confirmar_pagos"]

    @admin.action(description="Confirmar el pago de las inscripciones seleccionadas", permissions=["change"])
    def confirmar_pagos(self, request, queryset):
        confirmadas = 0
        for inscripcion in queryset:
            try:
                inscripcion.confirmar_pago()
                confirmadas += 1
            except CursoAgotado:
                self.message_user(
                    request,
                    f"No se pudo confirmar a {inscripcion.nombre}: el curso {inscripcion.curso} ya no tiene cupos.",
                    level=messages.ERROR,
                )
        if confirmadas:
            self.message_user(request, f"Se confirmaron {confirmadas} pagos.")
