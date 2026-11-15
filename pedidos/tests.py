"""Pruebas de los criterios de aceptación de las HU 01, 03, 04, 10, 11 y 24 (Sprint 2) y HU 07 (Sprint 3)."""
from datetime import date, datetime, timedelta

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from catalogo.models import Categoria, FotoProducto, Producto, TallaProducto
from core.festivos import festivos_colombia, sumar_dias_habiles
from core.models import ConfiguracionTienda
from core.roles import GRUPO_DISENADORA, GRUPO_DUENA, crear_roles
from core.tests_utils import PruebaConArchivos, imagen
from cotizaciones.models import ImagenReferencia, SolicitudCotizacion

from .entregas import estimar_entrega
from .models import DetallePedido, Pedido, TiempoEnvio, TipoEmpaque


def datos_envio(**extra):
    datos = {
        "nombre": "Paula Rojas", "correo": "paula@correo.com", "telefono": "3011112233",
        "whatsapp_igual": "on", "whatsapp": "", "direccion": "Calle 9 # 40-12", "barrio": "El Peñón",
        "ciudad": "Cali", "indicaciones": "", "nota": "", "motivo": "", "metodo_pago": "contra_entrega",
    }
    datos.update(extra)
    return datos


class BaseTienda(PruebaConArchivos):
    def setUp(self):
        self.categoria = Categoria.objects.create(nombre="Collares")
        self.producto = Producto.objects.create(
            nombre="Collar Flores", categoria=self.categoria, precio=68000, tecnica="Tejido Miyuki",
            material="Mostacillas Miyuki", dias_elaboracion=4,
        )
        FotoProducto.objects.create(producto=self.producto, imagen=imagen())
        self.talla = TallaProducto.objects.create(producto=self.producto, nombre="45 cm", medida="Clavícula")

    def agregar_al_carrito(self, producto=None, **datos):
        producto = producto or self.producto
        datos.setdefault("talla", self.talla.pk if producto == self.producto else "")
        return self.client.post(reverse("pedidos:agregar", args=[producto.pk]), datos)

    def comprar(self, **extra):
        self.agregar_al_carrito()
        return self.client.post(reverse("pedidos:pagar"), datos_envio(**extra))


