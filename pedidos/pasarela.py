"""HU 12: pasarela de pagos en línea (Nequi, PSE y Transferencia Bancolombia).

Pasarela escogida: Wompi (de Bancolombia). Es la que mejor se ajusta a Ladyrose
porque en un solo lugar recibe Nequi, PSE, el Botón Bancolombia y tarjetas, cobra
por transacción (sin mensualidad) y tiene un ambiente de pruebas (sandbox).

Por ahora el proyecto se entrega con una **pasarela de pruebas** que funciona
igual que el sandbox de Wompi, sin conectarse a internet:

1. La tienda crea el pago con una referencia única y lo firma (firma de integridad).
2. El cliente pasa a la página de la pasarela y aprueba, rechaza o cancela el pago.
3. La pasarela le avisa a la tienda con un *evento* firmado (como el webhook de
   Wompi). Solo ese evento puede dejar el pedido en "Pago aprobado".
4. El cliente vuelve a la tienda con el id de la transacción.

Cuando Ladyrose cree su cuenta de Wompi, basta con poner las llaves en el .env y
cambiar la URL de la página de pago por la de Wompi (https://checkout.wompi.co/p/).
"""
import hashlib
import secrets
import time

from django.conf import settings

MONEDA = "COP"


class EstadoTransaccion:
    """Estados de una transacción, con los mismos nombres que usa Wompi."""

    PENDIENTE = "PENDING"
    APROBADA = "APPROVED"
    RECHAZADA = "DECLINED"
    ANULADA = "VOIDED"
    ERROR = "ERROR"

    FINALES = {APROBADA, RECHAZADA, ANULADA, ERROR}


# Cómo llama Wompi a cada método de pago
TIPO_METODO = {"nequi": "NEQUI", "pse": "PSE", "bancolombia": "BANCOLOMBIA_TRANSFER"}


def config():
    return settings.LADYROSE["PASARELA"]


def en_centavos(valor):
    """Wompi recibe el monto en centavos: $95.000 -> 9500000."""
    return int(valor) * 100


def nueva_referencia(pedido):
    """Referencia única del pago, por ejemplo LR-0012-7K3QF2. Cada intento de pago tiene la suya."""
    return f"{pedido.numero}-{secrets.token_hex(3).upper()}"


def nuevo_id_transaccion():
    """Id de la transacción, con la forma de los de Wompi (por ejemplo 01-1531231271-19365)."""
    return f"01-{int(time.time())}-{secrets.randbelow(90000) + 10000}"


def _sha256(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def firma_integridad(referencia, monto_centavos, moneda=MONEDA):
    """Firma que evita que alguien cambie el monto o la referencia en el navegador.

    Igual que en Wompi: SHA256 de <referencia><monto en centavos><moneda><secreto de integridad>.
    """
    return _sha256(f"{referencia}{monto_centavos}{moneda}{config()['SECRETO_INTEGRIDAD']}")


def _valor(datos, ruta):
    """Lee un valor como "transaction.status" dentro de los datos del evento."""
    for parte in ruta.split("."):
        datos = datos[parte]
    return datos


def firma_evento(datos, propiedades, timestamp):
    """Checksum del evento, igual que en Wompi: SHA256 de los valores de las propiedades,
    el timestamp y el secreto de eventos, todo seguido."""
    texto = "".join(str(_valor(datos, p)) for p in propiedades) + str(timestamp) + config()["SECRETO_EVENTOS"]
    return _sha256(texto)


def evento_valido(evento):
    """Revisa que el evento venga de la pasarela (que la firma coincida)."""
    try:
        firma = evento["signature"]
        esperado = firma_evento(evento["data"], firma["properties"], evento["timestamp"])
    except (KeyError, TypeError):
        return False
    return secrets.compare_digest(esperado.lower(), str(firma.get("checksum", "")).lower())


def crear_evento(transaccion):
    """Evento "transaction.updated" con la misma forma que los de Wompi."""
    propiedades = ["transaction.id", "transaction.status", "transaction.amount_in_cents"]
    datos = {"transaction": transaccion}
    timestamp = int(time.time())
    return {
        "event": "transaction.updated",
        "data": datos,
        "environment": "test",
        "signature": {"properties": propiedades, "checksum": firma_evento(datos, propiedades, timestamp)},
        "timestamp": timestamp,
    }
