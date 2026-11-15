import json
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.mail import send_mail
from django.db import transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from catalogo.models import Producto, TallaProducto, texto_dias_habiles
from clientes.models import CodigoDescuento, CodigoInvalido
from clientes.views import URL_INGRESAR
from core.templatetags.ladyrose import pesos

from . import pagos, pasarela
from .carrito import Carrito, CarritoMayorista, ErrorCarrito
from .entregas import estimar_entrega, tiempos_fabricacion
from .envios import (MENSAJE_SIN_CONTRA_ENTREGA, MENSAJE_TRANSFERENCIA_POR_CONFIRMAR, calcular_envio,
                     permite_contra_entrega)
from .mayorista import estado_minimo
from .precotizacion import generar_pdf, numero_precotizacion
from .forms import AvisoClienteForm, ComprobanteForm, PedidoForm
from .models import DetallePedido, Pago, Pedido, TiempoEnvio, TipoEmpaque

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


def _agregar(request, carrito, producto):
    """Agrega el producto con la talla, el color y la cantidad que vienen del formulario."""
    talla = None
    talla_id = request.POST.get("talla")
    if talla_id:
        talla = TallaProducto.objects.filter(pk=talla_id, producto=producto).first()
    try:
        cantidad = int(request.POST.get("cantidad", 1))
    except ValueError:
        cantidad = 1
    carrito.agregar(producto, talla, request.POST.get("color", ""), cantidad)


@require_POST
def agregar(request, producto_id):
    producto = get_object_or_404(Producto, pk=producto_id)
    try:
        _agregar(request, Carrito(request), producto)
    except ErrorCarrito as error:
        messages.error(request, str(error))
        return redirect(producto.get_absolute_url())
    messages.success(request, f"Agregaste {producto.nombre} a tu carrito.")
    if request.POST.get("siguiente") == "pagar":
        return redirect("pedidos:pagar")
    return redirect("pedidos:carrito")


def _actualizar(request, carrito):
    try:
        carrito.actualizar(request.POST.get("clave", ""), int(request.POST.get("cantidad", 1)))
    except ValueError:
        pass


@require_POST
def actualizar(request):
    _actualizar(request, Carrito(request))
    return redirect("pedidos:carrito")


@require_POST
def quitar(request):
    Carrito(request).quitar(request.POST.get("clave", ""))
    return redirect("pedidos:carrito")


# ------------------------------------------------------------------
# Pedido al por mayor (HU 14): carrito separado del carrito al detal
# ------------------------------------------------------------------

def carrito_mayorista(request):
    c = CarritoMayorista(request)
    items = c.items()
    subtotal = sum((i["subtotal"] for i in items), 0)
    return render(request, "pedidos/carrito_mayorista.html", {
        "items": items,
        "subtotal": subtotal,
        # HU 14 CA 3: cuánto falta para llegar al monto mínimo
        "minimo": estado_minimo(subtotal),
    })


@require_POST
def agregar_mayorista(request, producto_id):
    producto = get_object_or_404(Producto, pk=producto_id)
    try:
        _agregar(request, CarritoMayorista(request), producto)
    except ErrorCarrito as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"Agregaste {producto.nombre} a tu pedido al por mayor.")
    if request.POST.get("siguiente") == "pedido":
        return redirect("pedidos:carrito_mayorista")
    return redirect(reverse("core:mayorista") + f"#ref-{producto.pk}")


def precotizacion_mayorista(request):
    """HU 14 CA 4: descarga la vista previa del pedido al por mayor como pre-cotización en PDF."""
    items = CarritoMayorista(request).items()
    if not items:
        messages.info(request, "Agrega referencias a tu pedido para descargar la pre-cotización.")
        return redirect("pedidos:carrito_mayorista")
    subtotal = sum((i["subtotal"] for i in items), 0)
    ahora = timezone.localtime()
    pdf = generar_pdf(items, estado_minimo(subtotal), usuario=request.user, ahora=ahora)
    respuesta = HttpResponse(pdf, content_type="application/pdf")
    respuesta["Content-Disposition"] = f'attachment; filename="ladyrose-{numero_precotizacion(ahora)}.pdf"'
    return respuesta


@require_POST
def actualizar_mayorista(request):
    _actualizar(request, CarritoMayorista(request))
    return redirect("pedidos:carrito_mayorista")


@require_POST
def quitar_mayorista(request):
    CarritoMayorista(request).quitar(request.POST.get("clave", ""))
    return redirect("pedidos:carrito_mayorista")


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
    return _pagar(request, Carrito(request))


@login_required(login_url=URL_INGRESAR)
def pagar_mayorista(request):
    """HU 14: el pedido mayorista se confirma con el mismo formulario de datos y pago."""
    return _pagar(request, CarritoMayorista(request))