class HU24DatosDespachoTests(BaseTienda):
    def test_carrito_agregar_cambiar_cantidad_y_quitar(self):
        self.agregar_al_carrito(cantidad=2)
        r = self.client.get(reverse("pedidos:carrito"))
        self.assertContains(r, "Collar Flores")
        self.assertContains(r, "$136.000")
        clave = list(self.client.session["carrito"].keys())[0]
        self.client.post(reverse("pedidos:actualizar"), {"clave": clave, "cantidad": 3})
        self.assertEqual(self.client.session["carrito"][clave], 3)
        self.client.post(reverse("pedidos:quitar"), {"clave": clave})
        self.assertEqual(self.client.session["carrito"], {})

    def test_ca1_pide_los_datos_obligatorios(self):
        self.agregar_al_carrito()
        r = self.client.get(reverse("pedidos:pagar"))
        for campo in ("nombre", "direccion", "barrio", "ciudad", "telefono"):
            self.assertContains(r, f'name="{campo}"')

    def test_ca4_sin_datos_obligatorios_no_se_confirma_y_marca_el_campo(self):
        r = self.comprar(direccion="", barrio="", telefono="")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Pedido.objects.exists())
        self.assertContains(r, "campo--error", count=3)
        self.assertContains(r, "Este dato es obligatorio para poder despachar tu pedido.", count=3)

    def test_ca2_whatsapp_igual_o_distinto(self):
        self.comprar()
        self.assertEqual(Pedido.objects.get().whatsapp, "3011112233")
        Pedido.objects.all().delete()
        r = self.comprar(whatsapp_igual="")
        self.assertContains(r, "Escribe tu número de WhatsApp")
        self.comprar(whatsapp_igual="", whatsapp="3209998877")
        self.assertEqual(Pedido.objects.get().whatsapp, "3209998877")

    def test_ca3_transferencia_exige_comprobante(self):
        r = self.comprar(metodo_pago="transferencia")
        self.assertContains(r, "Adjunta el comprobante de la transferencia")
        self.assertFalse(Pedido.objects.exists())
        comprobante = SimpleUploadedFile("pago.pdf", b"%PDF-1.4 comprobante", content_type="application/pdf")
        r = self.comprar(metodo_pago="transferencia", comprobante=comprobante)
        pedido = Pedido.objects.get()
        self.assertRedirects(r, reverse("pedidos:confirmado", args=[pedido.pk]))
        self.assertTrue(pedido.comprobante.name.endswith(".pdf"))

    def test_ca3_contra_entrega_no_pide_comprobante(self):
        self.comprar(metodo_pago="contra_entrega")
        self.assertEqual(Pedido.objects.get().metodo_pago, Pedido.MetodoPago.CONTRA_ENTREGA)

    def test_pedido_guarda_detalle_exacto_y_vacia_el_carrito(self):
        self.agregar_al_carrito(cantidad=2)
        self.client.post(reverse("pedidos:pagar"), datos_envio())
        pedido = Pedido.objects.get()
        detalle = pedido.detalles.get()
        self.assertEqual((detalle.referencia, detalle.talla, detalle.cantidad), ("Collar Flores", "45 cm (Clavícula)", 2))
        self.assertEqual(pedido.total, 136000)
        self.assertEqual(self.client.session["carrito"], {})
        r = self.client.get(reverse("pedidos:confirmado", args=[pedido.pk]))
        self.assertContains(r, pedido.numero)

    def test_ca5_el_panel_muestra_envio_productos_y_pago_en_una_vista(self):
        self.comprar()
        pedido = Pedido.objects.get()
        admin = User.objects.create_superuser("admin", "a@a.co", "x")
        self.client.force_login(admin)
        r = self.client.get(reverse("admin:pedidos_pedido_change", args=[pedido.pk]))
        for texto in ("Datos de envío", "Calle 9 # 40-12", "El Peñón", "Collar Flores", "45 cm (Clavícula)",
                      "Pago", "Pago contra entrega"):
            self.assertContains(r, texto)

    def test_hu31_la_compra_guarda_la_red_de_origen(self):
        self.client.get("/?utm_source=instagram")
        self.comprar()
        self.assertEqual(Pedido.objects.get().canal_origen, "instagram")

    def test_otra_persona_no_puede_ver_la_confirmacion(self):
        self.comprar()
        pedido = Pedido.objects.get()
        self.client.logout()
        self.client.cookies.clear()
        self.assertEqual(self.client.get(reverse("pedidos:confirmado", args=[pedido.pk])).status_code, 404)


class HU11RegaloTests(BaseTienda):
    def setUp(self):
        super().setUp()
        self.caja = TipoEmpaque.objects.create(nombre="Caja de regalo", costo=8000)

    def test_ca1_selector_de_empaques_con_costo_que_se_suma(self):
        self.agregar_al_carrito()
        r = self.client.get(reverse("pedidos:pagar"))
        self.assertContains(r, "Caja de regalo")
        self.assertContains(r, "$8.000")
        self.client.post(reverse("pedidos:pagar"), datos_envio(empaque=self.caja.pk))
        pedido = Pedido.objects.get()
        self.assertEqual((pedido.costo_empaque, pedido.total), (8000, 76000))

    def test_ca2_nota_de_maximo_200_caracteres(self):
        r = self.comprar(nota="x" * 201)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Pedido.objects.exists())
        self.comprar(nota="Feliz cumpleaños, mamá")
        self.assertEqual(Pedido.objects.get().nota, "Feliz cumpleaños, mamá")

    def test_ca3_enviar_a_otra_persona(self):
        r = self.comprar(enviar_a_otra_persona="on")
        self.assertContains(r, "Escribe los datos de la persona que recibe el regalo.")
        self.comprar(enviar_a_otra_persona="on", nombre_recibe="Marta Rojas", telefono_recibe="3005556677")
        pedido = Pedido.objects.get()
        self.assertEqual((pedido.nombre_recibe, pedido.telefono_recibe), ("Marta Rojas", "3005556677"))
        self.assertEqual(pedido.nombre, "Paula Rojas")

    def test_si_no_es_regalo_recibe_quien_compra(self):
        self.comprar()
        self.assertEqual(Pedido.objects.get().nombre_recibe, "Paula Rojas")


