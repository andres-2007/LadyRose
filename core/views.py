from django.shortcuts import render

from catalogo.models import Coleccion, Producto
from cursos.models import Curso

from .models import ConfiguracionTienda, ContenidoHistoria


def inicio(request):
    # Se muestran los próximos cursos; si no hay, los que ya se realizaron.
    proximos = list(Curso.objects.proximos().prefetch_related("fotos", "inscripciones")[:3])
    cursos = proximos or list(Curso.objects.realizados().prefetch_related("fotos")[:3])
    return render(request, "core/inicio.html", {
        "productos": Producto.objects.en_venta().select_related("categoria").prefetch_related("fotos")[:8],
        "colecciones": Coleccion.objects.filter(visible=True)[:3],
        "cursos": cursos,
        "cursos_son_realizados": not proximos,
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
    """HU 25 y HU 14: módulo mayorista con el monto mínimo vigente y el precio mayorista de cada referencia."""
    productos = (Producto.objects.mayoristas().select_related("categoria")
                 .prefetch_related("fotos", "tallas").order_by("categoria__nombre", "nombre"))
    categoria = request.GET.get("categoria", "")
    categorias = sorted({p.categoria for p in productos}, key=lambda c: c.nombre)
    if categoria:
        productos = productos.filter(categoria__slug=categoria)
    return render(request, "core/mayorista.html", {
        "monto_minimo": ConfiguracionTienda.obtener().monto_minimo_mayorista,
        "productos": productos,
        "categorias": categorias,
        "categoria_actual": categoria,
    })
