"""HU 22: datos del panel principal de la dueña.

Cada función hace la consulta en el momento en que se llama. Así el panel muestra
los datos al día cada vez que la dueña entra o recarga la página (CA 4).
"""
from datetime import datetime, time

from django.db.models import Count
from django.utils import timezone

from consultas.models import Consulta
from cotizaciones.models import SolicitudCotizacion
from pedidos.models import Pedido

from .models import VisitaOrigen


def pedidos_por_despachar():
    """CA 1: pedidos que todavía no han salido.

    No cuentan los que esperan el pago en línea o cuyo pago no se completó (HU 12),
    porque esos no se despachan hasta que el pago quede aprobado.
    """
    return Pedido.objects.para_produccion().filter(estado_envio=Pedido.EstadoEnvio.POR_DESPACHAR)


def resumen_pedidos():
    pendientes = pedidos_por_despachar()
    return {
        "total": pendientes.count(),
        # Los que la diseñadora ya terminó y solo falta enviar (HU 04)
        "listos": pendientes.filter(estado_produccion=Pedido.EstadoProduccion.TERMINADO).count(),
    }


def cotizaciones_sin_responder():
    """CA 1: solicitudes de cotización que siguen en "Nueva" (nadie las ha contactado, HU 28)."""
    return SolicitudCotizacion.objects.filter(consulta__estado=Consulta.Estado.NUEVA)


def resumen_cotizaciones():
    sin_responder = cotizaciones_sin_responder().select_related("consulta")
    return {
        "total": sin_responder.count(),
        # HU 28 CA 3: las que ya pasaron las 24 horas hábiles sin respuesta
        "atrasadas": sum(1 for s in sin_responder if s.consulta.sin_respuesta()),
    }


# ----------------------------------------------------------------------
# Visitas del día y del mes por canal (registro de la HU 31)
# ----------------------------------------------------------------------

def inicio_del_dia(hoy=None):
    hoy = hoy or timezone.localdate()
    return timezone.make_aware(datetime.combine(hoy, time.min))


def inicio_del_mes(hoy=None):
    hoy = hoy or timezone.localdate()
    return inicio_del_dia(hoy.replace(day=1))


def visitas_por_canal(desde):
    """CA 2: visitas desde una fecha, separadas por canal de llegada.

    Siempre salen Instagram, Facebook, TikTok, WhatsApp y Entrada directa (aunque
    tengan 0). "Otro" solo aparece si alguien llegó desde otro sitio.
    """
    conteo = dict(VisitaOrigen.objects.filter(fecha__gte=desde)
                  .values_list("canal").annotate(total=Count("id")).order_by())
    canales = [
        {"canal": valor, "nombre": nombre, "total": conteo.get(valor, 0)}
        for valor, nombre in VisitaOrigen.Canal.choices
        if valor != VisitaOrigen.Canal.OTRO or conteo.get(valor)
    ]
    return {"total": sum(conteo.values()), "canales": canales}


def visitas_hoy():
    return visitas_por_canal(inicio_del_dia())


def visitas_mes():
    return visitas_por_canal(inicio_del_mes())