class PanelBase(BaseTienda):
    def setUp(self):
        super().setUp()
        crear_roles()
        self.disenadora = User.objects.create_user("disenadora", password="x", is_staff=True, first_name="Liliana")
        self.disenadora.groups.add(Group.objects.get(name=GRUPO_DISENADORA))
        self.duena = User.objects.create_user("duena", password="x", is_staff=True)
        self.duena.groups.add(Group.objects.get(name=GRUPO_DUENA))

    def crear_pedido(self, dias=3, tecnica="Tejido Miyuki", estado=Pedido.EstadoProduccion.PENDIENTE, **extra):
        pedido = Pedido.objects.create(
            nombre="Ana Pérez", telefono="3001234567", correo="ana@correo.com", direccion="Calle 1", barrio="Centro",
            ciudad="Cali", metodo_pago="contra_entrega", tecnica=tecnica, dias_elaboracion=dias,
            fecha_limite=timezone.localdate() + timedelta(days=dias), estado_produccion=estado, **extra,
        )
        DetallePedido.objects.create(pedido=pedido, producto=self.producto, referencia=self.producto.nombre,
                                     talla="45 cm", color="Rosa", material="Mostacillas Miyuki",
                                     cantidad=1, precio_unitario=68000)
        return pedido


class HU01PanelPedidosTests(PanelBase):
    def test_solo_entra_el_personal_con_permiso(self):
        r = self.client.get(reverse("pedidos:panel"))
        self.assertEqual(r.status_code, 302)
        cliente = User.objects.create_user("cliente", password="x")
        self.client.force_login(cliente)
        self.assertNotEqual(self.client.get(reverse("pedidos:panel")).status_code, 200)

    def test_ca1_cada_pedido_muestra_numero_accesorio_tecnica_y_fecha(self):
        pedido = self.crear_pedido()
        self.client.force_login(self.disenadora)
        r = self.client.get(reverse("pedidos:panel"))
        self.assertContains(r, pedido.numero)
        self.assertContains(r, "Collar Flores")
        self.assertContains(r, "Tejido Miyuki")
        self.assertContains(r, self.producto.foto_principal.imagen.url)

    def test_ca2_dos_formas_de_ordenar(self):
        lejos = self.crear_pedido(dias=6, tecnica="Alambrismo")
        cerca = self.crear_pedido(dias=1, tecnica="Resina")
        largo = self.crear_pedido(dias=4, tecnica="Alambrismo")
        self.client.force_login(self.disenadora)
        r = self.client.get(reverse("pedidos:panel") + "?orden=fecha")
        self.assertEqual([p.pk for p in r.context["pendientes"]], [cerca.pk, largo.pk, lejos.pk])
        r = self.client.get(reverse("pedidos:panel") + "?orden=tecnica")
        self.assertEqual([p.pk for p in r.context["pendientes"]], [lejos.pk, largo.pk, cerca.pk])
        self.assertContains(r, "Fecha de entrega más próxima")
        self.assertContains(r, "Técnica / tiempo de elaboración")

    def test_ca3_mensaje_sin_pedidos(self):
        self.client.force_login(self.disenadora)
        self.assertContains(self.client.get(reverse("pedidos:panel")), "No tienes pedidos pendientes")

    def test_la_fecha_limite_sale_de_los_dias_de_elaboracion(self):
        self.comprar()
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.tecnica, "Tejido Miyuki")
        self.assertEqual(pedido.dias_elaboracion, 4)
        self.assertGreater(pedido.fecha_limite, timezone.localdate())
        self.assertLess(pedido.fecha_limite.weekday(), 5)


