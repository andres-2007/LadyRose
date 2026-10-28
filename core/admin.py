from django.contrib import admin
from django.db.models import Count
from django.shortcuts import redirect
from django.urls import reverse

from .models import ConfiguracionTienda, ContenidoHistoria, FotoTaller, VisitaOrigen

admin.site.site_header = "Panel de Ladyrose"
admin.site.site_title = "Ladyrose"
admin.site.index_title = "Administración de la tienda"
admin.site.enable_nav_sidebar = False


class UnicoAdmin(admin.ModelAdmin):
    """Para modelos de un solo registro: se abre directo el formulario de edición."""

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = self.model.obtener()
        info = (self.model._meta.app_label, self.model._meta.model_name)
        return redirect(reverse("admin:%s_%s_change" % info, args=[obj.pk]))


@admin.register(ConfiguracionTienda)
class ConfiguracionTiendaAdmin(UnicoAdmin):
    fields = ("monto_minimo_mayorista", "actualizado")
    readonly_fields = ("actualizado",)


class FotoTallerInline(admin.TabularInline):
    model = FotoTaller
    extra = 1


@admin.register(ContenidoHistoria)
class ContenidoHistoriaAdmin(UnicoAdmin):
    fields = ("titulo", "texto", "video_url")
    inlines = [FotoTallerInline]


@admin.register(VisitaOrigen)
class VisitaOrigenAdmin(admin.ModelAdmin):
    """HU 31: la dueña ve desde qué red llega cada visita."""

    list_display = ("fecha", "canal", "pagina")
    list_filter = ("canal", "fecha")
    date_hierarchy = "fecha"
    change_list_template = "admin/core/visitaorigen/change_list.html"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        respuesta = super().changelist_view(request, extra_context)
        try:
            qs = respuesta.context_data["cl"].queryset
        except (AttributeError, KeyError):
            return respuesta
        etiquetas = dict(VisitaOrigen.Canal.choices)
        resumen = [
            {"canal": etiquetas.get(f["canal"], f["canal"]), "total": f["total"]}
            for f in qs.values("canal").annotate(total=Count("id")).order_by("-total")
        ]
        respuesta.context_data["resumen_canales"] = resumen
        return respuesta