def _pagar(request, c):
    items = c.items()
    if not items:
        if c.mayorista:
            messages.info(request, "Tu pedido al por mayor está vacío.")
            return redirect("core:mayorista")
        messages.info(request, "Tu carrito está vacío.")
        return redirect("catalogo:lista")
    subtotal = sum((i["subtotal"] for i in items), 0)
    # HU 14 CA 2: el pedido mayorista solo se confirma si llega al monto mínimo vigente (HU 25).
    # No se exige cantidad mínima por referencia.
    if c.mayorista:
        minimo = estado_minimo(subtotal)
        if not minimo.alcanza:
            messages.error(request, f"Para confirmar el pedido al por mayor el subtotal debe ser de al menos "
                                    f"{pesos(minimo.minimo)}. Te faltan {pesos(minimo.falta)}.")
            return redirect("pedidos:carrito_mayorista")
    lineas = [(i["producto"], i["cantidad"]) for i in items]
    form = PedidoForm(request.POST or None, request.FILES or None, usuario=request.user, items=lineas,
                      initial=None if request.method == "POST" else _datos_cuenta(request.user))
    if request.method == "POST" and form.is_valid():
        try:
            pedido = _crear_pedido(request, form, items, subtotal, mayorista=c.mayorista)
        except ErrorCarrito as error:
            messages.error(request, str(error))
            return redirect("pedidos:carrito_mayorista" if c.mayorista else "pedidos:carrito")
        except CodigoInvalido as error:
            form.add_error("codigo", str(error))
        else:
            # HU 12: con Nequi, PSE o Transferencia Bancolombia se paga en la pasarela.
            # El carrito se vacía solo cuando el pago queda aprobado.
            if pedido.estado_pago == Pedido.EstadoPago.EN_PASARELA:
                return redirect(pagos.url_pago(request, pagos.crear_pago(pedido)))
            c.vaciar()
            _marcar_confirmado(request, pedido)
            return redirect("pedidos:confirmado", pk=pedido.pk)
    productos = [i["producto"] for i in items]
    codigo = form.codigo_descuento if form.is_bound and not form.errors.get("codigo") else None
    return render(request, "pedidos/pagar.html", {
        "form": form, "items": items, "subtotal": subtotal, "mayorista": c.mayorista,
        # HU 27: descuento del código que ya se validó (si la página vuelve con otros errores)
        "descuento": codigo.calcular(subtotal) if codigo else 0,
        # HU 30: costo del envío si la página vuelve con la ciudad y el barrio ya escritos
        "envio": form.envio,
        "mensaje_transferencia_por_confirmar": MENSAJE_TRANSFERENCIA_POR_CONFIRMAR,
        "contra_entrega_disponible": permite_contra_entrega(form["ciudad"].value() or ""),
        "mensaje_sin_contra_entrega": MENSAJE_SIN_CONTRA_ENTREGA,
        "empaques": TipoEmpaque.objects.filter(activo=True),
        "datos_transferencia": settings.LADYROSE["DATOS_TRANSFERENCIA"],
        # HU 07: tiempo de fabricación del carrito y, si ya hay ciudad, la fecha estimada
        "estimado": estimar_entrega(productos, form["ciudad"].value()),
        "tiempo_fabricacion_carrito": texto_dias_habiles(*tiempos_fabricacion(productos)),
        "ciudades_envio": TiempoEnvio.objects.values_list("ciudad", flat=True),
    })


def _carrito_de(request, mayorista):
    """HU 14: las consultas del pago usan el carrito al detal o el mayorista."""
    return CarritoMayorista(request) if mayorista else Carrito(request)


def _marcar_confirmado(request, pedido):
    """La página de confirmación solo la ve quien hizo el pedido."""
    confirmados = request.session.get("pedidos_confirmados", [])
    request.session["pedidos_confirmados"] = confirmados + [pedido.pk]


@require_GET
def calcular_envio_vista(request, mayorista=False):
    """HU 30: costo del envío para la ciudad y el barrio que escribe el cliente."""
    lineas = [(i["producto"], i["cantidad"]) for i in _carrito_de(request, mayorista).items()]
    ciudad = request.GET.get("ciudad", "").strip()
    if not lineas or not ciudad:
        return JsonResponse({"ok": False})
    envio = calcular_envio(lineas, ciudad, request.GET.get("barrio", ""))
    return JsonResponse({"ok": True, **envio.como_dict(),
                         # HU 12 CA 5: si la ciudad va por transportadora no se ofrece contra entrega
                         "contra_entrega": permite_contra_entrega(ciudad),
                         "texto": pesos(envio.valor) if envio.valor else ("Gratis" if envio.valor == 0 else "Por confirmar")})