class HU03DetallePedidoTests(PanelBase):
    def test_ca1_imagenes_de_referencia_del_cliente(self):
        cotizacion = SolicitudCotizacion.objects.create(nombre="Ana", whatsapp="300", descripcion="Aretes",
                                                        motivo="Para mi abuela", acepta_pieza_unica=True)
        ref = ImagenReferencia.objects.create(solicitud=cotizacion, imagen=imagen("ref.jpg"))
        pedido = self.crear_pedido(cotizacion=cotizacion)
        self.client.force_login(self.disenadora)
        r = self.client.get(reverse("pedidos:panel_detalle", args=[pedido.pk]))
        self.assertContains(r, ref.imagen.url)

    def test_ca2_resalta_empaque_y_nota(self):
        caja = TipoEmpaque.objects.create(nombre="Caja con cinta", costo=8000)
        pedido = self.crear_pedido(empaque=caja, nota="Feliz día, mamá")
        self.client.force_login(self.disenadora)
        r = self.client.get(reverse("pedidos:panel_detalle", args=[pedido.pk]))
        self.assertContains(r, "tarjeta-panel--regalo")
        self.assertContains(r, "Este pedido es un regalo")
        self.assertContains(r, "Caja con cinta")
        self.assertContains(r, "Feliz día, mamá")

    def test_ca3_muestra_la_historia_o_motivo(self):
        pedido = self.crear_pedido(motivo="Es para mi mamá, que cumple 60")
        self.client.force_login(self.disenadora)
        self.assertContains(self.client.get(reverse("pedidos:panel_detalle", args=[pedido.pk])),
                            "Es para mi mamá, que cumple 60")

    def test_ca4_colores_materiales_y_talla(self):
        pedido = self.crear_pedido()
        self.client.force_login(self.disenadora)
        r = self.client.get(reverse("pedidos:panel_detalle", args=[pedido.pk]))
        for texto in ("45 cm", "Rosa", "Mostacillas Miyuki"):
            self.assertContains(r, texto)


class HU04EstadosTests(PanelBase):
    def test_ca1_selector_con_los_tres_estados(self):
        self.crear_pedido()
        self.client.force_login(self.disenadora)
        r = self.client.get(reverse("pedidos:panel"))
        for estado in ('value="pendiente"', 'value="en_curso"', 'value="terminado"'):
            self.assertContains(r, estado)

    def test_ca2_terminado_pasa_a_listos_para_envio(self):
        pedido = self.crear_pedido()
        self.client.force_login(self.disenadora)
        r = self.client.post(reverse("pedidos:cambiar_estado", args=[pedido.pk]), {"estado": "terminado"},
                             HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(r.json()["ok"], True)
        r = self.client.get(reverse("pedidos:panel"))
        self.assertNotIn(pedido, r.context["pendientes"])
        self.assertIn(pedido, r.context["listos"])

    def test_ca3_el_estado_se_mantiene(self):
        pedido = self.crear_pedido()
        self.client.force_login(self.disenadora)
        self.client.post(reverse("pedidos:cambiar_estado", args=[pedido.pk]), {"estado": "en_curso"})
        self.client.logout()
        self.client.force_login(self.disenadora)
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado_produccion, "en_curso")
        self.assertContains(self.client.get(reverse("pedidos:panel")), 'value="en_curso" selected')

    def test_ca4_la_duena_ve_el_estado_en_su_panel(self):
        pedido = self.crear_pedido(estado=Pedido.EstadoProduccion.EN_CURSO)
        self.client.force_login(self.duena)
        r = self.client.get(reverse("admin:pedidos_pedido_changelist"))
        self.assertContains(r, "En curso")
        self.assertContains(r, pedido.numero)

    def test_estado_no_valido_o_sin_permiso(self):
        pedido = self.crear_pedido()
        self.client.force_login(self.disenadora)
        r = self.client.post(reverse("pedidos:cambiar_estado", args=[pedido.pk]), {"estado": "borrado"})
        self.assertEqual(r.status_code, 400)


