"""Pruebas de los criterios de aceptación de la HU 27 (Sprint 3): descuentos personalizados por cliente."""
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import unquote

from django.contrib.auth.models import Group, User
from django.core import mail
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from catalogo.models import Categoria, Producto
from core.roles import GRUPO_DISENADORA, GRUPO_DUENA, crear_roles
from core.tests_utils import PruebaConArchivos, iniciar_sesion_cliente
from cursos.models import Curso
from pedidos.models import Pedido, TipoEmpaque

from .models import Cliente, CodigoDescuento, proximo_cumpleanos

CLAVE = "ClaveSegura123*"


def datos_registro(**extra):
    datos = {"nombre": "Paula Rojas", "correo": "paula@correo.com", "whatsapp": "3011112233",
             "cumpleanos": "", "password1": CLAVE, "password2": CLAVE}
    datos.update(extra)
    return datos


def datos_envio(**extra):
    datos = {
        "nombre": "Paula Rojas", "correo": "paula@correo.com", "telefono": "3011112233",
        "whatsapp_igual": "on", "whatsapp": "", "direccion": "Calle 9 # 40-12", "barrio": "El Peñón",
        "ciudad": "Cali", "indicaciones": "", "nota": "", "motivo": "", "metodo_pago": "contra_entrega",
        "codigo": "",
    }
    datos.update(extra)
    return datos


def crear_cliente(correo, nombre="Cliente", **datos):
    usuario = User.objects.create_user(username=correo, email=correo, password=CLAVE, first_name=nombre)
    return Cliente.objects.create(usuario=usuario, **datos)


def crear_codigo(cliente, **datos):
    valores = {"tipo": CodigoDescuento.Tipo.PORCENTAJE, "valor": 10,
               "vence": timezone.localdate() + timedelta(days=10)}
    valores.update(datos)
    return CodigoDescuento.objects.create(cliente=cliente, **valores)


class BaseClientes(PruebaConArchivos):
    def setUp(self):
        self.categoria = Categoria.objects.create(nombre="Pulseras")
        self.producto = Producto.objects.create(nombre="Pulsera Ojo Turco", categoria=self.categoria, precio=20000)

    def agregar(self, producto=None, cantidad=1):
        producto = producto or self.producto
        return self.client.post(reverse("pedidos:agregar", args=[producto.pk]), {"cantidad": cantidad})

    def comprar(self, **extra):
        self.agregar(cantidad=2)  # subtotal $40.000
        return self.client.post(reverse("pedidos:pagar"), datos_envio(**extra))


# ----------------------------------------------------------------------
# CA 6 y CA 3: cuenta del cliente
# ----------------------------------------------------------------------

