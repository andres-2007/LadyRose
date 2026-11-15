from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from django import template

register = template.Library()


@register.filter
def pesos(valor):
    """Formatea un valor en pesos colombianos: 45000 -> $45.000"""
    try:
        numero = int(Decimal(valor))
    except (InvalidOperation, TypeError, ValueError):
        return valor
    return "$" + f"{numero:,}".replace(",", ".")


@register.simple_tag(takes_context=True)
def url_compartir(context, objeto, canal):
    """HU 31: enlace directo al producto o curso, marcado con la red por la que se comparte."""
    request = context["request"]
    return request.build_absolute_uri(objeto.get_absolute_url()) + f"?utm_source={canal}"


@register.simple_tag(takes_context=True)
def whatsapp_compartir(context, objeto):
    texto = f"Mira esto de Ladyrose: {objeto} {url_compartir(context, objeto, 'whatsapp')}"
    return "https://wa.me/?text=" + quote(texto)


@register.simple_tag(takes_context=True)
def facebook_compartir(context, objeto):
    return "https://www.facebook.com/sharer/sharer.php?u=" + quote(url_compartir(context, objeto, "facebook"), safe="")


@register.simple_tag
def whatsapp_tienda(numero, mensaje):
    """Botón que abre el WhatsApp oficial de Ladyrose con un mensaje precargado."""
    return f"https://wa.me/{numero}?text=" + quote(mensaje)


@register.simple_tag(takes_context=True)
def actual(context, prefijo, exacto=False):
    """Marca el enlace del menú de la página en la que está la persona."""
    ruta = context["request"].path
    coincide = ruta == prefijo if exacto else ruta.startswith(prefijo)
    return 'aria-current="page"' if coincide else ""


@register.filter
def primer_nombre(nombre):
    return (nombre or "").split(" ")[0]


@register.simple_tag(takes_context=True)
def resumen_panel(context):
    """HU 22: datos de las tarjetas del panel principal.

    Cada tarjeta sale solo si el usuario puede ver esos datos (las visitas son solo para la dueña).
    Se calcula cada vez que se abre la página, así que siempre está al día (CA 4).
    """
    from django.urls import reverse
    from django.utils import timezone

    from core import resumen

    usuario = context["request"].user
    hoy = timezone.localdate()
    datos = {}
    # CA 3: cada tarjeta abre la lista del panel con el detalle, ya filtrada
    if usuario.has_perm("pedidos.view_pedido"):
        datos["pedidos"] = resumen.resumen_pedidos()
        datos["pedidos"]["url"] = reverse("admin:pedidos_pedido_changelist") + "?despacho=pendientes"
    if usuario.has_perm("cotizaciones.view_solicitudcotizacion"):
        datos["cotizaciones"] = resumen.resumen_cotizaciones()
        datos["cotizaciones"]["url"] = (reverse("admin:cotizaciones_solicitudcotizacion_changelist")
                                        + "?consulta__estado__exact=nueva")
    if usuario.has_perm("core.view_visitaorigen"):
        lista = reverse("admin:core_visitaorigen_changelist")
        filtro_mes = f"?fecha__year={hoy.year}&fecha__month={hoy.month}"
        for clave, visitas, filtro in (("visitas_hoy", resumen.visitas_hoy(), filtro_mes + f"&fecha__day={hoy.day}"),
                                       ("visitas_mes", resumen.visitas_mes(), filtro_mes)):
            visitas["url"] = lista + filtro
            for canal in visitas["canales"]:
                canal["url"] = lista + filtro + f"&canal__exact={canal['canal']}"
            datos[clave] = visitas
    if datos:
        datos["generado"] = timezone.localtime()
        datos["hoy"] = hoy
    return datos