class HU10AvisoInsumosTests(PanelBase):
    def test_ca1_y_ca2_aviso_por_whatsapp_pone_el_pedido_en_pausa(self):
        pedido = self.crear_pedido(estado=Pedido.EstadoProduccion.EN_CURSO)
        self.client.force_login(self.disenadora)
        r = self.client.post(reverse("pedidos:avisar", args=[pedido.pk]),
                             {"canal": "whatsapp", "mensaje": "Se agotó la mostacilla rosa"})
        self.assertTrue(r["Location"].startswith("https://wa.me/573001234567?text="))
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado_produccion, Pedido.EstadoProduccion.EN_PAUSA)
        self.assertEqual(pedido.get_estado_produccion_display(), "En pausa - Esperando respuesta del cliente")

    def test_ca1_y_ca2_aviso_por_correo(self):
        pedido = self.crear_pedido()
        self.client.force_login(self.disenadora)
        self.client.post(reverse("pedidos:avisar", args=[pedido.pk]),
                         {"canal": "correo", "mensaje": "Se agotó el dije de luna"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["ana@correo.com"])
        self.assertIn("Se agotó el dije de luna", mail.outbox[0].body)
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado_produccion, Pedido.EstadoProduccion.EN_PAUSA)

    def test_ca3_reanudar_vuelve_a_en_curso(self):
        pedido = self.crear_pedido(estado=Pedido.EstadoProduccion.EN_PAUSA)
        self.client.force_login(self.disenadora)
        self.client.post(reverse("pedidos:reanudar", args=[pedido.pk]))
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado_produccion, Pedido.EstadoProduccion.EN_CURSO)


# ----------------------------------------------------------------------
# HU 07: tiempo estimado de fabricación y de envío (Sprint 3)
# ----------------------------------------------------------------------