class HU27CuentaClienteTests(BaseClientes):
    def test_ca6_crear_cuenta_con_nombre_correo_y_contrasena(self):
        r = self.client.post(reverse("clientes:registro"), datos_registro())
        self.assertRedirects(r, reverse("clientes:mi_cuenta"))
        usuario = User.objects.get(email="paula@correo.com")
        self.assertEqual(usuario.first_name, "Paula Rojas")
        self.assertTrue(usuario.check_password(CLAVE))
        self.assertEqual(usuario.cliente.whatsapp, "3011112233")
        self.assertEqual(int(self.client.session["_auth_user_id"]), usuario.pk)

    def test_ca6_no_se_repite_el_correo_ni_acepta_contrasenas_distintas(self):
        crear_cliente("paula@correo.com")
        r = self.client.post(reverse("clientes:registro"), datos_registro(correo="PAULA@correo.com"))
        self.assertContains(r, "Ya hay una cuenta con este correo")
        r = self.client.post(reverse("clientes:registro"), datos_registro(correo="otra@correo.com", password2="Otra123*xx"))
        self.assertContains(r, "Las contraseñas no coinciden")
        self.assertEqual(User.objects.count(), 1)

    def test_ca6_iniciar_sesion_con_correo_y_contrasena(self):
        crear_cliente("paula@correo.com", "Paula Rojas")
        r = self.client.post(reverse("clientes:ingresar"), {"correo": "paula@correo.com", "password": "mala"})
        self.assertContains(r, "El correo o la contraseña no son correctos")
        r = self.client.post(reverse("clientes:ingresar"), {"correo": "Paula@Correo.com", "password": CLAVE})
        self.assertRedirects(r, reverse("clientes:mi_cuenta"))

    def test_ca3_el_cumpleanos_es_opcional(self):
        self.client.post(reverse("clientes:registro"), datos_registro())
        self.assertIsNone(User.objects.get(email="paula@correo.com").cliente.cumpleanos)
        self.client.logout()
        self.client.post(reverse("clientes:registro"), datos_registro(correo="ana@correo.com", cumpleanos="1998-11-20"))
        self.assertEqual(User.objects.get(email="ana@correo.com").cliente.cumpleanos, date(1998, 11, 20))

    def test_ca3_el_cumpleanos_no_puede_ser_futuro(self):
        manana = (timezone.localdate() + timedelta(days=1)).isoformat()
        r = self.client.post(reverse("clientes:registro"), datos_registro(cumpleanos=manana))
        self.assertContains(r, "no puede estar en el futuro")

    def test_para_pagar_hay_que_iniciar_sesion_y_el_carrito_se_conserva(self):
        crear_cliente("paula@correo.com", "Paula Rojas")
        self.agregar()
        r = self.client.get(reverse("pedidos:pagar"))
        self.assertRedirects(r, reverse("clientes:ingresar") + "?next=/pagar/")
        r = self.client.post(reverse("clientes:ingresar") + "?next=/pagar/",
                             {"correo": "paula@correo.com", "password": CLAVE, "next": "/pagar/"})
        self.assertRedirects(r, "/pagar/")
        self.assertContains(self.client.get(reverse("pedidos:pagar")), "Pulsera Ojo Turco")

    def test_el_pago_se_llena_con_los_datos_de_la_cuenta(self):
        iniciar_sesion_cliente(self, "paula@correo.com", "Paula Rojas", whatsapp="3011112233")
        self.agregar()
        r = self.client.get(reverse("pedidos:pagar"))
        self.assertContains(r, 'value="Paula Rojas"')
        self.assertContains(r, 'value="paula@correo.com"')
        self.assertContains(r, 'value="3011112233"')

    def test_el_pedido_queda_ligado_a_la_cuenta(self):
        cliente = iniciar_sesion_cliente(self, "paula@correo.com", "Paula Rojas")
        self.comprar()
        self.assertEqual(Pedido.objects.get().cliente, cliente.usuario)

    def test_para_inscribirse_a_un_curso_hay_que_tener_cuenta(self):
        curso = Curso.objects.create(
            nombre="Macramé", tecnica="Macramé", materiales_incluidos="Hilos", modalidad="presencial",
            tipo_clase="grupal", fecha=timezone.localdate() + timedelta(days=20), horario="3 p.m.",
            precio=80000, cupos_maximos=20, publicado=True)
        r = self.client.get(curso.get_absolute_url())
        self.assertContains(r, "Crear mi cuenta")
        self.assertNotContains(r, "Inscribirme")
        datos = {"nombre": "Ana", "whatsapp": "3001234567", "correo": "ana@correo.com",
                 "curso": curso.pk, "modalidad": "presencial"}
        self.client.post(curso.get_absolute_url(), datos)
        self.assertFalse(curso.inscripciones.exists())
        cliente = iniciar_sesion_cliente(self, "ana@correo.com", "Ana Ruiz")
        self.assertContains(self.client.get(curso.get_absolute_url()), 'value="Ana Ruiz"')
        self.client.post(curso.get_absolute_url(), datos)
        self.assertEqual(curso.inscripciones.get().usuario, cliente.usuario)


# ----------------------------------------------------------------------
# CA 1: crear el código desde el panel
# ----------------------------------------------------------------------

class PanelDuena(BaseClientes):
    def setUp(self):
        super().setUp()
        crear_roles()
        self.duena = User.objects.create_user("duena", password="x", is_staff=True)
        self.duena.groups.add(Group.objects.get(name=GRUPO_DUENA))
        self.disenadora = User.objects.create_user("disenadora", password="x", is_staff=True)
        self.disenadora.groups.add(Group.objects.get(name=GRUPO_DISENADORA))