@require_GET
@login_required(login_url=URL_INGRESAR)
def aplicar_codigo(request, mayorista=False):
    """HU 27: revisa el código que escribe el cliente y devuelve cuánto se descuenta."""
    items = _carrito_de(request, mayorista).items()
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
def estimar(request, mayorista=False):
    """HU 07 CA 2 y CA 3: tiempo de envío y fechas estimadas para la ciudad que escribe el cliente."""
    productos = [i["producto"] for i in _carrito_de(request, mayorista).items()]
    estimado = estimar_entrega(productos, request.GET.get("ciudad", ""))
    if not productos or estimado is None:
        return JsonResponse({"ok": False})
    return JsonResponse({"ok": True, **estimado.como_dict()})


def _crear_pedido(request, form, items, subtotal, mayorista=False):
    with transaction.atomic():
        # Las piezas únicas se bloquean para que dos personas no compren la misma (HU 08)
        ids_unicas = [i["producto"].pk for i in items if i["producto"].pieza_unica]
        unicas = Producto.objects.select_for_update().filter(pk__in=ids_unicas)
        if any(p.vendida for p in unicas):
            raise ErrorCarrito("Una de las piezas únicas de tu carrito se acaba de vender.")

        pedido = form.save(commit=False)
        pedido.tipo = Pedido.Tipo.MAYORISTA if mayorista else Pedido.Tipo.DETAL
        pedido.cliente = request.user
        pedido.subtotal = subtotal
        pedido.costo_empaque = pedido.empaque.costo if pedido.empaque else 0
        # HU 27: el código se bloquea y se vuelve a revisar para que no se use dos veces al mismo tiempo
        if form.codigo_descuento:
            codigo = CodigoDescuento.objects.select_for_update().get(pk=form.codigo_descuento.pk)
            codigo.validar_para(request.user)
            pedido.descuento = codigo.calcular(subtotal)
        # HU 30: costo del envío según la zona o el peso (o "por confirmar")
        envio = form.envio
        pedido.peso_total = envio.peso
        pedido.costo_envio = envio.valor
        pedido.envio_costo_estado = envio.estado
        pedido.envio_detalle = envio.detalle
        pedido.calcular_total()
        # HU 12: el pago en línea se hace en la pasarela. Si el envío está por confirmar,
        # se paga después, cuando la dueña confirme el valor (como la transferencia de la HU 30).
        if pedido.pago_en_linea and not envio.por_confirmar:
            pedido.estado_pago = Pedido.EstadoPago.EN_PASARELA
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


@login_required(login_url=URL_INGRESAR)
def mi_pedido(request, pk):
    """HU 30: el cliente ve su pedido con el envío y, si paga por transferencia, sube el comprobante."""
    pedido = get_object_or_404(Pedido.objects.prefetch_related("detalles"), pk=pk, cliente=request.user)
    puede_subir = (pedido.metodo_pago == Pedido.MetodoPago.TRANSFERENCIA and not pedido.comprobante
                   and not pedido.envio_por_confirmar)
    form = ComprobanteForm(request.POST or None, request.FILES or None) if puede_subir else None
    if form is not None and request.method == "POST" and form.is_valid():
        pedido.comprobante = form.cleaned_data["comprobante"]
        pedido.save(update_fields=["comprobante"])
        messages.success(request, "¡Recibimos tu comprobante! Lo revisamos y despachamos tu pedido.")
        return redirect("pedidos:mi_pedido", pk=pedido.pk)
    return render(request, "pedidos/mi_pedido.html", {
        "pedido": pedido, "form": form, "datos_transferencia": settings.LADYROSE["DATOS_TRANSFERENCIA"],
        # HU 12: pago en línea pendiente (por ejemplo, cuando el envío ya quedó confirmado)
        "puede_pagar_en_linea": _puede_pagar_en_linea(pedido),
    })


def _puede_pagar_en_linea(pedido):
    return (pedido.pago_en_linea and not pedido.envio_por_confirmar
            and pedido.estado_pago in (Pedido.EstadoPago.PENDIENTE, Pedido.EstadoPago.EN_PASARELA))


# ------------------------------------------------------------------
# Pago en línea (HU 12): Nequi, PSE y Transferencia Bancolombia
# ------------------------------------------------------------------

@require_POST
@login_required(login_url=URL_INGRESAR)
def pagar_en_linea(request, pk):
    """El cliente paga un pedido que ya existe (por ejemplo, cuando le confirmaron el envío)."""
    pedido = get_object_or_404(Pedido, pk=pk, cliente=request.user)
    if not _puede_pagar_en_linea(pedido):
        return redirect("pedidos:mi_pedido", pk=pedido.pk)
    pedido.estado_pago = Pedido.EstadoPago.EN_PASARELA
    pedido.save(update_fields=["estado_pago"])
    return redirect(pagos.url_pago(request, pagos.crear_pago(pedido)))