class HU07TiempoEntregaTests(BaseTienda):
    def setUp(self):
        super().setUp()
        self.producto.dias_fabricacion_min, self.producto.dias_elaboracion = 3, 4
        self.producto.save()
        # Cali la crea la migración: entrega directa, de 1 a 2 días hábiles
        TiempoEnvio.objects.create(ciudad="Bogotá", dias_min=2, dias_max=4)

    def estimar(self, ciudad):
        return self.client.get(reverse("pedidos:estimar_entrega"), {"ciudad": ciudad}).json()

    # ----- CA 1: tiempo de fabricación en la ficha -----
    def test_ca1_la_ficha_muestra_el_tiempo_de_fabricacion(self):
        r = self.client.get(self.producto.get_absolute_url())
        self.assertContains(r, "Tiempo de fabricación:")
        self.assertContains(r, "De 3 a 4 días hábiles")

    def test_ca1_si_minimo_y_maximo_son_iguales_muestra_un_solo_valor(self):
        self.producto.dias_fabricacion_min = self.producto.dias_elaboracion = 1
        self.producto.save()
        r = self.client.get(self.producto.get_absolute_url())
        self.assertContains(r, "1 día hábil")

    def test_ca1_el_minimo_no_puede_ser_mayor_que_el_maximo(self):
        self.producto.dias_fabricacion_min = 5
        with self.assertRaises(ValidationError):
            self.producto.full_clean()

    # ----- CA 2: tiempo de envío según la ciudad -----
    def test_ca2_el_pago_muestra_el_tiempo_de_fabricacion_y_pide_la_ciudad(self):
        self.agregar_al_carrito()
        r = self.client.get(reverse("pedidos:pagar"))
        self.assertContains(r, "De 3 a 4 días hábiles")
        self.assertContains(r, "Tiempo estimado de envío")
        self.assertContains(r, "Escribe tu ciudad para calcularlo")

    def test_ca2_tiempo_de_envio_segun_la_ciudad_de_la_tabla(self):
        self.agregar_al_carrito()
        self.assertEqual(self.estimar("Cali")["tiempo_envio"], "De 1 a 2 días hábiles")
        self.assertEqual(self.estimar("Bogotá")["tiempo_envio"], "De 2 a 4 días hábiles")

    def test_ca2_la_ciudad_se_reconoce_sin_tildes_ni_mayusculas(self):
        self.agregar_al_carrito()
        respuesta = self.estimar("  BOGOTA ")
        self.assertEqual(respuesta["tiempo_envio"], "De 2 a 4 días hábiles")
        self.assertEqual(respuesta["ciudad"], "Bogotá")

    def test_ca2_ciudad_que_no_esta_en_la_tabla_usa_el_tiempo_de_otras_ciudades(self):
        config = ConfiguracionTienda.obtener()
        config.envio_otras_ciudades_min, config.envio_otras_ciudades_max = 4, 7
        config.save()
        self.agregar_al_carrito()
        self.assertEqual(self.estimar("Pasto")["tiempo_envio"], "De 4 a 7 días hábiles")

    def test_ca2_si_la_pagina_vuelve_con_errores_conserva_el_calculo(self):
        r = self.comprar(nombre="", ciudad="Bogotá")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "a Bogotá")
        self.assertContains(r, "De 2 a 4 días hábiles")
        self.assertContains(r, "Recibirás tu pedido aproximadamente entre el")

    def test_ca2_sin_productos_en_el_carrito_no_calcula(self):
        self.assertEqual(self.estimar("Cali"), {"ok": False})

    def test_tabla_de_envios_no_acepta_minimo_mayor_ni_ciudades_repetidas(self):
        with self.assertRaises(ValidationError):
            TiempoEnvio(ciudad="Pereira", dias_min=5, dias_max=2).full_clean()
        with self.assertRaises(ValidationError):
            TiempoEnvio(ciudad="bogota", dias_min=1, dias_max=2).full_clean()

    # ----- CA 3: suma de los dos tiempos y mensaje con las fechas -----
    def test_ca3_suma_los_dos_tiempos_en_dias_habiles(self):
        # Martes 10 de noviembre de 2026. El lunes 16 es festivo (Independencia de Cartagena).
        # Desde: 3 + 1 = 4 días hábiles -> 11, 12, 13, (16 festivo), 17
        # Hasta: 4 + 2 = 6 días hábiles -> ..., 18, 19
        estimado = estimar_entrega([self.producto], "Cali", desde=date(2026, 11, 10))
        self.assertEqual(estimado.fecha_desde, date(2026, 11, 17))
        self.assertEqual(estimado.fecha_hasta, date(2026, 11, 19))
        self.assertEqual(
            estimado.mensaje,
            "Recibirás tu pedido aproximadamente entre el martes 17 de noviembre y el jueves 19 de noviembre.",
        )

    def test_ca3_con_varios_productos_cuenta_el_que_mas_se_demora(self):
        rapido = Producto.objects.create(nombre="Aretes", categoria=self.categoria, precio=20000,
                                         dias_fabricacion_min=1, dias_elaboracion=1)
        estimado = estimar_entrega([rapido, self.producto], "Cali", desde=date(2026, 11, 10))
        self.assertEqual((estimado.fabricacion_min, estimado.fabricacion_max), (3, 4))

    def test_ca3_el_mensaje_llega_al_pago(self):
        self.agregar_al_carrito()
        respuesta = self.estimar("Bogotá")
        hoy = timezone.localdate()
        self.assertEqual(respuesta["fecha_desde"], sumar_dias_habiles(hoy, 3 + 2).isoformat())
        self.assertEqual(respuesta["fecha_hasta"], sumar_dias_habiles(hoy, 4 + 4).isoformat())
        self.assertTrue(respuesta["mensaje"].startswith("Recibirás tu pedido aproximadamente entre el"))

    # ----- CA 4: aviso de la transportadora -----
    def test_ca4_otras_ciudades_avisan_que_el_tiempo_depende_de_la_transportadora(self):
        self.agregar_al_carrito()
        for ciudad in ("Bogotá", "Pasto"):
            aviso = self.estimar(ciudad)["aviso"]
            self.assertIn("depende de la transportadora", aviso)
            self.assertIn("no se hace responsable por los retrasos", aviso)

    def test_ca4_en_cali_no_sale_el_aviso_de_la_transportadora(self):
        self.agregar_al_carrito()
        self.assertEqual(self.estimar("Cali")["aviso"], "")

    # ----- Panel -----
    def test_la_duena_administra_la_tabla_y_la_disenadora_no(self):
        crear_roles()
        duena = User.objects.create_user("duena", password="x", is_staff=True)
        duena.groups.add(Group.objects.get(name=GRUPO_DUENA))
        disenadora = User.objects.create_user("disenadora", password="x", is_staff=True)
        disenadora.groups.add(Group.objects.get(name=GRUPO_DISENADORA))
        url = reverse("admin:pedidos_tiempoenvio_changelist")
        self.client.force_login(duena)
        self.assertContains(self.client.get(url), "Bogotá")
        self.client.force_login(disenadora)
        self.assertEqual(self.client.get(url).status_code, 403)


