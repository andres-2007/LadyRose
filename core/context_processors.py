from django.conf import settings


def datos_tienda(request):
    from pedidos.carrito import CLAVE_SESION

    lineas = request.session.get(CLAVE_SESION, {}) if hasattr(request, "session") else {}
    return {
        "LADYROSE": settings.LADYROSE,
        "CANTIDAD_CARRITO": sum(lineas.values()),
    }
