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
