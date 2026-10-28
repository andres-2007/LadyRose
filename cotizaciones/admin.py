from django.contrib import admin
from django.utils.html import format_html

from .models import ImagenReferencia, SolicitudCotizacion


class ImagenReferenciaInline(admin.TabularInline):
    model = ImagenReferencia
    extra = 0
    fields = ("vista_previa",)
    readonly_fields = ("vista_previa",)
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Imagen")
    def vista_previa(self, obj):
        return format_html('<a href="{0}" target="_blank"><img src="{0}" style="height:120px"></a>',
                           obj.imagen.url)


@admin.register(SolicitudCotizacion)
class SolicitudCotizacionAdmin(admin.ModelAdmin):
    list_display = ("fecha", "nombre", "tipo", "producto", "whatsapp", "estado")
    list_filter = ("estado", "tipo")
    search_fields = ("nombre", "whatsapp", "correo", "descripcion", "motivo")
    inlines = [ImagenReferenciaInline]
    readonly_fields = ("motivo_destacado", "tipo", "nombre", "whatsapp", "correo", "descripcion",
                       "producto_original", "cambio_color", "cambio_talla", "cambio_material",
                       "cambio_otro", "acepta_pieza_unica", "fecha_aceptacion", "fecha")
    fieldsets = (
        ("Cliente", {"fields": ("nombre", "whatsapp", "correo", "fecha")}),
        # HU 09: la historia o el motivo aparece destacado al abrir la solicitud
        ("Historia o motivo", {"fields": ("motivo_destacado",)}),
        ("Pedido", {"fields": ("tipo", "descripcion", "producto_original", "cambio_color",
                               "cambio_talla", "cambio_material", "cambio_otro")}),
        ("Aviso de pieza única", {"fields": ("acepta_pieza_unica", "fecha_aceptacion")}),
        ("Seguimiento", {"fields": ("estado",)}),
    )

    def has_add_permission(self, request):
        return False

    @admin.display(description="Para quién es / qué la inspira")
    def motivo_destacado(self, obj):
        if not obj.motivo:
            return "El cliente no escribió una historia."
        return format_html('<div class="lr-destacado">{}</div>', obj.motivo)

    @admin.display(description="Producto original")
    def producto_original(self, obj):
        if not obj.producto:
            return "-"
        foto = obj.producto.foto_principal
        img = format_html('<br><img src="{}" style="height:90px;margin-top:6px;border-radius:6px">', foto.imagen.url) if foto else ""
        return format_html('<a href="{}" target="_blank">{}</a>{}', obj.producto.get_absolute_url(),
                           obj.producto.nombre, img)
