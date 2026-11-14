"""HU 30: costo de envío según la zona.

- Cali, barrio de una zona activa: la tarifa fija de la zona (puede ser $0, envío gratis).
- Cali, barrio fuera de las zonas: "Domicilio por confirmar" (depende de la hora y la distancia).
- Otras ciudades (también Jamundí, Yumbo, Palmira...): según el peso total del pedido y la
  tabla de tarifas por peso. Si no hay tabla o el pedido pesa más que el último rango,
  queda "Envío por confirmar".

Cuando queda por confirmar, la dueña registra el valor en el panel y el cliente recibe un aviso
antes del despacho.
"""
from dataclasses import dataclass
from decimal import Decimal

from .models import BarrioZona, Pedido, TarifaPeso, normalizar_ciudad

CIUDADES_CALI = {"cali", "santiago de cali"}

MENSAJE_CALI_POR_CONFIRMAR = (
    "Domicilio por confirmar: en Cali el valor depende de la hora y de la distancia. "
    "Te avisamos el valor antes de despachar tu pedido."
)
MENSAJE_OTRA_CIUDAD_POR_CONFIRMAR = (
    "Envío por confirmar: lo calculamos con Servientrega según el peso de tu pedido "
    "y te avisamos el valor antes de despacharlo."
)
MENSAJE_TRANSFERENCIA_POR_CONFIRMAR = (
    "Como el envío está por confirmar, no transfieras todavía. Cuando te confirmemos el valor "
    "te enviamos un enlace para pagar el total y subir el comprobante."
)

Estado = Pedido.EstadoEnvioCosto


def es_cali(ciudad):
    return normalizar_ciudad(ciudad) in CIUDADES_CALI


def barrio_en_zona(barrio):
    """El barrio de una zona activa que coincide con lo que escribió el cliente (sin tildes ni mayúsculas)."""
    normalizado = normalizar_ciudad(barrio)
    if not normalizado:
        return None
    return (BarrioZona.objects.select_related("zona")
            .filter(nombre_normalizado=normalizado, zona__activa=True).first())


def peso_total(items):
    """items: lista de (producto, cantidad)."""
    return sum((producto.peso or 0) * cantidad for producto, cantidad in items if producto is not None)


@dataclass
class Envio:
    estado: str
    valor: Decimal | None
    peso: int
    detalle: str
    mensaje: str = ""

    @property
    def por_confirmar(self):
        return self.estado == Estado.POR_CONFIRMAR

    def como_dict(self):
        return {"estado": self.estado, "valor": int(self.valor) if self.valor is not None else None,
                "peso": self.peso, "detalle": self.detalle, "mensaje": self.mensaje,
                "por_confirmar": self.por_confirmar}


def calcular_envio(items, ciudad, barrio=""):
    """HU 30: costo del envío para los productos del carrito y la dirección del cliente."""
    peso = peso_total(items)
    if es_cali(ciudad):
        encontrado = barrio_en_zona(barrio)
        if encontrado:
            zona = encontrado.zona
            detalle = f"Zona {zona.nombre} ({encontrado.nombre})"
            mensaje = "Domicilio gratis en tu zona." if zona.tarifa == 0 else f"Tarifa fija de la zona {zona.nombre}."
            return Envio(Estado.CALCULADO, zona.tarifa, peso, detalle, mensaje)
        return Envio(Estado.POR_CONFIRMAR, None, peso, "Cali, fuera de las zonas con tarifa fija",
                     MENSAJE_CALI_POR_CONFIRMAR)
    tarifa = TarifaPeso.objects.filter(peso_hasta__gte=peso).order_by("peso_hasta").first()
    if tarifa:
        return Envio(Estado.CALCULADO, tarifa.valor, peso, f"Servientrega, {peso} g (hasta {tarifa.peso_hasta} g)",
                     f"Según el peso de tu pedido ({peso} g).")
    return Envio(Estado.POR_CONFIRMAR, None, peso, f"Otra ciudad, {peso} g (sin tarifa para ese peso)",
                 MENSAJE_OTRA_CIUDAD_POR_CONFIRMAR)