class HU27CrearCodigoTests(PanelDuena):
    def test_ca1_la_duena_crea_un_codigo_para_un_cliente_con_porcentaje_y_vencimiento(self):
        cliente = crear_cliente("paula@correo.com", "Paula Rojas")
        self.client.force_login(self.duena)
        url = reverse("admin:clientes_codigodescuento_add")
        r = self.client.get(url, {"cliente": cliente.pk, "motivo": "cumpleanos"})
        self.assertContains(r, "CUMPLE-PAULA-")  # código propuesto, editable
        vence = timezone.localdate() + timedelta(days=15)
        r = self.client.post(url, {"cliente": cliente.pk, "motivo": "cumpleanos", "codigo": "cumple-paula",
                                   "tipo": "porcentaje", "valor": "15", "vence": vence.isoformat()})
        codigo = CodigoDescuento.objects.get()
        self.assertRedirects(r, reverse("admin:clientes_codigodescuento_enviar", args=[codigo.pk]))
        self.assertEqual((codigo.codigo, codigo.cliente, codigo.valor, codigo.vence),
                         ("CUMPLE-PAULA", cliente, 15, vence))

    def test_ca1_tambien_con_valor_en_pesos_y_codigo_automatico(self):
        codigo = crear_codigo(crear_cliente("ana@correo.com", "Ana María"), codigo="",
                              tipo=CodigoDescuento.Tipo.VALOR, valor=5000, motivo="gracias")
        self.assertTrue(codigo.codigo.startswith("GRACIAS-ANA-"))
        self.assertEqual(codigo.descuento_texto, "$5.000 de descuento")

    def test_ca1_validaciones_del_codigo(self):
        cliente = crear_cliente("ana@correo.com")
        with self.assertRaises(ValidationError):
            CodigoDescuento(cliente=cliente, tipo="porcentaje", valor=120,
                            vence=timezone.localdate()).full_clean()
        with self.assertRaises(ValidationError):
            CodigoDescuento(cliente=cliente, tipo="valor", valor=5000,
                            vence=timezone.localdate() - timedelta(days=1)).full_clean()

    def test_la_disenadora_no_ve_clientes_ni_codigos(self):
        self.client.force_login(self.disenadora)
        for nombre in ("admin:clientes_cliente_changelist", "admin:clientes_codigodescuento_changelist"):
            self.assertEqual(self.client.get(reverse(nombre)).status_code, 403)


# ----------------------------------------------------------------------
# CA 2: el código solo funciona con su cuenta y una sola vez
# ----------------------------------------------------------------------

