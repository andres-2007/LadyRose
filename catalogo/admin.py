from django.contrib import admin
from django.utils.html import format_html

from .models import Categoria, Coleccion, FotoProducto, Producto, TallaProducto


class FotoProductoInline(admin.TabularInline):
    model = FotoProducto
    extra = 1
    fields = ("imagen", "vista_previa", "orden")
    readonly_fields = ("vista_previa",)

    @admin.display(description="Vista previa")
    def vista_previa(self, obj):
        if obj.pk and obj.imagen:
            return format_html('<img src="{}" style="height:60px;border-radius:4px">', obj.imagen.url)
        return "-"


class TallaProductoInline(admin.TabularInline):
    model = TallaProducto
    extra = 1
    fields = ("nombre", "medida", "disponible", "orden")


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "cantidad_productos")
    search_fields = ("nombre",)
    exclude = ("slug",)

    @admin.display(description="Productos")
    def cantidad_productos(self, obj):
        return obj.productos.count()


@admin.register(Coleccion)
class ColeccionAdmin(admin.ModelAdmin):
    """HU 16: la diseñadora crea colecciones con nombre, descripción y portada."""

    list_display = ("nombre", "portada_mini", "cantidad_productos", "visible", "orden")
    list_editable = ("visible", "orden")
    search_fields = ("nombre",)
    exclude = ("slug",)

    @admin.display(description="Portada")
    def portada_mini(self, obj):
        if obj.portada:
            return format_html('<img src="{}" style="height:44px;border-radius:4px">', obj.portada.url)
        return "-"

    @admin.display(description="Productos")
    def cantidad_productos(self, obj):
        return obj.productos.count()


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ("miniatura", "nombre", "categoria", "precio", "precio_oferta", "en_oferta_hoy",
                    "pieza_unica", "vendida", "visible")
    list_display_links = ("miniatura", "nombre")
    list_filter = ("categoria", "colecciones", "visible", "pieza_unica", "vendida")
    filter_horizontal = ("colecciones",)
    list_editable = ("precio", "visible")
    search_fields = ("nombre", "descripcion")
    inlines = [FotoProductoInline, TallaProductoInline]
    fieldsets = (
        (None, {"fields": ("nombre", "categoria", "colecciones", "descripcion", "precio", "visible")}),
        ("Fabricación", {"fields": ("material", "colores", "tecnica", "dias_elaboracion")}),
        ("Pieza única", {"fields": ("pieza_unica", "vendida"),
                         "description": "Una pieza única vendida pasa sola a la Galería de piezas vendidas."}),
        ("Oferta", {"fields": ("precio_oferta", "oferta_inicio", "oferta_fin")}),
        ("Cuidados", {"fields": ("instrucciones_cuidado",)}),
    )
    actions = ["ocultar", "mostrar"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("categoria").prefetch_related("fotos")

    @admin.display(description="")
    def miniatura(self, obj):
        foto = obj.foto_principal
        if foto:
            return format_html('<img src="{}" style="height:44px;width:44px;object-fit:cover;border-radius:4px">',
                               foto.imagen.url)
        return "-"

    @admin.display(boolean=True, description="Oferta activa")
    def en_oferta_hoy(self, obj):
        return obj.en_oferta

    @admin.action(description="Ocultar los productos seleccionados (agotados)", permissions=["change"])
    def ocultar(self, request, queryset):
        n = queryset.update(visible=False)
        self.message_user(request, f"Se ocultaron {n} productos.")

    @admin.action(description="Volver a mostrar los productos seleccionados", permissions=["change"])
    def mostrar(self, request, queryset):
        n = queryset.update(visible=True)
        self.message_user(request, f"Se mostraron {n} productos.")
