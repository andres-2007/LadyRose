"""Pruebas de los criterios de aceptación de las HU 01, 03, 04, 10, 11 y 24 (Sprint 2)."""
from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from catalogo.models import Categoria, FotoProducto, Producto, TallaProducto
from core.roles import GRUPO_DISENADORA, GRUPO_DUENA, crear_roles
from core.tests_utils import PruebaConArchivos, imagen
from cotizaciones.models import ImagenReferencia, SolicitudCotizacion

from .models import DetallePedido, Pedido, TipoEmpaque


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