class HU27UsarCodigoTests(BaseClientes):
    def setUp(self):
        super().setUp()
        self.cliente = iniciar_sesion_cliente(self, "paula@correo.com", "Paula Rojas")

    def test_ca2_el_codigo_se_aplica_y_queda_usado(self):
        codigo = crear_codigo(self.cliente, codigo="PAULA10", valor=10)
        r = self.comprar(codigo="paula10")
        pedido = Pedido.objects.get()
        self.assertRedirects(r, reverse("pedidos:confirmado", args=[pedido.pk]))
        self.assertEqual((pedido.subtotal, pedido.descuento, pedido.total),
                         (Decimal("40000"), Decimal("4000"), Decimal("36000")))
        codigo.refresh_from_db()
        self.assertTrue(codigo.usado)
        self.assertEqual(pedido.codigo_descuento, codigo)
        self.assertContains(self.client.get(r.url), "PAULA10")

    def test_ca2_no_funciona_con_otra_cuenta(self):
        otro = crear_cliente("ana@correo.com", "Ana")
        crear_codigo(otro, codigo="ANA10")
        r = self.comprar(codigo="ANA10")
        self.assertContains(r, "Este código no está asignado a tu cuenta.")
        self.assertFalse(Pedido.objects.exists())

    def test_ca2_no_funciona_si_ya_se_uso(self):
        crear_codigo(self.cliente, codigo="PAULA10")
        self.comprar(codigo="PAULA10")
        r = self.comprar(codigo="PAULA10")
        self.assertContains(r, "Este código ya fue usado.")
        self.assertEqual(Pedido.objects.count(), 1)

    def test_ca2_no_funciona_si_esta_vencido(self):
        codigo = crear_codigo(self.cliente, codigo="PAULA10")
        CodigoDescuento.objects.filter(pk=codigo.pk).update(vence=timezone.localdate() - timedelta(days=1))
        r = self.comprar(codigo="PAULA10")
        self.assertContains(r, "Este código venció")
        self.assertFalse(Pedido.objects.exists())

    def test_ca2_funciona_hasta_el_ultimo_dia(self):
        crear_codigo(self.cliente, codigo="HOY", vence=timezone.localdate())
        self.comprar(codigo="HOY")
        self.assertEqual(Pedido.objects.get().descuento, Decimal("4000"))

    def test_codigo_que_no_existe(self):
        r = self.comprar(codigo="NOEXISTE")
        self.assertContains(r, "Ese código no existe")

    def test_el_boton_aplicar_muestra_el_descuento_sin_recargar(self):
        crear_codigo(self.cliente, codigo="PAULA10")
        self.agregar(cantidad=2)
        r = self.client.get(reverse("pedidos:aplicar_codigo"), {"codigo": "paula10"}).json()
        self.assertTrue(r["ok"])
        self.assertEqual(r["descuento"], 4000)
        r = self.client.get(reverse("pedidos:aplicar_codigo"), {"codigo": "otro"}).json()
        self.assertFalse(r["ok"])

    def test_el_descuento_es_sobre_los_productos_incluso_en_oferta_y_no_sobre_el_empaque(self):
        hoy = timezone.localdate()
        Producto.objects.filter(pk=self.producto.pk).update(
            precio_oferta=15000, oferta_inicio=hoy - timedelta(days=1), oferta_fin=hoy + timedelta(days=1))
        empaque = TipoEmpaque.objects.create(nombre="Caja", costo=8000)
        crear_codigo(self.cliente, codigo="PAULA10", valor=10)
        self.comprar(codigo="PAULA10", empaque=empaque.pk)
        pedido = Pedido.objects.get()
        # 2 x $15.000 = $30.000 -> 10% = $3.000; el empaque se cobra completo
        self.assertEqual((pedido.subtotal, pedido.descuento, pedido.total),
                         (Decimal("30000"), Decimal("3000"), Decimal("35000")))

    def test_un_descuento_en_pesos_no_deja_el_total_negativo(self):
        crear_codigo(self.cliente, codigo="GRANDE", tipo=CodigoDescuento.Tipo.VALOR, valor=100000)
        self.comprar(codigo="GRANDE")
        pedido = Pedido.objects.get()
        self.assertEqual((pedido.descuento, pedido.total), (Decimal("40000"), Decimal("0")))

    def test_el_cliente_ve_sus_codigos_disponibles_en_mi_cuenta(self):
        crear_codigo(self.cliente, codigo="PAULA10")
        usado = crear_codigo(self.cliente, codigo="USADO")
        CodigoDescuento.objects.filter(pk=usado.pk).update(usado_en=timezone.now())
        r = self.client.get(reverse("clientes:mi_cuenta"))
        self.assertContains(r, "PAULA10")
        self.assertNotContains(r, "USADO")


# ----------------------------------------------------------------------
# CA 4: cumpleaños de los próximos 7 días y envío del código
# ----------------------------------------------------------------------

