"""Pruebas de los criterios de aceptación de las HU 01, 03, 04, 10, 11 y 24 (Sprint 2) y HU 07 y 30 (Sprint 3)."""
from datetime import date, datetime, timedelta
from decimal import Decimal
from urllib.parse import unquote

from django.contrib.auth.models import Group, User
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from catalogo.models import Categoria, FotoProducto, Producto, TallaProducto
from core.festivos import festivos_colombia, sumar_dias_habiles
from core.models import ConfiguracionTienda
from core.roles import GRUPO_DISENADORA, GRUPO_DUENA, crear_roles
from core.tests_utils import PruebaConArchivos, imagen, iniciar_sesion_cliente
from cotizaciones.models import ImagenReferencia, SolicitudCotizacion

from .entregas import estimar_entrega
from .models import BarrioZona, DetallePedido, Pedido, TarifaPeso, TiempoEnvio, TipoEmpaque, ZonaEnvio


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
        # HU 27: para comprar hay que tener cuenta
        self.cliente = iniciar_sesion_cliente(self)

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
        # HU 30: con el envío ya calculado (barrio en una zona) el comprobante se pide al pagar
        zona = ZonaEnvio.objects.create(nombre="Oeste", tarifa=5000)
        BarrioZona.objects.create(zona=zona, nombre="El Peñón")
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
        self.client.logout()
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


# ----------------------------------------------------------------------
# HU 30: costo de envío según la zona (Sprint 3)
# ----------------------------------------------------------------------

class HU30EnvioBase(BaseTienda):
    def setUp(self):
        super().setUp()
        self.sur = ZonaEnvio.objects.create(nombre="Sur", tarifa=5000)
        BarrioZona.objects.create(zona=self.sur, nombre="Ciudad Jardín")
        self.gratis = ZonaEnvio.objects.create(nombre="Sur cercana", tarifa=0)
        BarrioZona.objects.create(zona=self.gratis, nombre="Valle del Lili")

    def envio(self, ciudad, barrio=""):
        return self.client.get(reverse("pedidos:calcular_envio"), {"ciudad": ciudad, "barrio": barrio}).json()

    def tarifas(self):
        TarifaPeso.objects.create(peso_hasta=500, valor=12000)
        TarifaPeso.objects.create(peso_hasta=1000, valor=18000)


class HU30ZonasCaliTests(HU30EnvioBase):
    def test_ca1_zona_con_tarifa_fija(self):
        r = self.comprar(barrio_lista="Ciudad Jardín", barrio="")
        pedido = Pedido.objects.get()
        self.assertRedirects(r, reverse("pedidos:confirmado", args=[pedido.pk]))
        self.assertEqual((pedido.barrio, pedido.costo_envio, pedido.envio_costo_estado),
                         ("Ciudad Jardín", Decimal("5000"), "calculado"))
        self.assertEqual(pedido.total, Decimal("73000"))  # $68.000 + $5.000

    def test_ca1_zona_con_envio_gratis(self):
        self.agregar_al_carrito()
        r = self.envio("Cali", "Valle del Lili")
        self.assertEqual((r["valor"], r["texto"]), (0, "Gratis"))

    def test_ca1_el_barrio_escrito_a_mano_tambien_se_reconoce(self):
        self.agregar_al_carrito()
        self.assertEqual(self.envio(" CALI ", "ciudad jardin")["valor"], 5000)

    def test_ca1_el_pago_muestra_la_lista_de_barrios_con_otro_barrio(self):
        self.agregar_al_carrito()
        r = self.client.get(reverse("pedidos:pagar"))
        self.assertContains(r, '<option value="Ciudad Jardín">Ciudad Jardín</option>', html=True)
        self.assertContains(r, '<option value="otro">Otro barrio</option>', html=True)

    def test_ca1_una_zona_inactiva_no_se_usa(self):
        ZonaEnvio.objects.filter(pk=self.sur.pk).update(activa=False)
        self.agregar_al_carrito()
        self.assertTrue(self.envio("Cali", "Ciudad Jardín")["por_confirmar"])

    def test_ca1_un_barrio_no_puede_estar_en_dos_zonas(self):
        with self.assertRaises(ValidationError):
            BarrioZona(zona=self.gratis, nombre="ciudad jardin").full_clean()

    def test_ca2_cali_fuera_de_zona_queda_por_confirmar(self):
        r = self.comprar(barrio_lista="otro", barrio="San Antonio")
        pedido = Pedido.objects.get()
        self.assertEqual((pedido.barrio, pedido.costo_envio, pedido.envio_costo_estado),
                         ("San Antonio", None, "por_confirmar"))
        self.assertEqual(pedido.total, Decimal("68000"))
        r = self.client.get(r.url)
        self.assertContains(r, "depende de la hora y la distancia")
        self.assertContains(r, "Por confirmar")

    def test_ca2_sin_zonas_cargadas_todo_cali_queda_por_confirmar(self):
        ZonaEnvio.objects.all().delete()
        self.agregar_al_carrito()
        r = self.envio("Cali", "Ciudad Jardín")
        self.assertTrue(r["por_confirmar"])
        self.assertIn("depende de la hora y de la distancia", r["mensaje"])

    def test_ca2_con_envio_por_confirmar_la_transferencia_se_hace_despues(self):
        r = self.comprar(barrio_lista="otro", barrio="San Antonio", metodo_pago="transferencia")
        pedido = Pedido.objects.get()
        self.assertFalse(pedido.comprobante)
        self.assertContains(self.client.get(r.url), "No transfieras todavía")

    def test_el_barrio_es_obligatorio(self):
        r = self.comprar(barrio_lista="", barrio="")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Este dato es obligatorio para poder despachar tu pedido.")
        self.assertFalse(Pedido.objects.exists())


