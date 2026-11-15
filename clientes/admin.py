"""HU 27: panel de clientes y de códigos de descuento (solo la dueña)."""
from datetime import timedelta

from django.contrib import admin, messages
from django.core.mail import send_mail
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from urllib.parse import quote, urlencode

from pedidos.models import Pedido

from .models import DIAS_CUMPLEANOS, Cliente, CodigoDescuento


# ----------------------------------------------------------------------
# Filtros de la lista de clientes
# ----------------------------------------------------------------------

def ids_cumplen_pronto(queryset, hoy=None):
    hoy = hoy or timezone.localdate()
    return [c.pk for c in queryset.exclude(cumpleanos=None) if c.cumple_pronto(hoy)]


def filtro_compradores():
    """HU 27 CA 5: compraron con la cuenta o, antes, como invitados con el mismo correo."""
    con_cuenta = Pedido.objects.exclude(cliente=None).values_list("cliente_id", flat=True)
    correos = {c.lower() for c in Pedido.objects.exclude(correo="").values_list("correo", flat=True)}
    filtro = Q(usuario_id__in=list(con_cuenta))
    for correo in correos:
        filtro |= Q(usuario__email__iexact=correo)
    return filtro


class CumpleanosFiltro(admin.SimpleListFilter):
    """HU 27 CA 4: clientes que cumplen años en los próximos 7 días."""

    title = "cumpleaños"
    parameter_name = "cumple"

    def lookups(self, request, model_admin):
        return [("pronto", f"En los próximos {DIAS_CUMPLEANOS} días")]

    def queryset(self, request, queryset):
        if self.value() == "pronto":
            return queryset.filter(pk__in=ids_cumplen_pronto(queryset))
        return queryset


class YaComproFiltro(admin.SimpleListFilter):
    """HU 27 CA 5: filtrar a los clientes que ya han comprado."""

    title = "¿ya compró?"
    parameter_name = "compro"

    def lookups(self, request, model_admin):
        return [("si", "Sí, ya compró"), ("no", "Todavía no")]

    def queryset(self, request, queryset):
        if self.value() == "si":
            return queryset.filter(filtro_compradores())
        if self.value() == "no":
            return queryset.exclude(filtro_compradores())
        return queryset


# ----------------------------------------------------------------------
# Clientes
# ----------------------------------------------------------------------

@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nombre_cliente", "correo_cliente", "whatsapp_cliente", "cumple", "compras", "descuento")
    list_filter = (CumpleanosFiltro, YaComproFiltro)
    search_fields = ("usuario__first_name", "usuario__email", "whatsapp")
    fields = ("nombre_cliente", "correo_cliente", "whatsapp", "cumpleanos", "creado", "compras")
    readonly_fields = ("nombre_cliente", "correo_cliente", "creado", "compras")
    change_list_template = "admin/clientes/cliente/change_list.html"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("usuario").prefetch_related("codigos")

    def has_add_permission(self, request):
        return False  # las cuentas las crea cada cliente al registrarse

    def changelist_view(self, request, extra_context=None):
        todos = Cliente.objects.all()
        extra_context = {
            **(extra_context or {}),
            "total_cumplen": len(ids_cumplen_pronto(todos)),
            "total_compraron": todos.filter(filtro_compradores()).count(),
            "dias_cumpleanos": DIAS_CUMPLEANOS,
        }
        return super().changelist_view(request, extra_context)

    @admin.display(description="Nombre", ordering="usuario__first_name")
    def nombre_cliente(self, obj):
        return obj.nombre

    @admin.display(description="Correo", ordering="usuario__email")
    def correo_cliente(self, obj):
        return obj.correo

    @admin.display(description="WhatsApp")
    def whatsapp_cliente(self, obj):
        return obj.whatsapp_contacto or "—"

    @admin.display(description="Cumpleaños", ordering="cumpleanos")
    def cumple(self, obj):
        if not obj.cumpleanos:
            return "—"
        dias = obj.dias_para_cumpleanos()
        texto = obj.cumpleanos.strftime("%d/%m")
        if dias == 0:
            return format_html('{} <strong class="lr-cumple">¡Hoy!</strong>', texto)
        if dias <= DIAS_CUMPLEANOS:
            return format_html('{} <strong class="lr-cumple">en {} día{}</strong>', texto, dias, "s" if dias > 1 else "")
        return texto

    @admin.display(description="Compras")
    def compras(self, obj):
        return obj.pedidos().count()

    @admin.display(description="Código de descuento")
    def descuento(self, obj):
        """Si tiene un código disponible se puede enviar; si no, se crea uno."""
        hoy = timezone.localdate()
        disponible = next((c for c in obj.codigos.all() if not c.usado and not c.vencido(hoy)), None)
        if disponible:
            url = reverse("admin:clientes_codigodescuento_enviar", args=[disponible.pk])
            return format_html('{} · <a class="button" href="{}">Enviar</a>', disponible.codigo, url)
        if obj.cumple_pronto(hoy):
            motivo = CodigoDescuento.Motivo.CUMPLEANOS
        elif obj.ya_compro:
            motivo = CodigoDescuento.Motivo.GRACIAS
        else:
            motivo = CodigoDescuento.Motivo.OTRO
        url = reverse("admin:clientes_codigodescuento_add") + "?" + urlencode({"cliente": obj.pk, "motivo": motivo})
        return format_html('<a class="button" href="{}">Crear código</a>', url)


