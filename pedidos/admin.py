from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from core.templatetags.ladyrose import pesos

from .models import DetallePedido, Pedido, TipoEmpaque


@admin.register(TipoEmpaque)
class TipoEmpaqueAdmin(admin.ModelAdmin):
    """HU 11: la dueña administra los empaques y su costo."""

    list_display = ("nombre", "descripcion", "costo", "activo", "orden")
    list_editable = ("costo", "activo", "orden")


class DetallePedidoInline(admin.TabularInline):
    model = DetallePedido
    extra = 0
    fields = ("referencia", "talla", "color", "material", "cantidad", "precio_unitario")

    def get_readonly_fields(self, request, obj=None):
        # Lo que compró el cliente no se cambia; en pedidos creados a mano sí se llena.
        if obj and obj.detalles.exists() and not obj.cotizacion_id:
            return self.fields
        return ()


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    """HU 24 CA 5: envío, productos y pago en una sola vista."""

    list_display = ("numero_pedido", "creado", "nombre", "ciudad", "total_pesos", "metodo_pago",
                    "estado_pago", "estado_produccion", "estado_envio", "regalo")
    list_filter = ("estado_produccion", "estado_envio", "estado_pago", "metodo_pago", "canal_origen")
    search_fields = ("id", "nombre", "telefono", "correo", "nombre_recibe", "direccion")
    list_editable = ("estado_envio",)
    date_hierarchy = "creado"
    inlines = [DetallePedidoInline]
    readonly_fields = ("numero_pedido", "creado", "ver_comprobante", "abrir_en_panel", "nota_destacada",
                       "subtotal", "costo_empaque", "total", "canal_origen", "estado_actualizado")
    fieldsets = (
        (None, {"fields": ("numero_pedido", "creado", "abrir_en_panel")}),
        ("Quien compra", {"fields": ("nombre", "correo", "telefono", "whatsapp_igual", "whatsapp")}),
        ("Datos de envío", {"fields": ("enviar_a_otra_persona", "nombre_recibe", "telefono_recibe",
                                       "direccion", "barrio", "ciudad", "indicaciones", "estado_envio")}),
        ("Regalo", {"fields": ("empaque", "nota_destacada", "nota", "motivo")}),
        ("Pago", {"fields": ("metodo_pago", "comprobante", "ver_comprobante", "estado_pago",
                             "subtotal", "costo_empaque", "total")}),
        ("Producción", {"fields": ("cotizacion", "tecnica", "dias_elaboracion", "fecha_limite",
                                   "estado_produccion", "estado_actualizado", "canal_origen")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("empaque")

    @admin.display(description="Pedido", ordering="id")
    def numero_pedido(self, obj):
        return obj.numero

    @admin.display(description="Total", ordering="total")
    def total_pesos(self, obj):
        return pesos(obj.total)

    @admin.display(boolean=True, description="Regalo")
    def regalo(self, obj):
        return obj.tiene_regalo

    @admin.display(description="Comprobante")
    def ver_comprobante(self, obj):
        if not obj.comprobante:
            return "No aplica" if obj.metodo_pago == Pedido.MetodoPago.CONTRA_ENTREGA else "Sin comprobante"
        url = obj.comprobante.url
        if url.lower().endswith(".pdf"):
            return format_html('<a href="{}" target="_blank">Abrir PDF</a>', url)
        return format_html('<a href="{0}" target="_blank"><img src="{0}" style="max-height:220px;border-radius:6px"></a>', url)

    @admin.display(description="Panel de producción")
    def abrir_en_panel(self, obj):
        if not obj.pk:
            return "-"
        return format_html('<a class="button" href="{}">Ver tarjeta de producción</a>',
                           reverse("pedidos:panel_detalle", args=[obj.pk]))

    @admin.display(description="Nota (vista)")
    def nota_destacada(self, obj):
        if not obj.nota:
            return "Sin nota"
        return format_html('<div class="lr-destacado">{}</div>', obj.nota)

    def save_model(self, request, obj, form, change):
        if obj.cotizacion_id and not obj.motivo:
            obj.motivo = obj.cotizacion.motivo
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        pedido = form.instance
        detalles = list(pedido.detalles.all())
        subtotal = sum((d.subtotal for d in detalles), 0)
        if detalles and subtotal != pedido.subtotal:
            pedido.subtotal = subtotal
            pedido.costo_empaque = pedido.empaque.costo if pedido.empaque else 0
            pedido.total = subtotal + pedido.costo_empaque
            pedido.save(update_fields=["subtotal", "costo_empaque", "total"])