class HU30OtrasCiudadesTests(HU30EnvioBase):
    def test_ca3_otra_ciudad_segun_el_peso_total(self):
        self.tarifas()
        self.agregar_al_carrito(cantidad=2)  # 2 x 50 g = 100 g
        r = self.envio("Bogotá")
        self.assertEqual((r["peso"], r["valor"]), (100, 12000))
        Producto.objects.filter(pk=self.producto.pk).update(peso=400)  # 800 g
        self.assertEqual(self.envio("Bogotá")["valor"], 18000)

    def test_ca3_el_limite_de_cada_rango_esta_incluido(self):
        self.tarifas()
        Producto.objects.filter(pk=self.producto.pk).update(peso=500)
        self.agregar_al_carrito()
        self.assertEqual(self.envio("Medellín")["valor"], 12000)

    def test_ca3_las_ciudades_cerca_de_cali_tambien_van_por_peso(self):
        self.tarifas()
        self.agregar_al_carrito()
        self.assertEqual(self.envio("Jamundí")["valor"], 12000)

    def test_ca3_si_pesa_mas_que_el_ultimo_rango_queda_por_confirmar(self):
        self.tarifas()
        Producto.objects.filter(pk=self.producto.pk).update(peso=1500)
        self.agregar_al_carrito()
        r = self.envio("Bogotá")
        self.assertTrue(r["por_confirmar"])
        self.assertIn("Servientrega", r["mensaje"])

    def test_ca3_sin_tabla_de_pesos_queda_por_confirmar(self):
        self.agregar_al_carrito()
        self.assertTrue(self.envio("Pasto")["por_confirmar"])

    def test_ca3_el_pedido_guarda_el_peso_y_el_costo(self):
        self.tarifas()
        self.comprar(ciudad="Pereira", barrio="Centro")
        pedido = Pedido.objects.get()
        self.assertEqual((pedido.peso_total, pedido.costo_envio, pedido.total),
                         (50, Decimal("12000"), Decimal("80000")))

    def test_ca4_el_peso_es_obligatorio_y_mayor_a_cero(self):
        for peso in (None, 0):
            self.producto.peso = peso
            with self.assertRaises(ValidationError):
                self.producto.full_clean()


class HU30ResumenTests(HU30EnvioBase):
    def test_ca5_el_envio_aparece_separado_en_el_pago(self):
        self.agregar_al_carrito()
        r = self.client.get(reverse("pedidos:pagar"))
        self.assertContains(r, "data-fila-envio")
        self.assertContains(r, "Escribe tu ciudad")

    def test_ca5_y_en_la_confirmacion(self):
        r = self.comprar(barrio_lista="Ciudad Jardín", barrio="")
        r = self.client.get(r.url)
        self.assertContains(r, "<span>Productos</span><span>$68.000</span>", html=True)
        self.assertContains(r, "<span>Envío</span><span>$5.000</span>", html=True)
        self.assertContains(r, "$73.000")

    def test_el_descuento_no_se_aplica_al_envio(self):
        from clientes.models import CodigoDescuento
        CodigoDescuento.objects.create(cliente=self.cliente, codigo="DIEZ", tipo="porcentaje", valor=10,
                                       vence=timezone.localdate())
        self.comprar(barrio_lista="Ciudad Jardín", barrio="", codigo="DIEZ")
        pedido = Pedido.objects.get()
        # $68.000 - 10% ($6.800) + envío $5.000
        self.assertEqual((pedido.descuento, pedido.total), (Decimal("6800"), Decimal("66200")))


