from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.mail import send_mail
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from catalogo.models import Producto, TallaProducto, texto_dias_habiles
from clientes.models import CodigoDescuento, CodigoInvalido
from clientes.views import URL_INGRESAR
from core.templatetags.ladyrose import pesos

from .carrito import Carrito, ErrorCarrito
from .entregas import estimar_entrega, tiempos_fabricacion
from .forms import AvisoClienteForm, PedidoForm
from .models import DetallePedido, Pedido, TiempoEnvio, TipoEmpaque

ESTADOS_SELECTOR = [
    (Pedido.EstadoProduccion.PENDIENTE, "Pendiente"),
    (Pedido.EstadoProduccion.EN_CURSO, "En curso"),
    (Pedido.EstadoProduccion.TERMINADO, "Terminado"),
]


# ------------------------------------------------------------------
# Carrito (HU 24) y selección de talla (HU 19)
# ------------------------------------------------------------------

def carrito(request):
    c = Carrito(request)
    items = c.items()
    return render(request, "pedidos/carrito.html", {
        "items": items,
        "subtotal": sum((i["subtotal"] for i in items), 0),
    })


@require_POST
def agregar(request, producto_id):
    producto = get_object_or_404(Producto, pk=producto_id)
    talla = None
    talla_id = request.POST.get("talla")
    if talla_id:
        talla = TallaProducto.objects.filter(pk=talla_id, producto=producto).first()
    try:
        cantidad = int(request.POST.get("cantidad", 1))
    except ValueError:
        cantidad = 1
    try:
        Carrito(request).agregar(producto, talla, request.POST.get("color", ""), cantidad)
    except ErrorCarrito as error:
        messages.error(request, str(error))
        return redirect(producto.get_absolute_url())
    messages.success(request, f"Agregaste {producto.nombre} a tu carrito.")
    if request.POST.get("siguiente") == "pagar":
        return redirect("pedidos:pagar")
    return redirect("pedidos:carrito")


@require_POST
def actualizar(request):
    c = Carrito(request)
    try:
        c.actualizar(request.POST.get("clave", ""), int(request.POST.get("cantidad", 1)))
    except ValueError:
        pass
    return redirect("pedidos:carrito")


@require_POST
def quitar(request):
    Carrito(request).quitar(request.POST.get("clave", ""))
    return redirect("pedidos:carrito")


# ------------------------------------------------------------------
# Proceso de pago (HU 24 y HU 11)
# ------------------------------------------------------------------

def _datos_cuenta(usuario):
    """HU 27: el pago se llena con los datos de la cuenta del cliente."""
    cliente = getattr(usuario, "cliente", None)
    telefono = cliente.whatsapp_contacto if cliente else ""
    return {"nombre": usuario.get_full_name() or usuario.first_name, "correo": usuario.email,
            "telefono": telefono, "whatsapp_igual": True}


@login_required(login_url=URL_INGRESAR)  # HU 27: para comprar hay que tener cuenta
def pagar(request):
    c = Carrito(request)
    items = c.items()
    if not items:
        messages.info(request, "Tu carrito está vacío.")
        return redirect("catalogo:lista")
    subtotal = sum((i["subtotal"] for i in items), 0)
    form = PedidoForm(request.POST or None, request.FILES or None, usuario=request.user,
                      initial=None if request.method == "POST" else _datos_cuenta(request.user))
    if request.method == "POST" and form.is_valid():
        try:
            pedido = _crear_pedido(request, form, items, subtotal)
        except ErrorCarrito as error:
            messages.error(request, str(error))
            return redirect("pedidos:carrito")
        except CodigoInvalido as error:
            form.add_error("codigo", str(error))
        else:
            c.vaciar()
            confirmados = request.session.get("pedidos_confirmados", [])
            request.session["pedidos_confirmados"] = confirmados + [pedido.pk]
            return redirect("pedidos:confirmado", pk=pedido.pk)
    productos = [i["producto"] for i in items]
    codigo = form.codigo_descuento if form.is_bound and not form.errors.get("codigo") else None
    return render(request, "pedidos/pagar.html", {
        "form": form, "items": items, "subtotal": subtotal,
        # HU 27: descuento del código que ya se validó (si la página vuelve con otros errores)
        "descuento": codigo.calcular(subtotal) if codigo else 0,
        "empaques": TipoEmpaque.objects.filter(activo=True),
        "datos_transferencia": settings.LADYROSE["DATOS_TRANSFERENCIA"],
        # HU 07: tiempo de fabricación del carrito y, si ya hay ciudad, la fecha estimada
        "estimado": estimar_entrega(productos, form["ciudad"].value()),
        "tiempo_fabricacion_carrito": texto_dias_habiles(*tiempos_fabricacion(productos)),
        "ciudades_envio": TiempoEnvio.objects.values_list("ciudad", flat=True),
    })


