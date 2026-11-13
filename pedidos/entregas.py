"""HU 07: tiempo estimado de fabricación y de envío.

Se suman en días hábiles (sin fines de semana ni festivos de Colombia) a partir
de hoy, y se arma el mensaje "Recibirás tu pedido aproximadamente entre el
[Fecha A] y el [Fecha B]".
"""
from dataclasses import dataclass
from datetime import date

from django.utils import timezone
from django.utils.formats import date_format

from catalogo.models import texto_dias_habiles
from core.festivos import sumar_dias_habiles
from core.models import ConfiguracionTienda

from .models import TiempoEnvio, normalizar_ciudad

AVISO_TRANSPORTADORA = (
    "El tiempo de envío a otras ciudades es aproximado porque depende de la transportadora. "
    "Ladyrose no se hace responsable por los retrasos causados por ella."
)


@dataclass
class EstimadoEntrega:
    ciudad: str
    fabricacion_min: int
    fabricacion_max: int
    envio_min: int
    envio_max: int
    por_transportadora: bool
    ciudad_en_tabla: bool
    fecha_desde: date
    fecha_hasta: date

    @property
    def tiempo_fabricacion(self):
        return texto_dias_habiles(self.fabricacion_min, self.fabricacion_max)

    @property
    def tiempo_envio(self):
        if self.envio_max == 0:
            return "El mismo día que la pieza queda lista"
        if self.envio_min == 0:
            return "Hasta " + texto_dias_habiles(self.envio_max, self.envio_max)
        return texto_dias_habiles(self.envio_min, self.envio_max)

    @property
    def mensaje(self):
        """HU 07 CA 3."""
        desde, hasta = _fecha_larga(self.fecha_desde), _fecha_larga(self.fecha_hasta)
        if self.fecha_desde == self.fecha_hasta:
            return f"Recibirás tu pedido aproximadamente el {desde}."
        return f"Recibirás tu pedido aproximadamente entre el {desde} y el {hasta}."

    @property
    def aviso(self):
        """HU 07 CA 4: solo para los envíos por transportadora."""
        return AVISO_TRANSPORTADORA if self.por_transportadora else ""

    def como_dict(self):
        return {
            "ciudad": self.ciudad,
            "tiempo_fabricacion": self.tiempo_fabricacion,
            "tiempo_envio": self.tiempo_envio,
            "fecha_desde": self.fecha_desde.isoformat(),
            "fecha_hasta": self.fecha_hasta.isoformat(),
            "mensaje": self.mensaje,
            "aviso": self.aviso,
            "por_transportadora": self.por_transportadora,
        }


def _fecha_larga(fecha):
    # Ej.: "martes 17 de noviembre"
    return date_format(fecha, r"l j \d\e F").lower()


def tiempos_fabricacion(productos):
    """El pedido sale cuando está lista la pieza que más se demora.

    Las piezas se hacen en paralelo, así que se toma el mayor mínimo y el mayor
    máximo de los productos del carrito.
    """
    productos = [p for p in productos if p is not None]
    if not productos:
        return 0, 0
    minimo = max((p.dias_fabricacion_min or p.dias_elaboracion) for p in productos)
    maximo = max(p.dias_elaboracion for p in productos)
    return min(minimo, maximo), maximo


def tiempo_envio(ciudad):
    """(mínimo, máximo, por_transportadora, fila de la tabla o None) para la ciudad de destino."""
    fila = TiempoEnvio.objects.filter(ciudad_normalizada=normalizar_ciudad(ciudad)).first()
    if fila:
        return fila.dias_min, fila.dias_max, fila.por_transportadora, fila
    config = ConfiguracionTienda.obtener()
    return config.envio_otras_ciudades_min, config.envio_otras_ciudades_max, True, None


def estimar_entrega(productos, ciudad, desde=None):
    """HU 07 CA 2 y CA 3: suma la fabricación y el envío en días hábiles desde hoy."""
    ciudad = " ".join((ciudad or "").split())
    if not ciudad:
        return None
    desde = desde or timezone.localdate()
    fab_min, fab_max = tiempos_fabricacion(productos)
    env_min, env_max, transportadora, fila = tiempo_envio(ciudad)
    return EstimadoEntrega(
        # Si la ciudad está en la tabla se muestra como la escribió la dueña ("bogota" -> "Bogotá")
        ciudad=fila.ciudad if fila else ciudad, fabricacion_min=fab_min, fabricacion_max=fab_max,
        envio_min=env_min, envio_max=env_max, por_transportadora=transportadora, ciudad_en_tabla=bool(fila),
        fecha_desde=sumar_dias_habiles(desde, fab_min + env_min),
        fecha_hasta=sumar_dias_habiles(desde, fab_max + env_max),
    )