# ----------------------------------------------------------------------
# Códigos de descuento
# ----------------------------------------------------------------------

@admin.register(CodigoDescuento)
class CodigoDescuentoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "cliente", "motivo", "descuento", "vence", "estado_codigo", "enviado_en", "enviar")
    list_filter = ("motivo", "tipo")
    search_fields = ("codigo", "cliente__usuario__first_name", "cliente__usuario__email")
    fields = ("cliente", "motivo", "codigo", "tipo", "valor", "vence", "estado_codigo", "enviado_en", "pedido_usado")
    readonly_fields = ("estado_codigo", "enviado_en", "pedido_usado")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("cliente__usuario")

    def get_fields(self, request, obj=None):
        if obj is None:  # al crear solo se piden los datos del código
            return ("cliente", "motivo", "codigo", "tipo", "valor", "vence")
        return self.fields

    def get_readonly_fields(self, request, obj=None):
        # Un código usado ya no se cambia
        if obj and obj.usado:
            return ("cliente", "motivo", "codigo", "tipo", "valor", "vence") + self.readonly_fields
        return self.readonly_fields

    def get_changeform_initial_data(self, request):
        """HU 27: el código se propone solo (ej. CUMPLE-PAULA-7K3Q) y la dueña lo puede cambiar."""
        inicial = super().get_changeform_initial_data(request)
        cliente = Cliente.objects.filter(pk=request.GET.get("cliente") or None).first()
        motivo = request.GET.get("motivo") or CodigoDescuento.Motivo.OTRO
        inicial.setdefault("motivo", motivo)
        inicial["codigo"] = CodigoDescuento.proponer_codigo(cliente, motivo)
        inicial.setdefault("vence", timezone.localdate() + timedelta(days=30))
        return inicial

    def response_add(self, request, obj, post_url_continue=None):
        if "_continue" not in request.POST and "_addanother" not in request.POST:
            messages.success(request, f"Código {obj.codigo} creado para {obj.cliente.nombre}. Ahora envíaselo.")
            return redirect("admin:clientes_codigodescuento_enviar", obj.pk)
        return super().response_add(request, obj, post_url_continue)

    @admin.display(description="Descuento")
    def descuento(self, obj):
        return obj.descuento_texto

    @admin.display(description="Estado")
    def estado_codigo(self, obj):
        return obj.estado

    @admin.display(description="Pedido donde se usó")
    def pedido_usado(self, obj):
        pedido = getattr(obj, "pedido", None)
        if not pedido:
            return "—"
        return format_html('<a href="{}">{}</a>', reverse("admin:pedidos_pedido_change", args=[pedido.pk]), pedido.numero)

    @admin.display(description="")
    def enviar(self, obj):
        if obj.usado or obj.vencido():
            return ""
        return format_html('<a class="button" href="{}">Enviar</a>',
                           reverse("admin:clientes_codigodescuento_enviar", args=[obj.pk]))

    # ----- HU 27 CA 4: envío por correo o WhatsApp con el nombre del cliente -----
    def get_urls(self):
        return [
            path("<int:pk>/enviar/", self.admin_site.admin_view(self.vista_enviar),
                 name="clientes_codigodescuento_enviar"),
        ] + super().get_urls()

    def vista_enviar(self, request, pk):
        codigo = get_object_or_404(CodigoDescuento.objects.select_related("cliente__usuario"), pk=pk)
        if not self.has_change_permission(request, codigo):
            return redirect("admin:index")
        cliente = codigo.cliente
        mensaje = codigo.mensaje(request.build_absolute_uri("/"))
        if request.method == "POST":
            canal = request.POST.get("canal")
            if canal == "correo":
                send_mail(f"Un regalo para ti, {cliente.primer_nombre}", mensaje, None, [cliente.correo])
                codigo.enviado_en = timezone.now()
                codigo.save(update_fields=["enviado_en"])
                messages.success(request, f"Le enviamos el código a {cliente.correo}.")
                return redirect("admin:clientes_codigodescuento_changelist")
            if canal == "whatsapp" and cliente.whatsapp_internacional:
                codigo.enviado_en = timezone.now()
                codigo.save(update_fields=["enviado_en"])
                return redirect(f"https://wa.me/{cliente.whatsapp_internacional}?text={quote(mensaje)}")
            messages.error(request, "Este cliente no tiene un número de WhatsApp registrado.")
        contexto = {
            **self.admin_site.each_context(request),
            "title": f"Enviar el código {codigo.codigo}",
            "codigo": codigo, "cliente": cliente, "mensaje": mensaje,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/clientes/codigodescuento/enviar.html", contexto)