@require_GET
@login_required(login_url=URL_INGRESAR)
def aplicar_codigo(request):
    """HU 27: revisa el código que escribe el cliente y devuelve cuánto se descuenta."""
    items = Carrito(request).items()
    subtotal = sum((i["subtotal"] for i in items), 0)
    try:
        codigo = CodigoDescuento.buscar(request.GET.get("codigo", ""), request.user)
    except CodigoInvalido as error:
        return JsonResponse({"ok": False, "mensaje": str(error)})
    descuento = codigo.calcular(subtotal)
    return JsonResponse({
        "ok": True, "codigo": codigo.codigo, "descuento": int(descuento),
        "mensaje": f"Código aplicado: {codigo.descuento_texto} ({pesos(descuento)} menos en tus productos).",
    })


@require_GET
def estimar(request):
    """HU 07 CA 2 y CA 3: tiempo de envío y fechas estimadas para la ciudad que escribe el cliente."""
    productos = [i["producto"] for i in Carrito(request).items()]
    estimado = estimar_entrega(productos, request.GET.get("ciudad", ""))
    if not productos or estimado is None:
        return JsonResponse({"ok": False})
    return JsonResponse({"ok": True, **estimado.como_dict()})


def _crear_pedido(request, form, items, subtotal):
    with transaction.atomic():
        # Las piezas únicas se bloquean para que dos personas no compren la misma (HU 08)
        ids_unicas = [i["producto"].pk for i in items if i["producto"].pieza_unica]
        unicas = Producto.objects.select_for_update().filter(pk__in=ids_unicas)
        if any(p.vendida for p in unicas):
            raise ErrorCarrito("Una de las piezas únicas de tu carrito se acaba de vender.")

        pedido = form.save(commit=False)
        pedido.cliente = request.user
        pedido.subtotal = subtotal
        pedido.costo_empaque = pedido.empaque.costo if pedido.empaque else 0
        # HU 27: el código se bloquea y se vuelve a revisar para que no se use dos veces al mismo tiempo
        if form.codigo_descuento:
            codigo = CodigoDescuento.objects.select_for_update().get(pk=form.codigo_descuento.pk)
            codigo.validar_para(request.user)
            pedido.descuento = codigo.calcular(subtotal)
        pedido.total = subtotal - pedido.descuento + pedido.costo_empaque
        pedido.canal_origen = request.session.get("canal_origen", "")
        pedido.save()
        for i in items:
            p = i["producto"]
            DetallePedido.objects.create(
                pedido=pedido, producto=p, referencia=p.nombre,
                talla=str(i["talla"]) if i["talla"] else "", color=i["color"], material=p.material,
                cantidad=i["cantidad"], precio_unitario=i["precio"],
            )
        pedido.calcular_produccion()
        pedido.save()
        # HU 27 CA 2: el código queda usado al confirmar el pedido
        if form.codigo_descuento:
            codigo.usado_en = timezone.now()
            codigo.save(update_fields=["usado_en"])
            pedido.codigo_descuento = codigo
            pedido.save(update_fields=["codigo_descuento"])
        # HU 08: la pieza única vendida pasa a la galería
        unicas.update(vendida=True)
    return pedido


def confirmado(request, pk):
    if pk not in request.session.get("pedidos_confirmados", []):
        raise Http404
    pedido = get_object_or_404(Pedido, pk=pk)
    return render(request, "pedidos/confirmado.html", {
        "pedido": pedido,
        "datos_transferencia": settings.LADYROSE["DATOS_TRANSFERENCIA"],
    })


# ------------------------------------------------------------------
# Panel de producción de la diseñadora (HU 01, 03, 04 y 10)
# ------------------------------------------------------------------

def _panel(vista):
    """Solo entra el personal con permiso de ver pedidos (dueña y diseñadora)."""
    vista = permission_required("pedidos.view_pedido", raise_exception=True)(vista)
    return login_required(vista, login_url="admin:login")


def _puede_cambiar(request):
    return request.user.has_perm("pedidos.change_pedido")


