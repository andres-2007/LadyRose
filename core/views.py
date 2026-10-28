from django.shortcuts import render

from catalogo.models import Coleccion, Producto
from cursos.models import Curso

from .models import ConfiguracionTienda, ContenidoHistoria


def inicio(request):
    return render(request, "core/inicio.html", {
        "productos": Producto.objects.en_venta().select_related("categoria").prefetch_related("fotos")[:8],
        "colecciones": Coleccion.objects.filter(visible=True)[:3],
        "cursos": Curso.objects.publicados().prefetch_related("fotos", "inscripciones")[:3],
        "galeria": Producto.objects.galeria().prefetch_related("fotos")[:4],
        "lema": ContenidoHistoria.LEMA,
    })


def historia(request):
    """HU 18: sección "Nuestra historia"."""
    return render(request, "core/historia.html", {
        "historia": ContenidoHistoria.obtener(),
        "lema": ContenidoHistoria.LEMA,
    })


def mayorista(request):
    """HU 25: página del módulo mayorista con el monto mínimo vigente.

    El carrito mayorista se construye en la HU 14 (Sprint 3).
    """
    return render(request, "core/mayorista.html", {
        "monto_minimo": ConfiguracionTienda.obtener().monto_minimo_mayorista,
    })
