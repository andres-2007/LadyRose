from django import template
from django.urls import reverse

from catalogo.models import Producto

from ..forms import PreguntaForm, datos_iniciales

register = template.Library()


@register.inclusion_tag("consultas/_preguntanos.html", takes_context=True)
def formulario_pregunta(context, objeto, abierto=False):
    """HU 28: bloque "¿Tienes una pregunta?" en la ficha del producto o del curso."""
    request = context["request"]
    tipo = "producto" if isinstance(objeto, Producto) else "curso"
    return {
        "form": context.get("form_pregunta") or PreguntaForm(initial=datos_iniciales(request.user)),
        "accion": reverse(f"consultas:preguntar_{tipo}", args=[objeto.slug]),
        "objeto": objeto, "abierto": abierto, "csrf_token": context.get("csrf_token"),
        "LADYROSE": context.get("LADYROSE"),
    }