@_panel
def panel(request):
    pendientes = (Pedido.objects.exclude(estado_produccion=Pedido.EstadoProduccion.TERMINADO)
                  .prefetch_related("detalles__producto__fotos").select_related("empaque"))
    # HU 01 CA 2: dos formas de ordenar independientes
    orden = request.GET.get("orden", "fecha")
    if orden == "tecnica":
        pendientes = pendientes.order_by("tecnica", "-dias_elaboracion", "fecha_limite")
    else:
        orden = "fecha"
        pendientes = pendientes.order_by("fecha_limite", "creado")
    tecnica = request.GET.get("tecnica", "")
    if tecnica:
        pendientes = pendientes.filter(tecnica__icontains=tecnica)
    tecnicas = sorted({t.strip() for valor in Pedido.objects.exclude(tecnica="")
                       .exclude(estado_produccion=Pedido.EstadoProduccion.TERMINADO)
                       .values_list("tecnica", flat=True) for t in valor.split(",") if t.strip()})
    # HU 04 CA 2: lo terminado sale de la lista y queda en "Listos para envío"
    listos = (Pedido.objects.filter(estado_produccion=Pedido.EstadoProduccion.TERMINADO,
                                    estado_envio=Pedido.EstadoEnvio.POR_DESPACHAR)
              .prefetch_related("detalles__producto__fotos").order_by("fecha_limite"))
    return render(request, "pedidos/panel/lista.html", {
        "pendientes": pendientes, "listos": listos, "orden": orden,
        "tecnicas": tecnicas, "tecnica_actual": tecnica,
        "estados": ESTADOS_SELECTOR, "puede_cambiar": _puede_cambiar(request),
    })


@_panel
def panel_detalle(request, pk):
    pedido = get_object_or_404(
        Pedido.objects.select_related("empaque", "cotizacion").prefetch_related(
            "detalles__producto__fotos", "cotizacion__imagenes"), pk=pk)
    mensaje = (
        f"Hola {pedido.nombre.split()[0]}, te escribimos de Ladyrose por tu pedido {pedido.numero}. "
        "Uno de los insumos que necesitamos para tu pieza se agotó en el comercio. "
        "Te proponemos estas alternativas: "
    )
    return render(request, "pedidos/panel/detalle.html", {
        "pedido": pedido,
        "estados": ESTADOS_SELECTOR,
        "puede_cambiar": _puede_cambiar(request),
        "form_aviso": AvisoClienteForm(initial={"mensaje": mensaje}),
    })


@_panel
@require_POST
def cambiar_estado(request, pk):
    """HU 04: guarda el estado sin salir del panel."""
    if not _puede_cambiar(request):
        return JsonResponse({"ok": False, "error": "No tienes permiso para cambiar el estado."}, status=403)
    pedido = get_object_or_404(Pedido, pk=pk)
    estado = request.POST.get("estado")
    if estado not in dict(ESTADOS_SELECTOR):
        return JsonResponse({"ok": False, "error": "Estado no válido."}, status=400)
    pedido.cambiar_estado(estado)
    if request.headers.get("x-requested-with") == "fetch":
        return JsonResponse({"ok": True, "estado": estado, "etiqueta": pedido.get_estado_produccion_display(),
                             "terminado": estado == Pedido.EstadoProduccion.TERMINADO})
    messages.success(request, f"El pedido {pedido.numero} quedó en \"{pedido.get_estado_produccion_display()}\".")
    return redirect(request.POST.get("volver") or "pedidos:panel")


@_panel
@require_POST
def avisar_cliente(request, pk):
    """HU 10: aviso por falta de insumos. El pedido queda en pausa."""
    if not _puede_cambiar(request):
        raise Http404
    pedido = get_object_or_404(Pedido, pk=pk)
    form = AvisoClienteForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Escribe el mensaje para el cliente.")
        return redirect(pedido.get_absolute_url())
    mensaje = form.cleaned_data["mensaje"]
    if form.cleaned_data["canal"] == "correo":
        if not pedido.correo:
            messages.error(request, "Este cliente no dejó correo. Usa WhatsApp.")
            return redirect(pedido.get_absolute_url())
        send_mail(f"Tu pedido {pedido.numero} en Ladyrose", mensaje, None, [pedido.correo])
        pedido.cambiar_estado(Pedido.EstadoProduccion.EN_PAUSA)
        messages.success(request, f"Le enviamos el correo a {pedido.correo}. El pedido quedó en pausa.")
        return redirect(pedido.get_absolute_url())
    pedido.cambiar_estado(Pedido.EstadoProduccion.EN_PAUSA)
    return redirect(f"https://wa.me/{pedido.whatsapp_internacional}?text={quote(mensaje)}")


@_panel
@require_POST
def reanudar(request, pk):
    """HU 10 CA 3: cuando el cliente responde, el pedido vuelve a "En curso"."""
    if not _puede_cambiar(request):
        raise Http404
    pedido = get_object_or_404(Pedido, pk=pk)
    pedido.cambiar_estado(Pedido.EstadoProduccion.EN_CURSO)
    messages.success(request, f"El pedido {pedido.numero} volvió a \"En curso\".")
    return redirect(pedido.get_absolute_url())
