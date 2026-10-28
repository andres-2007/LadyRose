from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from catalogo.models import Producto

from .forms import CotizacionForm, InspiradaForm, PersonalizarProductoForm
from .models import ImagenReferencia, SolicitudCotizacion


def _guardar(form, **extra):
    with transaction.atomic():
        solicitud = form.save(commit=False)
        for campo, valor in extra.items():
            setattr(solicitud, campo, valor)
        solicitud.acepta_pieza_unica = True
        solicitud.fecha_aceptacion = timezone.now()
        solicitud.save()
        for imagen in form.cleaned_data.get("imagenes", []):
            ImagenReferencia.objects.create(solicitud=solicitud, imagen=imagen)
    return solicitud


def cotizar(request):
    """HU 09 y HU 20: formulario de cotización de una pieza personalizada."""
    form = CotizacionForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        _guardar(form, tipo=SolicitudCotizacion.Tipo.PERSONALIZADA)
        return redirect("cotizaciones:gracias")
    return render(request, "cotizaciones/formulario.html", {"form": form})


def personalizar(request, slug):
    """HU 34: el cliente pide cambios sobre un producto del catálogo."""
    producto = get_object_or_404(Producto.objects.visibles(), slug=slug)
    form = PersonalizarProductoForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        _guardar(form, tipo=SolicitudCotizacion.Tipo.CAMBIOS_PRODUCTO, producto=producto)
        return redirect("cotizaciones:gracias")
    return render(request, "cotizaciones/formulario.html", {"form": form, "producto": producto})


def inspirada(request, slug):
    """HU 08: cotizar una pieza inspirada en otra de la galería."""
    producto = get_object_or_404(Producto.objects.galeria(), slug=slug)
    form = InspiradaForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        _guardar(form, tipo=SolicitudCotizacion.Tipo.INSPIRADA, producto=producto)
        return redirect("cotizaciones:gracias")
    return render(request, "cotizaciones/formulario.html", {"form": form, "producto": producto, "inspirada": True})


def gracias(request):
    # HU 34: mensaje de confirmación con el tiempo estimado de respuesta
    return render(request, "cotizaciones/gracias.html", {
        "tiempo_respuesta": settings.LADYROSE["TIEMPO_RESPUESTA"],
    })