def resultado_pago(request):
    """Página a la que vuelve el cliente desde la pasarela (?id=<transacción>)."""
    pago = get_object_or_404(Pago.objects.select_related("pedido"), transaccion_id=request.GET.get("id", ""))
    pedido = pago.pedido
    if request.user.is_authenticated and pedido.cliente_id not in (None, request.user.pk):
        raise Http404
    if pago.estado == Pago.Estado.APROBADO:
        # Ahora sí se vacía el carrito con el que se hizo el pedido
        (CarritoMayorista(request) if pedido.es_mayorista else Carrito(request)).vaciar()
        _marcar_confirmado(request, pedido)
        return redirect("pedidos:confirmado", pk=pedido.pk)
    if pago.estado == Pago.Estado.PENDIENTE:
        return render(request, "pedidos/pago_en_proceso.html", {"pago": pago})
    messages.error(request, "El pago no se completó.")
    return redirect("pedidos:carrito_mayorista" if pedido.es_mayorista else "pedidos:carrito")


@csrf_exempt
@require_POST
def eventos_pasarela(request):
    """HU 12 CA 3: webhook de la pasarela. Solo un evento con la firma correcta aprueba el pago.

    La pasarela espera un 200; con otra respuesta vuelve a intentar más tarde.
    """
    try:
        evento = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "JSON inválido"}, status=400)
    if not isinstance(evento, dict) or not pasarela.evento_valido(evento):
        return JsonResponse({"ok": False, "error": "Firma inválida"}, status=400)
    pago = pagos.procesar_evento(evento)
    return JsonResponse({"ok": True, "referencia": pago.referencia if pago else None})


def _pago_desde_pasarela(request):
    """Revisa que el enlace de pago no se haya cambiado (firma de integridad)."""
    datos = request.GET if request.method == "GET" else request.POST
    pago = Pago.objects.select_related("pedido").filter(referencia=datos.get("reference", "")).first()
    if pago is None:
        raise Http404
    centavos = pasarela.en_centavos(pago.monto)
    firma = pasarela.firma_integridad(pago.referencia, centavos)
    if datos.get("amount-in-cents") != str(centavos) or datos.get("signature:integrity") != firma:
        raise Http404
    return pago, datos


def pasarela_pago(request):
    """Página de pago de la pasarela de pruebas (hace las veces del Web Checkout de Wompi)."""
    pago, datos = _pago_desde_pasarela(request)
    if request.method == "POST" and not pago.terminado:
        estado = {
            "pagar": pasarela.EstadoTransaccion.APROBADA,
            "rechazar": pasarela.EstadoTransaccion.RECHAZADA,
            "cancelar": pasarela.EstadoTransaccion.ANULADA,
        }.get(request.POST.get("accion"))
        if estado:
            # La pasarela le avisa a la tienda con un evento firmado, como el webhook de Wompi.
            # (Con Wompi real, este evento llega por internet a /pagos/eventos/.)
            evento = pasarela.crear_evento({
                "id": pasarela.nuevo_id_transaccion(), "reference": pago.referencia,
                "amount_in_cents": pasarela.en_centavos(pago.monto), "status": estado,
                "payment_method_type": pasarela.TIPO_METODO.get(pago.metodo, ""),
                "customer_email": pago.pedido.correo, "currency": pasarela.MONEDA,
            })
            pagos.procesar_evento(evento)
            pago.refresh_from_db()
    if pago.terminado:
        # Siempre se vuelve a la página de resultado de la tienda (no a otra que venga en el enlace)
        return redirect(f"{reverse('pedidos:resultado_pago')}?id={pago.transaccion_id}")
    return render(request, "pedidos/pasarela.html", {
        "pago": pago, "pedido": pago.pedido, "datos": datos, "pasarela": pasarela.config(),
        "campos": [(k, v) for k, v in datos.items() if k not in ("accion", "csrfmiddlewaretoken")],
    })


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
    pendientes = (Pedido.objects.para_produccion().exclude(estado_produccion=Pedido.EstadoProduccion.TERMINADO)
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
    tecnicas = sorted({t.strip() for valor in Pedido.objects.para_produccion().exclude(tecnica="")
                       .exclude(estado_produccion=Pedido.EstadoProduccion.TERMINADO)
                       .values_list("tecnica", flat=True) for t in valor.split(",") if t.strip()})
    # HU 04 CA 2: lo terminado sale de la lista y queda en "Listos para envío"
    listos = (Pedido.objects.para_produccion().filter(estado_produccion=Pedido.EstadoProduccion.TERMINADO,
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
