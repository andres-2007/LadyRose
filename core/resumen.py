"""HU 22: datos del panel principal de la dueña.

Cada función hace la consulta en el momento en que se llama. Así el panel muestra
los datos al día cada vez que la dueña entra o recarga la página (CA 4).
"""
from consultas.models import Consulta
from cotizaciones.models import SolicitudCotizacion
from pedidos.models import Pedido


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
