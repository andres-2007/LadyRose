"""HU 28: panel de seguimiento de clientes potenciales (solo la dueña)."""
from urllib.parse import quote

from django.contrib import admin, messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html


from .models import HORAS_RESPUESTA, Consulta


def resumen_del_mes(hoy=None):
    """HU 28 CA 5: de las consultas que llegaron este mes, cuántas terminaron en compra."""
    hoy = hoy or timezone.localdate()
    del_mes = Consulta.objects.filter(fecha__year=hoy.year, fecha__month=hoy.month)
    total = del_mes.count()
    compraron = del_mes.filter(estado=Consulta.Estado.COMPRO).count()
    return {"total": total, "compraron": compraron,
            "porcentaje": round(compraron * 100 / total) if total else 0}


def ids_sin_respuesta(ahora=None):
    ahora = ahora or timezone.now()
    return [c.pk for c in Consulta.objects.filter(estado=Consulta.Estado.NUEVA) if c.sin_respuesta(ahora)]


class SinRespuestaFiltro(admin.SimpleListFilter):
    title = "tiempo de respuesta"
    parameter_name = "atrasadas"

    def lookups(self, request, model_admin):
        return [("si", f"Más de {HORAS_RESPUESTA} horas hábiles sin respuesta")]

    def queryset(self, request, queryset):
        if self.value() == "si":
            return queryset.filter(pk__in=ids_sin_respuesta())
        return queryset


@admin.register(Consulta)
class ConsultaAdmin(admin.ModelAdmin):
    list_display = ("aviso", "fecha", "nombre", "contacto", "interes_lista", "origen", "estado", "whatsapp_boton")
    list_display_links = ("nombre",)
    list_editable = ("estado",)
    list_filter = ("estado", SinRespuestaFiltro, "origen")
    search_fields = ("nombre", "whatsapp", "correo", "mensaje", "producto__nombre", "curso__nombre")
    date_hierarchy = "fecha"
    change_list_template = "admin/consultas/consulta/change_list.html"
    fields = ("estado", "whatsapp_boton", "nombre", "whatsapp", "correo", "interes_detalle", "origen", "mensaje",
              "fecha", "contactada_en", "compro_en", "pedido_enlace")
    readonly_fields = ("whatsapp_boton", "nombre", "whatsapp", "correo", "interes_detalle", "origen", "mensaje",
                       "fecha", "contactada_en", "compro_en", "pedido_enlace")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("producto", "curso", "cotizacion", "pedido")

    def has_add_permission(self, request):
        return False  # las consultas llegan desde la página

    def changelist_view(self, request, extra_context=None):
        extra_context = {
            **(extra_context or {}),
            "resumen_mes": resumen_del_mes(),
            "total_sin_respuesta": len(ids_sin_respuesta()),
            "horas_respuesta": HORAS_RESPUESTA,
            "nombre_mes": timezone.localdate().strftime("%m/%Y"),
        }
        return super().changelist_view(request, extra_context)

    def save_model(self, request, obj, form, change):
        # Los cambios de estado desde el panel guardan la fecha de contacto o de compra
        if "estado" in form.changed_data:
            obj.cambiar_estado(obj.estado)
        else:
            super().save_model(request, obj, form, change)

    # ----- Columnas -----
    @admin.display(description="")
    def aviso(self, obj):
        """HU 28 CA 3: consultas con más de 24 horas hábiles sin respuesta."""
        if obj.sin_respuesta():
            return format_html('<span class="lr-atrasada" data-atrasada>Sin respuesta +{} h hábiles</span>',
                               HORAS_RESPUESTA)
        return ""

    @admin.display(description="Contacto")
    def contacto(self, obj):
        return obj.whatsapp or obj.correo or "—"

    @admin.display(description="Interés")
    def interes_lista(self, obj):
        return obj.interes

    @admin.display(description="Producto o curso de interés")
    def interes_detalle(self, obj):
        if obj.producto_id:
            return format_html('<a href="{}" target="_blank">{}</a>', obj.producto.get_absolute_url(), obj.producto.nombre)
        if obj.curso_id:
            return format_html('<a href="{}" target="_blank">{}</a>', obj.curso.get_absolute_url(), obj.curso.nombre)
        if obj.cotizacion_id:
            url = reverse("admin:cotizaciones_solicitudcotizacion_change", args=[obj.cotizacion_id])
            return format_html('<a href="{}">{}</a>', url, obj.interes)
        return obj.interes

    @admin.display(description="Pedido con el que compró")
    def pedido_enlace(self, obj):
        if not obj.pedido_id:
            return "—"
        return format_html('<a href="{}">{}</a>', reverse("admin:pedidos_pedido_change", args=[obj.pedido_id]),
                           obj.pedido.numero)

    @admin.display(description="WhatsApp")
    def whatsapp_boton(self, obj):
        """HU 28 CA 4: abre WhatsApp con un mensaje que menciona el producto."""
        if not obj.pk or not obj.whatsapp_internacional:
            return "Sin WhatsApp"
        url = reverse("admin:consultas_consulta_whatsapp", args=[obj.pk])
        return format_html('<a class="button lr-boton-wa" href="{}" target="_blank" rel="noopener">WhatsApp</a>', url)

    # ----- HU 28 CA 4: botón de WhatsApp -----
    def get_urls(self):
        return [
            path("<int:pk>/whatsapp/", self.admin_site.admin_view(self.abrir_whatsapp),
                 name="consultas_consulta_whatsapp"),
        ] + super().get_urls()

    def abrir_whatsapp(self, request, pk):
        consulta = get_object_or_404(Consulta, pk=pk)
        if not self.has_change_permission(request, consulta):
            return redirect("admin:index")
        if not consulta.whatsapp_internacional:
            messages.error(request, "Esta consulta no tiene número de WhatsApp.")
            return redirect("admin:consultas_consulta_changelist")
        # Al escribirle, la consulta nueva pasa a "Contactada" y deja de estar resaltada
        if consulta.estado == Consulta.Estado.NUEVA:
            consulta.cambiar_estado(Consulta.Estado.CONTACTADA)
        return redirect(f"https://wa.me/{consulta.whatsapp_internacional}?text={quote(consulta.mensaje_whatsapp())}")
