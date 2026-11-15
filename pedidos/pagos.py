"""HU 12: pagos en línea de los pedidos (Nequi, PSE y Transferencia Bancolombia).

Aquí está lo que hace la tienda con la pasarela: crear el intento de pago, armar el
enlace a la página de pago y registrar la respuesta de la transacción.
"""
from urllib.parse import urlencode

from django.db import transaction
from django.urls import reverse

from . import pasarela
from .models import Pago, Pedido

# Estado del pago en la tienda según el estado de la transacción en la pasarela
ESTADOS = {
    pasarela.EstadoTransaccion.APROBADA: Pago.Estado.APROBADO,
    pasarela.EstadoTransaccion.RECHAZADA: Pago.Estado.RECHAZADO,
    pasarela.EstadoTransaccion.ANULADA: Pago.Estado.CANCELADO,
    pasarela.EstadoTransaccion.ERROR: Pago.Estado.ERROR,
}


def crear_pago(pedido):
    """Nuevo intento de pago por el total del pedido."""
    return Pago.objects.create(pedido=pedido, metodo=pedido.metodo_pago, monto=pedido.total,
                               referencia=pasarela.nueva_referencia(pedido))


def url_pago(request, pago):
    """Enlace a la página de pago con los mismos parámetros que usa el Web Checkout de Wompi."""
    centavos = pasarela.en_centavos(pago.monto)
    pedido = pago.pedido
    parametros = {
        "public-key": pasarela.config()["LLAVE_PUBLICA"],
        "currency": pasarela.MONEDA,
        "amount-in-cents": centavos,
        "reference": pago.referencia,
        "signature:integrity": pasarela.firma_integridad(pago.referencia, centavos),
        "redirect-url": request.build_absolute_uri(reverse("pedidos:resultado_pago")),
        "customer-data:email": pedido.correo,
        "customer-data:full-name": pedido.nombre,
        "customer-data:phone-number": pedido.telefono,
    }
    return reverse("pedidos:pasarela") + "?" + urlencode(parametros)


def procesar_evento(evento):
    """Aviso (webhook) de la pasarela con el resultado de una transacción.

    CA 3: el pedido pasa a "Pago aprobado" solo por aquí, cuando el evento trae la
    firma correcta de la pasarela. La página a la que vuelve el cliente no puede
    aprobar nada: solo muestra lo que la pasarela ya confirmó.
    Devuelve el pago actualizado, o None si el evento no es válido.
    """
    if not pasarela.evento_valido(evento):
        return None
    if evento.get("event") != "transaction.updated":
        return None
    return registrar_transaccion(evento["data"]["transaction"])


def registrar_transaccion(datos):
    """Guarda la respuesta de la pasarela para el pago con esa referencia.

    datos: la transacción como la manda la pasarela (id, reference, status, amount_in_cents...).
    Devuelve el pago, o None si la referencia no existe o el monto no coincide.
    """
    with transaction.atomic():
        pago = (Pago.objects.select_for_update().select_related("pedido")
                .filter(referencia=datos.get("reference")).first())
        if pago is None or int(datos.get("amount_in_cents", -1)) != pasarela.en_centavos(pago.monto):
            return None
        estado = ESTADOS.get(datos.get("status"))
        if estado is None or pago.terminado:
            return pago  # sigue pendiente, o ya se había registrado (la pasarela puede reenviar el aviso)
        pago.estado = estado
        pago.transaccion_id = str(datos.get("id", ""))
        pago.detalle = str(datos.get("status_message") or datos.get("status", ""))[:200]
        pago.save()
        pedido = pago.pedido
        if estado == Pago.Estado.APROBADO:
            pedido.estado_pago = Pedido.EstadoPago.APROBADO
            pedido.save(update_fields=["estado_pago"])
        else:
            pedido.estado_pago = Pedido.EstadoPago.RECHAZADO
            pedido.save(update_fields=["estado_pago"])
            liberar_reservas(pedido)
    return pago


def liberar_reservas(pedido):
    """CA 2: si el pago se cancela o falla, se suelta lo que el pedido tenía apartado
    para que el cliente pueda volver a intentarlo con su carrito intacto:
    - las piezas únicas vuelven a estar a la venta (HU 08)
    - el código de descuento vuelve a quedar sin usar (HU 27)
    """
    from catalogo.models import Producto

    ids = [d.producto_id for d in pedido.detalles.all() if d.producto_id]
    Producto.objects.filter(pk__in=ids, pieza_unica=True, vendida=True).update(vendida=False)
    if pedido.codigo_descuento_id:
        codigo = pedido.codigo_descuento
        codigo.usado_en = None
        codigo.save(update_fields=["usado_en"])
        pedido.codigo_descuento = None
        pedido.save(update_fields=["codigo_descuento"])


def soltar_intentos_anteriores(usuario):
    """Si el cliente dejó un pago en línea a medias (cerró la ventana de la pasarela) y vuelve a
    comprar, ese intento se da por cancelado y se suelta lo que tenía apartado."""
    abandonados = Pedido.objects.filter(cliente=usuario, estado_pago=Pedido.EstadoPago.EN_PASARELA)
    for pedido in abandonados:
        pedido.pagos.filter(estado=Pago.Estado.PENDIENTE).update(
            estado=Pago.Estado.CANCELADO, detalle="El cliente no terminó el pago")
        pedido.estado_pago = Pedido.EstadoPago.RECHAZADO
        pedido.save(update_fields=["estado_pago"])
        liberar_reservas(pedido)
