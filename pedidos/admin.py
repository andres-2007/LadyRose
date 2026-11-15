from urllib.parse import quote

from django.contrib import admin, messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from core.templatetags.ladyrose import pesos

from .avisos import avisar_envio_por_correo, mensaje_envio
from .models import BarrioZona, DetallePedido, Pedido, TarifaPeso, TiempoEnvio, TipoEmpaque, ZonaEnvio


# ----------------------------------------------------------------------
# HU 30: zonas de Cali y tarifas por peso (solo la dueña)
# ----------------------------------------------------------------------

class BarrioZonaInline(admin.TabularInline):
    model = BarrioZona
    extra = 3
    fields = ("nombre",)


@admin.register(ZonaEnvio)
class ZonaEnvioAdmin(admin.ModelAdmin):
    """HU 30 CA 1: zonas de Cali con tarifa fija (0 = domicilio gratis) y sus barrios."""

    list_display = ("nombre", "tarifa_texto", "activa", "lista_barrios")
    list_editable = ("activa",)
    search_fields = ("nombre", "barrios__nombre")
    inlines = [BarrioZonaInline]

    @admin.display(description="Tarifa", ordering="tarifa")
    def tarifa_texto(self, obj):
        return "Gratis" if obj.tarifa == 0 else pesos(obj.tarifa)

    @admin.display(description="Barrios")
    def lista_barrios(self, obj):
        return ", ".join(b.nombre for b in obj.barrios.all()) or "Sin barrios"


@admin.register(TarifaPeso)
class TarifaPesoAdmin(admin.ModelAdmin):
    """HU 30 CA 3: tarifas de envío a otras ciudades según el peso (copiadas de Servientrega)."""

    list_display = ("rango", "peso_hasta", "valor")
    list_editable = ("peso_hasta", "valor")
    list_display_links = ("rango",)

    @admin.display(description="Rango")
    def rango(self, obj):
        anterior = TarifaPeso.objects.filter(peso_hasta__lt=obj.peso_hasta).order_by("-peso_hasta").first()
        desde = anterior.peso_hasta + 1 if anterior else 1
        return f"De {desde} a {obj.peso_hasta} g"


@admin.register(TipoEmpaque)
class TipoEmpaqueAdmin(admin.ModelAdmin):
    """HU 11: la dueña administra los empaques y su costo."""

    list_display = ("nombre", "descripcion", "costo", "activo", "orden")
    list_editable = ("costo", "activo", "orden")


