"""Avisos al cliente por correo.

HU 30 CA 2: aviso cuando la dueña confirma el valor del envío.
HU 12 CA 4: correo de confirmación con el resumen de la compra.
"""
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from core.templatetags.ladyrose import pesos

from .models import Pedido


def mensaje_envio(pedido, request=None):
    """Texto del aviso (correo y WhatsApp) con el valor del envío y el nuevo total."""
    url = reverse("pedidos:mi_pedido", args=[pedido.pk])
    if request is not None:
        url = request.build_absolute_uri(url)
    nombre = pedido.nombre.split()[0] if pedido.nombre else ""
    valor = "gratis" if pedido.costo_envio == 0 else pesos(pedido.costo_envio)
    partes = [
        f"¡Hola {nombre}! Ya tenemos el valor del envío de tu pedido {pedido.numero}: {valor}.",
        f"El total de tu pedido queda en {pesos(pedido.total)}.",
    ]
    if pedido.metodo_pago == Pedido.MetodoPago.TRANSFERENCIA and not pedido.comprobante:
        partes.append(f"Para despacharlo, transfiere {pesos(pedido.total)} "
                      f"({settings.LADYROSE['DATOS_TRANSFERENCIA']}) y sube el comprobante aquí: {url}")
    elif pedido.pago_en_linea and not pedido.pago_aprobado:
        # HU 12: el cliente paga en línea desde la página de su pedido
        partes.append(f"Para despacharlo, paga {pesos(pedido.total)} con {pedido.get_metodo_pago_display()} "
                      f"desde tu pedido: {url}")
    elif pedido.metodo_pago == Pedido.MetodoPago.CONTRA_ENTREGA:
        partes.append(f"Lo pagas cuando lo recibas. Puedes ver tu pedido aquí: {url}")
    else:
        partes.append(f"Puedes ver tu pedido aquí: {url}")
    partes.append("Con cariño, Ladyrose.")
    return "\n\n".join(partes)


def avisar_envio_por_correo(pedido, request=None):
    """Envía el aviso por correo. Devuelve False si el pedido no tiene correo."""
    if not pedido.correo:
        return False
    send_mail(f"El envío de tu pedido {pedido.numero}", mensaje_envio(pedido, request), None, [pedido.correo])
    pedido.envio_avisado_en = timezone.now()
    pedido.save(update_fields=["envio_avisado_en"])
    return True


def url_pedido(pedido, request=None):
    """Enlace completo a la página del pedido del cliente.

    Cuando el aviso sale del webhook de la pasarela no hay request, así que se usa la
    dirección del sitio de la configuración (LADYROSE_URL_SITIO).
    """
    ruta = reverse("pedidos:mi_pedido", args=[pedido.pk])
    if request is not None:
        return request.build_absolute_uri(ruta)
    return settings.LADYROSE["URL_SITIO"].rstrip("/") + ruta


def enviar_confirmacion(pedido, request=None):
    """HU 12 CA 4: correo con el resumen de la compra. Devuelve False si el pedido no tiene correo."""
    if not pedido.correo:
        return False
    contexto = {"pedido": pedido, "url_pedido": url_pedido(pedido, request)}
    asunto = (f"Pago aprobado: tu pedido {pedido.numero} en Ladyrose" if pedido.pago_aprobado
              else f"Recibimos tu pedido {pedido.numero} en Ladyrose")
    correo = EmailMultiAlternatives(asunto, render_to_string("pedidos/correos/confirmacion.txt", contexto),
                                    None, [pedido.correo])
    correo.attach_alternative(render_to_string("pedidos/correos/confirmacion.html", contexto), "text/html")
    correo.send()
    return True
