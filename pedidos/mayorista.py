"""HU 14: reglas del pedido al por mayor.

El pedido mayorista se puede confirmar cuando el subtotal llega al monto mínimo
vigente que configura la dueña (HU 25). Si no llega, se le muestra a la persona
cuánto dinero le falta.
"""
from dataclasses import dataclass
from decimal import Decimal

from core.models import ConfiguracionTienda


@dataclass
class EstadoMinimo:
    minimo: Decimal
    subtotal: Decimal

    @property
    def alcanza(self):
        return self.subtotal >= self.minimo

    @property
    def falta(self):
        return max(self.minimo - self.subtotal, Decimal(0))

    @property
    def porcentaje(self):
        """Qué tanto del mínimo lleva (de 0 a 100), para la barra de avance."""
        if not self.minimo:
            return 100
        return min(int(self.subtotal * 100 / self.minimo), 100)


def estado_minimo(subtotal):
    return EstadoMinimo(ConfiguracionTienda.obtener().monto_minimo_mayorista, Decimal(subtotal or 0))