class HU30ConfirmarEnvioTests(HU30EnvioBase):
    def setUp(self):
        super().setUp()
        self.comprar(barrio_lista="otro", barrio="San Antonio", metodo_pago="transferencia")
        self.pedido = Pedido.objects.get()
        self.comprador = self.cliente.usuario
        crear_roles()
        self.duena = User.objects.create_user("duena", password="x", is_staff=True)
        self.duena.groups.add(Group.objects.get(name=GRUPO_DUENA))
        self.disenadora = User.objects.create_user("disenadora", password="x", is_staff=True)
        self.disenadora.groups.add(Group.objects.get(name=GRUPO_DISENADORA))

    def registrar_valor(self, valor):
        url = reverse("admin:pedidos_pedido_change", args=[self.pedido.pk])
        r = self.client.get(url)
        datos = {k: v for k, v in r.context["adminform"].form.initial.items() if v is not None}
        datos.update({
            "costo_envio": valor, "metodo_pago": self.pedido.metodo_pago, "estado_pago": self.pedido.estado_pago,
            "estado_envio": self.pedido.estado_envio, "estado_produccion": self.pedido.estado_produccion,
            "detalles-TOTAL_FORMS": "0", "detalles-INITIAL_FORMS": "0",
        })
        datos.pop("comprobante", None)
        datos.pop("empaque", None)
        datos.pop("cotizacion", None)
        datos["whatsapp_igual"] = "on" if self.pedido.whatsapp_igual else ""
        datos["fecha_limite"] = self.pedido.fecha_limite.isoformat()
        return self.client.post(url, datos)

    def test_ca2_la_duena_registra_el_valor_y_se_avisa_por_correo(self):
        self.client.force_login(self.duena)
        r = self.registrar_valor("9000")
        self.assertEqual(r.status_code, 302)
        self.pedido.refresh_from_db()
        self.assertEqual((self.pedido.costo_envio, self.pedido.envio_costo_estado, self.pedido.total),
                         (Decimal("9000"), "confirmado", Decimal("77000")))
        self.assertEqual(len(mail.outbox), 1)
        cuerpo = mail.outbox[0].body
        self.assertIn("$9.000", cuerpo)
        self.assertIn("$77.000", cuerpo)
        self.assertIn(reverse("pedidos:mi_pedido", args=[self.pedido.pk]), cuerpo)
        self.assertIsNotNone(self.pedido.envio_avisado_en)

    def test_ca2_aviso_por_whatsapp_con_el_valor(self):
        self.client.force_login(self.duena)
        self.registrar_valor("9000")
        r = self.client.get(reverse("admin:pedidos_pedido_avisar_envio", args=[self.pedido.pk]))
        self.assertTrue(r.url.startswith("https://wa.me/573011112233?text="))
        self.assertIn("$9.000", unquote(r.url))

    def test_ca2_la_disenadora_no_registra_el_valor(self):
        self.client.force_login(self.disenadora)
        r = self.client.get(reverse("admin:pedidos_pedido_change", args=[self.pedido.pk]))
        self.assertNotIn("costo_envio", r.context["adminform"].form.fields)

    def test_ca2_el_cliente_sube_el_comprobante_cuando_ya_sabe_el_total(self):
        url = reverse("pedidos:mi_pedido", args=[self.pedido.pk])
        r = self.client.get(url)
        self.assertContains(r, "Estamos calculando el valor del envío")
        self.assertNotContains(r, "Enviar comprobante")
        self.client.force_login(self.duena)
        self.registrar_valor("9000")
        self.client.force_login(self.comprador)
        r = self.client.get(url)
        self.assertContains(r, "Transfiere")
        self.assertContains(r, "$77.000")
        comprobante = SimpleUploadedFile("pago.pdf", b"%PDF-1.4 comprobante", content_type="application/pdf")
        self.client.post(url, {"comprobante": comprobante})
        self.pedido.refresh_from_db()
        self.assertTrue(self.pedido.comprobante.name.endswith(".pdf"))

    def test_otro_cliente_no_ve_el_pedido(self):
        iniciar_sesion_cliente(self, "otra@correo.com")
        r = self.client.get(reverse("pedidos:mi_pedido", args=[self.pedido.pk]))
        self.assertEqual(r.status_code, 404)

    def test_el_panel_de_produccion_avisa_que_el_envio_esta_por_confirmar(self):
        self.client.force_login(self.disenadora)
        r = self.client.get(reverse("pedidos:panel_detalle", args=[self.pedido.pk]))
        self.assertContains(r, "Por confirmar")
