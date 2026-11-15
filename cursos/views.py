from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .excel import libro_inscritos
from .forms import InscripcionForm
from .models import Curso


def lista(request):
    cursos = Curso.objects.proximos().prefetch_related("fotos", "inscripciones")
    realizados = Curso.objects.realizados().prefetch_related("fotos")
    return render(request, "cursos/lista.html", {"cursos": cursos, "realizados": realizados})


def _datos_cuenta(usuario):
    """HU 27: la inscripción se llena con los datos de la cuenta."""
    if not usuario.is_authenticated:
        return {}
    cliente = getattr(usuario, "cliente", None)
    return {"nombre": usuario.get_full_name() or usuario.first_name, "correo": usuario.email,
            "whatsapp": cliente.whatsapp_contacto if cliente else ""}


def detalle(request, slug):
    curso = get_object_or_404(Curso.objects.publicados().prefetch_related("fotos"), slug=slug)
    form = InscripcionForm(curso=curso, initial=_datos_cuenta(request.user))
    if request.method == "POST":
        # HU 27: para inscribirse hay que tener cuenta
        if not request.user.is_authenticated:
            return redirect(f"{reverse('clientes:ingresar')}?next={curso.get_absolute_url()}")
        # Los cursos que ya se realizaron no reciben inscripciones.
        if curso.realizado:
            messages.error(request, "Este curso ya se realizó. Escríbenos para conocer las próximas fechas.")
            return redirect(curso.get_absolute_url())
        # HU 21: si no quedan cupos, no se aceptan inscripciones.
        if curso.agotado:
            messages.error(request, "Este curso está agotado.")
            return redirect(curso.get_absolute_url())
        datos = request.POST.copy()
        datos.setdefault("curso", str(curso.pk))
        if not datos.get("modalidad") and len(curso.modalidades_permitidas) == 1:
            datos["modalidad"] = curso.modalidades_permitidas[0]
        form = InscripcionForm(datos, curso=curso)
        if form.is_valid():
            inscripcion = form.save(commit=False)
            inscripcion.usuario = request.user
            inscripcion.save()
            messages.success(
                request,
                "¡Listo! Recibimos tu inscripción. Te escribiremos por WhatsApp para confirmar el pago "
                "y apartar tu cupo.",
            )
            return redirect(inscripcion.curso.get_absolute_url())
    return render(request, "cursos/detalle.html", {"curso": curso, "form": form})


@staff_member_required
@permission_required("cursos.view_inscripcion", raise_exception=True)
def descargar_inscritos(request, pk):
    """HU 26 CA 4: lista de inscritos en Excel."""
    curso = get_object_or_404(Curso, pk=pk)
    contenido = libro_inscritos([curso])
    respuesta = HttpResponse(
        contenido, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    respuesta["Content-Disposition"] = f'attachment; filename="inscritos-{curso.slug}.xlsx"'
    return respuesta
