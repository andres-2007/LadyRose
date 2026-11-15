"""HU 30 CA 2: aviso al cliente cuando la dueña confirma el valor del envío."""
from django.conf import settings
from django.core.mail import send_mail
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
