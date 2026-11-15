from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from catalogo.models import Producto
from cursos.models import Curso

from .forms import PreguntaForm
from .models import Consulta


def _guardar_pregunta(request, origen, objeto, **relacion):
    form = PreguntaForm(request.POST)
    if form.is_valid():
        consulta = form.save(commit=False)
        consulta.origen = origen
        consulta.usuario = request.user if request.user.is_authenticated else None
        consulta.correo = request.user.email if request.user.is_authenticated else ""
        for campo, valor in relacion.items():
            setattr(consulta, campo, valor)
        consulta.save()
        messages.success(request, "¡Recibimos tu pregunta! Te respondemos por WhatsApp en menos de "
                                  f"{settings.LADYROSE['TIEMPO_RESPUESTA']}.")
        return redirect(objeto.get_absolute_url() + "#preguntanos")
    return render(request, "consultas/preguntar.html", {"form": form, "objeto": objeto})


@require_POST
def preguntar_producto(request, slug):
    """HU 28 CA 1: pregunta por un producto desde su ficha."""
    producto = get_object_or_404(Producto.objects.visibles(), slug=slug)
    return _guardar_pregunta(request, Consulta.Origen.PRODUCTO, producto, producto=producto)


@require_POST
def preguntar_curso(request, slug):
    """HU 28 CA 1: pregunta por un curso desde su página."""
    curso = get_object_or_404(Curso.objects.publicados(), slug=slug)
    return _guardar_pregunta(request, Consulta.Origen.CURSO, curso, curso=curso)