@admin.register(TiempoEnvio)
class TiempoEnvioAdmin(admin.ModelAdmin):
    """HU 07: tabla de tiempos de envío por ciudad que administra la dueña.

    Las ciudades que no estén aquí usan el tiempo de "otras ciudades" de la
    configuración de la tienda.
    """

    list_display = ("ciudad", "dias_min", "dias_max", "por_transportadora")
    list_editable = ("dias_min", "dias_max", "por_transportadora")
    search_fields = ("ciudad",)


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

    list_display = ("numero_pedido", "creado", "tipo", "nombre", "ciudad", "total_pesos", "envio_lista", "metodo_pago",
                    "estado_pago", "estado_produccion", "estado_envio", "regalo")
    list_filter = ("tipo", "envio_costo_estado", "estado_produccion", "estado_envio", "estado_pago", "metodo_pago",
                   "canal_origen")
    search_fields = ("id", "nombre", "telefono", "correo", "nombre_recibe", "direccion")
    list_editable = ("estado_envio",)
    date_hierarchy = "creado"
    inlines = [DetallePedidoInline]
    readonly_fields = ("numero_pedido", "creado", "tipo", "ver_comprobante", "abrir_en_panel", "nota_destacada",
                       "subtotal", "costo_empaque", "total", "canal_origen", "estado_actualizado",
                       "cliente", "codigo_descuento", "descuento",
                       "envio_costo_estado", "envio_detalle", "peso_total", "envio_avisado_en", "avisar_envio")
    fieldsets = (
        (None, {"fields": ("numero_pedido", "creado", "tipo", "abrir_en_panel")}),
        ("Quien compra", {"fields": ("cliente", "nombre", "correo", "telefono", "whatsapp_igual", "whatsapp")}),
        ("Datos de envío", {"fields": ("enviar_a_otra_persona", "nombre_recibe", "telefono_recibe",
                                       "direccion", "barrio", "ciudad", "indicaciones", "estado_envio")}),
        # HU 30: si quedó por confirmar, la dueña escribe el valor y se avisa al cliente
        ("Costo del envío", {"fields": ("envio_costo_estado", "envio_detalle", "peso_total", "costo_envio",
                                        "envio_avisado_en", "avisar_envio")}),
        ("Regalo", {"fields": ("empaque", "nota_destacada", "nota", "motivo")}),
        ("Pago", {"fields": ("metodo_pago", "comprobante", "ver_comprobante", "estado_pago",
                             "subtotal", "codigo_descuento", "descuento", "costo_empaque", "total")}),
        ("Producción", {"fields": ("cotizacion", "tecnica", "dias_elaboracion", "fecha_limite",
                                   "estado_produccion", "estado_actualizado", "canal_origen")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("empaque")

    def get_readonly_fields(self, request, obj=None):
        campos = list(super().get_readonly_fields(request, obj))
        # HU 30: solo la dueña registra el valor del envío
        if not request.user.has_perm("pedidos.change_zonaenvio"):
            campos.append("costo_envio")
        return campos

    @admin.display(description="Envío")
    def envio_lista(self, obj):
        if obj.envio_por_confirmar:
            return format_html('<span class="lr-atrasada">Por confirmar</span>')
        if obj.costo_envio is None:
            return "—"
        return "Gratis" if obj.costo_envio == 0 else pesos(obj.costo_envio)

    @admin.display(description="Avisar al cliente")
    def avisar_envio(self, obj):
        if not obj.pk or obj.costo_envio is None or obj.envio_por_confirmar:
            return "Primero escriba el costo del envío y guarde."
        url = reverse("admin:pedidos_pedido_avisar_envio", args=[obj.pk])
        return format_html('<a class="button" href="{}" target="_blank" rel="noopener">Avisar por WhatsApp</a>', url)

    # ----- HU 30 CA 2: aviso por WhatsApp con el valor del envío -----
    def get_urls(self):
        return [
            path("<int:pk>/avisar-envio/", self.admin_site.admin_view(self.vista_avisar_envio),
                 name="pedidos_pedido_avisar_envio"),
        ] + super().get_urls()

    def vista_avisar_envio(self, request, pk):
        pedido = get_object_or_404(Pedido, pk=pk)
        if not self.has_change_permission(request, pedido) or pedido.costo_envio is None:
            return redirect("admin:pedidos_pedido_change", pk)
        pedido.envio_avisado_en = timezone.now()
        pedido.save(update_fields=["envio_avisado_en"])
        texto = mensaje_envio(pedido, request)
        return redirect(f"https://wa.me/{pedido.whatsapp_internacional}?text={quote(texto)}")

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
        # HU 30 CA 2: la dueña registra el valor del domicilio que estaba por confirmar
        confirmado_ahora = (change and "costo_envio" in form.changed_data and obj.costo_envio is not None
                            and obj.envio_costo_estado == Pedido.EstadoEnvioCosto.POR_CONFIRMAR)
        if "costo_envio" in form.changed_data:
            if obj.costo_envio is not None and obj.envio_costo_estado == Pedido.EstadoEnvioCosto.POR_CONFIRMAR:
                obj.envio_costo_estado = Pedido.EstadoEnvioCosto.CONFIRMADO
            obj.calcular_total()
        super().save_model(request, obj, form, change)
        if confirmado_ahora:
            if avisar_envio_por_correo(obj, request):
                messages.success(request, f"Le enviamos el valor del envío a {obj.correo}. "
                                          "Si quieres, avísale también por WhatsApp con el botón del pedido.")
            else:
                messages.warning(request, "El pedido no tiene correo: avísale por WhatsApp con el botón del pedido.")

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        pedido = form.instance
        detalles = list(pedido.detalles.all())
        subtotal = sum((d.subtotal for d in detalles), 0)
        if detalles and subtotal != pedido.subtotal:
            pedido.subtotal = subtotal
            pedido.costo_empaque = pedido.empaque.costo if pedido.empaque else 0
            pedido.calcular_total()
            pedido.save(update_fields=["subtotal", "costo_empaque", "total"])