class HU27CumpleanosTests(PanelDuena):
    def cumple_en(self, dias):
        return (timezone.localdate() + timedelta(days=dias)).replace(year=1995)

    def test_ca4_lista_de_quienes_cumplen_en_los_proximos_7_dias(self):
        crear_cliente("hoy@correo.com", "Cumple Hoy", cumpleanos=self.cumple_en(0))
        crear_cliente("pronto@correo.com", "Cumple Pronto", cumpleanos=self.cumple_en(7))
        crear_cliente("lejos@correo.com", "Cumple Lejos", cumpleanos=self.cumple_en(8))
        crear_cliente("sin@correo.com", "Sin Fecha")
        self.client.force_login(self.duena)
        r = self.client.get(reverse("admin:clientes_cliente_changelist"), {"cumple": "pronto"})
        self.assertContains(r, "Cumple Hoy")
        self.assertContains(r, "Cumple Pronto")
        self.assertNotContains(r, "Cumple Lejos")
        self.assertNotContains(r, "Sin Fecha")

    def test_ca4_cuenta_bien_los_dias_en_cambio_de_anio_y_29_de_febrero(self):
        self.assertEqual(proximo_cumpleanos(date(1990, 1, 2), date(2026, 12, 28)), date(2027, 1, 2))
        cliente = Cliente(cumpleanos=date(1990, 1, 2))
        self.assertEqual(cliente.dias_para_cumpleanos(date(2026, 12, 28)), 5)
        self.assertEqual(proximo_cumpleanos(date(2000, 2, 29), date(2026, 2, 20)), date(2026, 2, 28))

    def test_ca4_enviar_el_codigo_por_correo_con_el_nombre(self):
        codigo = crear_codigo(crear_cliente("paula@correo.com", "Paula Rojas"), codigo="CUMPLE-PAULA",
                              motivo="cumpleanos")
        self.client.force_login(self.duena)
        url = reverse("admin:clientes_codigodescuento_enviar", args=[codigo.pk])
        self.assertContains(self.client.get(url), "¡Hola Paula!")
        self.client.post(url, {"canal": "correo"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["paula@correo.com"])
        self.assertIn("¡Hola Paula!", mail.outbox[0].body)
        self.assertIn("CUMPLE-PAULA", mail.outbox[0].body)
        codigo.refresh_from_db()
        self.assertIsNotNone(codigo.enviado_en)

    def test_ca4_enviar_el_codigo_por_whatsapp_con_el_nombre(self):
        codigo = crear_codigo(crear_cliente("paula@correo.com", "Paula Rojas", whatsapp="3011112233"),
                              codigo="CUMPLE-PAULA", motivo="cumpleanos")
        self.client.force_login(self.duena)
        r = self.client.post(reverse("admin:clientes_codigodescuento_enviar", args=[codigo.pk]), {"canal": "whatsapp"})
        self.assertTrue(r.url.startswith("https://wa.me/573011112233?text="))
        texto = unquote(r.url)
        self.assertIn("¡Hola Paula!", texto)
        self.assertIn("CUMPLE-PAULA", texto)

    def test_ca4_si_no_dejo_whatsapp_se_usa_el_de_su_ultimo_pedido(self):
        cliente = crear_cliente("paula@correo.com", "Paula Rojas")
        Pedido.objects.create(nombre="Paula", correo="paula@correo.com", telefono="3157654321", direccion="Calle 1",
                              barrio="Centro", ciudad="Cali", metodo_pago="contra_entrega")
        self.assertEqual(cliente.whatsapp_internacional, "573157654321")


# ----------------------------------------------------------------------
# CA 5: filtro de clientes que ya han comprado
# ----------------------------------------------------------------------

class HU27YaCompraronTests(PanelDuena):
    def pedido(self, **datos):
        return Pedido.objects.create(nombre="X", telefono="3001234567", direccion="Calle 1", barrio="Centro",
                                     ciudad="Cali", metodo_pago="contra_entrega", **datos)

    def test_ca5_filtrar_a_los_clientes_que_ya_compraron(self):
        con_cuenta = crear_cliente("cuenta@correo.com", "Compro Con Cuenta")
        crear_cliente("invitada@correo.com", "Compro Como Invitada")
        crear_cliente("nueva@correo.com", "Todavia Nada")
        self.pedido(cliente=con_cuenta.usuario)
        self.pedido(correo="INVITADA@correo.com")  # pedido de antes de tener cuenta, mismo correo
        self.client.force_login(self.duena)
        url = reverse("admin:clientes_cliente_changelist")
        r = self.client.get(url, {"compro": "si"})
        self.assertContains(r, "Compro Con Cuenta")
        self.assertContains(r, "Compro Como Invitada")
        self.assertNotContains(r, "Todavia Nada")
        r = self.client.get(url, {"compro": "no"})
        self.assertContains(r, "Todavia Nada")
        self.assertNotContains(r, "Compro Con Cuenta")

    def test_ca5_desde_la_lista_se_le_asigna_un_descuento(self):
        cliente = crear_cliente("cuenta@correo.com", "Compro Con Cuenta")
        self.pedido(cliente=cliente.usuario)
        self.client.force_login(self.duena)
        r = self.client.get(reverse("admin:clientes_cliente_changelist"), {"compro": "si"})
        self.assertContains(r, f"?cliente={cliente.pk}&amp;motivo=gracias")