class HU07FestivosTests(PruebaConArchivos):
    """Subtarea de la HU 07: pruebas con fechas cercanas a festivos."""

    def test_festivos_de_colombia_2026(self):
        esperados = {date(2026, m, d) for m, d in [
            (1, 1), (1, 12), (3, 23), (4, 2), (4, 3), (5, 1), (5, 18), (6, 8), (6, 15), (6, 29),
            (7, 20), (8, 7), (8, 17), (10, 12), (11, 2), (11, 16), (12, 8), (12, 25)]}
        self.assertEqual(set(festivos_colombia(2026)), esperados)

    def test_festivos_de_colombia_2025(self):
        esperados = {date(2025, m, d) for m, d in [
            (1, 1), (1, 6), (3, 24), (4, 17), (4, 18), (5, 1), (6, 2), (6, 23), (6, 30),
            (7, 20), (8, 7), (8, 18), (10, 13), (11, 3), (11, 17), (12, 8), (12, 25)]}
        self.assertEqual(set(festivos_colombia(2025)), esperados)

    def test_salta_el_puente_festivo(self):
        # Viernes 13 de noviembre de 2026 + 1 día hábil: el lunes 16 es festivo
        self.assertEqual(sumar_dias_habiles(date(2026, 11, 13), 1), date(2026, 11, 17))

    def test_salta_semana_santa(self):
        # Miércoles 1 de abril de 2026: jueves y viernes santo son festivos
        self.assertEqual(sumar_dias_habiles(date(2026, 4, 1), 1), date(2026, 4, 6))

    def test_salta_navidad_y_el_cambio_de_anio(self):
        self.assertEqual(sumar_dias_habiles(date(2026, 12, 24), 1), date(2026, 12, 28))
        self.assertEqual(sumar_dias_habiles(date(2026, 12, 31), 1), date(2027, 1, 4))

    def test_la_fecha_limite_del_panel_tampoco_cae_en_festivo(self):
        # HU 01 usa el mismo cálculo: pedido del viernes 13 con 1 día de fabricación -> martes 17
        categoria = Categoria.objects.create(nombre="Pulseras")
        producto = Producto.objects.create(nombre="Pulsera", categoria=categoria, precio=20000,
                                           dias_fabricacion_min=1, dias_elaboracion=1)
        pedido = Pedido.objects.create(
            creado=timezone.make_aware(datetime(2026, 11, 13, 10, 0)), nombre="Ana", telefono="3001234567",
            direccion="Calle 1", barrio="Centro", ciudad="Cali", metodo_pago="contra_entrega",
        )
        DetallePedido.objects.create(pedido=pedido, producto=producto, referencia="Pulsera", precio_unitario=20000)
        pedido.calcular_produccion()
        self.assertEqual(pedido.fecha_limite, date(2026, 11, 17))
