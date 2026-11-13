from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import IngresarForm, RegistroForm

URL_INGRESAR = "clientes:ingresar"


def _siguiente(request, por_defecto="clientes:mi_cuenta"):
    destino = request.POST.get("next") or request.GET.get("next")
    if destino and url_has_allowed_host_and_scheme(destino, {request.get_host()}, request.is_secure()):
        return destino
    return por_defecto


def registro(request):
    """HU 27 CA 6 y CA 3."""
    if request.user.is_authenticated:
        return redirect(_siguiente(request))
    form = RegistroForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.save()
        login(request, usuario, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, f"¡Bienvenida, {usuario.first_name.split()[0]}! Tu cuenta quedó creada.")
        return redirect(_siguiente(request))
    return render(request, "clientes/registro.html", {"form": form, "next": _siguiente(request, "")})


def ingresar(request):
    """HU 27 CA 6."""
    if request.user.is_authenticated:
        return redirect(_siguiente(request))
    form = IngresarForm(request.POST or None, request=request)
    if request.method == "POST" and form.is_valid():
        # El carrito se conserva al iniciar sesión
        carrito = request.session.get("carrito")
        login(request, form.usuario)
        if carrito:
            request.session["carrito"] = carrito
        return redirect(_siguiente(request))
    return render(request, "clientes/ingresar.html", {"form": form, "next": _siguiente(request, "")})


@require_POST
def salir(request):
    logout(request)
    messages.info(request, "Cerraste sesión.")
    return redirect("core:inicio")


@login_required(login_url=URL_INGRESAR)
def mi_cuenta(request):
    """El cliente ve sus códigos de descuento disponibles y sus pedidos."""
    cliente = getattr(request.user, "cliente", None)
    hoy = timezone.localdate()
    contexto = {"cliente": cliente}
    if cliente:
        contexto.update({
            "codigos": cliente.codigos_disponibles(hoy).order_by("vence"),
            "pedidos": cliente.pedidos().order_by("-creado")[:10],
        })
    return render(request, "clientes/mi_cuenta.html", contexto)
