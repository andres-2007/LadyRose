from django.shortcuts import get_object_or_404, render

from .models import AVISO_CUIDADOS, TEXTO_PH, Categoria, Coleccion, Producto

# HU 08: aviso de las piezas de la galería
AVISO_GALERIA = (
    "Esta pieza ya tiene dueña. Podemos hacerte una inspirada en ella, pero replicarla "
    "depende de que los insumos todavía existan en el mercado."
)

ORDENES = {
    "nuevos": ("-creado", "Lo más nuevo"),
    "menor": ("precio", "Menor precio"),
    "mayor": ("-precio", "Mayor precio"),
}


def lista(request):
    productos = (Producto.objects.en_venta().select_related("categoria")
                 .prefetch_related("fotos", "tallas"))
    categoria = coleccion = None
    if request.GET.get("categoria"):
        categoria = get_object_or_404(Categoria, slug=request.GET["categoria"])
        productos = productos.filter(categoria=categoria)
    # HU 16: el catálogo se filtra por la colección elegida
    if request.GET.get("coleccion"):
        coleccion = get_object_or_404(Coleccion, slug=request.GET["coleccion"], visible=True)
        productos = productos.filter(colecciones=coleccion)
    orden = request.GET.get("orden", "nuevos")
    if orden not in ORDENES:
        orden = "nuevos"
    productos = productos.order_by(ORDENES[orden][0])
    return render(request, "catalogo/lista.html", {
        "productos": productos,
        "categorias": Categoria.objects.all(),
        "categoria_actual": categoria,
        "coleccion_actual": coleccion,
        "orden": orden,
        "ordenes": [(k, v[1]) for k, v in ORDENES.items()],
    })


def detalle(request, slug):
    # Los productos ocultos (HU 15) no se pueden ver en la página pública.
    producto = get_object_or_404(
        Producto.objects.visibles().select_related("categoria").prefetch_related("fotos", "tallas", "colecciones"),
        slug=slug,
    )
    relacionados = (Producto.objects.en_venta().filter(categoria=producto.categoria)
                    .exclude(pk=producto.pk).prefetch_related("fotos")[:4])
    return render(request, "catalogo/detalle.html", {
        "producto": producto,
        "aviso_cuidados": AVISO_CUIDADOS,
        "texto_ph": TEXTO_PH,
        "aviso_galeria": AVISO_GALERIA,
        "relacionados": relacionados,
    })


def colecciones(request):
    """HU 16: página de colecciones."""
    return render(request, "catalogo/colecciones.html", {
        "colecciones": Coleccion.objects.filter(visible=True),
    })


def galeria(request):
    """HU 08: galería de piezas vendidas."""
    return render(request, "catalogo/galeria.html", {
        "piezas": Producto.objects.galeria().prefetch_related("fotos").order_by("-actualizado"),
        "aviso_galeria": AVISO_GALERIA,
    })
