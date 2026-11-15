"""Pruebas de los criterios de aceptación de la HU 28 (Sprint 3): seguimiento de clientes potenciales."""
from datetime import datetime, timedelta
from urllib.parse import unquote

from django.contrib.auth.models import Group, User
from django.urls import reverse
from django.utils import timezone

from catalogo.models import Categoria, Producto
from core.festivos import fin_horas_habiles
from core.roles import GRUPO_DISENADORA, GRUPO_DUENA, crear_roles
from core.tests_utils import PruebaConArchivos, iniciar_sesion_cliente
from cotizaciones.models import SolicitudCotizacion
from cursos.models import Curso, Inscripcion
from pedidos.models import Pedido

from .admin import resumen_del_mes
from .models import Consulta


def hora(anio, mes, dia, h=0, m=0):
    return timezone.make_aware(datetime(anio, mes, dia, h, m))


class BaseConsultas(PruebaConArchivos):
    def setUp(self):
        self.categoria = Categoria.objects.create(nombre="Collares")
        self.producto = Producto.objects.create(nombre="Maxicollar Sagrado Corazón", categoria=self.categoria,
                                                precio=40000)
        self.curso = Curso.objects.create(
            nombre="Taller Bendición del Hogar", tecnica="Macramé", materiales_incluidos="Hilos",
            modalidad="presencial", tipo_clase="grupal", fecha=timezone.localdate() + timedelta(days=20),
            horario="2 p.m.", precio=100000, cupos_maximos=20, publicado=True)
        crear_roles()
        self.duena = User.objects.create_user("duena", password="x", is_staff=True)
        self.duena.groups.add(Group.objects.get(name=GRUPO_DUENA))
        self.disenadora = User.objects.create_user("disenadora", password="x", is_staff=True)
        self.disenadora.groups.add(Group.objects.get(name=GRUPO_DISENADORA))

    def consulta(self, **datos):
        valores = {"origen": Consulta.Origen.PRODUCTO, "nombre": "Carolina Duque", "whatsapp": "3204445566",
                   "producto": self.producto}
        valores.update(datos)
        return Consulta.objects.create(**valores)

    def preguntar(self, objeto=None, **datos):
        objeto = objeto or self.producto
        tipo = "producto" if isinstance(objeto, Producto) else "curso"
        valores = {"nombre": "Carolina Duque", "whatsapp": "320 444 5566", "mensaje": "¿Lo tienen en rosado?"}
        valores.update(datos)
        return self.client.post(reverse(f"consultas:preguntar_{tipo}", args=[objeto.slug]), valores)


# ----------------------------------------------------------------------
# CA 1: cada consulta o cotización queda registrada
# ----------------------------------------------------------------------

class HU28RegistroTests(BaseConsultas):
    def test_ca1_la_pregunta_por_un_producto_queda_registrada(self):
        antes = timezone.now()
        r = self.preguntar()
        self.assertRedirects(r, self.producto.get_absolute_url() + "#preguntanos", fetch_redirect_response=False)
        c = Consulta.objects.get()
        self.assertEqual((c.origen, c.nombre, c.whatsapp, c.producto, c.estado),
                         ("producto", "Carolina Duque", "320 444 5566", self.producto, "nueva"))
        self.assertGreaterEqual(c.fecha, antes)

    def test_ca1_la_pregunta_por_un_curso_queda_registrada(self):
        self.preguntar(self.curso, mensaje="¿Cuándo abren otra fecha?")
        c = Consulta.objects.get()
        self.assertEqual((c.origen, c.curso, c.interes), ("curso", self.curso, "Taller Bendición del Hogar"))

    def test_ca1_la_ficha_del_producto_y_del_curso_tienen_el_formulario(self):
        self.assertContains(self.client.get(self.producto.get_absolute_url()), "¿Tienes una pregunta sobre")
        self.assertContains(self.client.get(self.curso.get_absolute_url()), "¿Tienes una pregunta sobre")

    def test_ca1_sin_nombre_o_whatsapp_no_se_registra(self):
        r = self.preguntar(nombre="", whatsapp="12")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Este dato es obligatorio para poder responderte.")
        self.assertContains(r, "Escribe un número de WhatsApp válido")
        self.assertFalse(Consulta.objects.exists())

    def test_ca1_si_tiene_cuenta_se_llena_y_queda_ligada(self):
        cliente = iniciar_sesion_cliente(self, "paola@correo.com", "Paola Martínez", whatsapp="3127778899")
        r = self.client.get(self.producto.get_absolute_url())
        self.assertContains(r, 'value="Paola Martínez"')
        self.preguntar(nombre="Paola Martínez", whatsapp="3127778899")
        c = Consulta.objects.get()
        self.assertEqual((c.usuario, c.correo), (cliente.usuario, "paola@correo.com"))

    def test_ca1_la_solicitud_de_cotizacion_queda_registrada(self):
        datos = {"nombre": "Laura Gómez", "whatsapp": "3157654321", "correo": "laura@correo.com",
                 "descripcion": "Unos aretes de luna", "motivo": "", "acepta_pieza_unica": "on",
                 "cambio_color": "Plateado"}
        self.client.post(reverse("cotizaciones:personalizar", args=[self.producto.slug]), datos)
        solicitud = SolicitudCotizacion.objects.get()
        c = Consulta.objects.get()
        self.assertEqual((c.origen, c.cotizacion, c.producto, c.nombre, c.whatsapp, c.correo),
                         ("cotizacion", solicitud, self.producto, "Laura Gómez", "3157654321", "laura@correo.com"))


# ----------------------------------------------------------------------
# CA 2: estados de la consulta
# ----------------------------------------------------------------------

class HU28EstadosTests(BaseConsultas):
    def test_ca2_los_cuatro_estados(self):
        self.assertEqual([e.label for e in Consulta.Estado], ["Nueva", "Contactada", "Compró", "Descartada"])
        self.assertEqual(self.consulta().estado, Consulta.Estado.NUEVA)

    def test_ca2_la_duena_cambia_el_estado_desde_el_panel(self):
        c = self.consulta()
        self.client.force_login(self.duena)
        self.client.post(reverse("admin:consultas_consulta_change", args=[c.pk]), {"estado": "descartada"})
        c.refresh_from_db()
        self.assertEqual(c.estado, "descartada")

    def test_ca2_contactada_y_compro_guardan_la_fecha(self):
        c = self.consulta()
        c.cambiar_estado(Consulta.Estado.CONTACTADA)
        self.assertIsNotNone(c.contactada_en)
        c.cambiar_estado(Consulta.Estado.COMPRO)
        self.assertIsNotNone(c.compro_en)

    def test_la_cotizacion_muestra_el_estado_de_su_consulta(self):
        solicitud = SolicitudCotizacion.objects.create(nombre="Laura", whatsapp="3157654321")
        from .models import registrar_cotizacion
        registrar_cotizacion(solicitud).cambiar_estado(Consulta.Estado.CONTACTADA)
        self.client.force_login(self.duena)
        r = self.client.get(reverse("admin:cotizaciones_solicitudcotizacion_changelist"))
        self.assertContains(r, "Contactada")

    def test_solo_la_duena_ve_las_consultas(self):
        url = reverse("admin:consultas_consulta_changelist")
        self.client.force_login(self.disenadora)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.duena)
        self.assertEqual(self.client.get(url).status_code, 200)


# ----------------------------------------------------------------------
# CA 3: resaltar las que llevan más de 24 horas hábiles sin respuesta
# ----------------------------------------------------------------------

class HU28ResaltadoTests(BaseConsultas):
    def test_ca3_24_horas_habiles_saltan_fines_de_semana_y_festivos(self):
        # Viernes 13 de noviembre de 2026, 3 p.m.; el lunes 16 es festivo -> martes 17, 3 p.m.
        self.assertEqual(fin_horas_habiles(hora(2026, 11, 13, 15), 24), hora(2026, 11, 17, 15))
        # Martes a mediodía -> miércoles a mediodía
        self.assertEqual(fin_horas_habiles(hora(2026, 11, 24, 12), 24), hora(2026, 11, 25, 12))
        # Sábado 21: cuenta desde el lunes 23 a las 12 a.m. -> martes 24 a las 12 a.m.
        self.assertEqual(fin_horas_habiles(hora(2026, 11, 21, 10), 24), hora(2026, 11, 24))
        # Jueves 24 de diciembre, 6 p.m.: 6 horas el 24, Navidad y fin de semana no cuentan -> lunes 28, 6 p.m.
        self.assertEqual(fin_horas_habiles(hora(2026, 12, 24, 18), 24), hora(2026, 12, 28, 18))

    def test_ca3_una_consulta_nueva_se_resalta_al_cumplir_el_plazo(self):
        c = self.consulta(fecha=hora(2026, 11, 13, 15))
        self.assertFalse(c.sin_respuesta(hora(2026, 11, 16, 20)))  # lunes festivo: aún no
        self.assertFalse(c.sin_respuesta(hora(2026, 11, 17, 14, 59)))
        self.assertTrue(c.sin_respuesta(hora(2026, 11, 17, 15)))

    def test_ca3_las_contactadas_no_se_resaltan(self):
        c = self.consulta(fecha=hora(2026, 11, 2, 9))
        c.cambiar_estado(Consulta.Estado.CONTACTADA)
        self.assertFalse(c.sin_respuesta(hora(2026, 11, 20, 9)))

    def test_ca3_el_panel_resalta_solo_las_atrasadas(self):
        self.consulta(nombre="Atrasada Uno", fecha=timezone.now() - timedelta(days=6))
        self.consulta(nombre="Reciente Dos", fecha=timezone.now() - timedelta(minutes=30))
        self.client.force_login(self.duena)
        url = reverse("admin:consultas_consulta_changelist")
        r = self.client.get(url)
        self.assertContains(r, "Sin respuesta +24 h hábiles", count=1)
        r = self.client.get(url, {"atrasadas": "si"})
        self.assertContains(r, "Atrasada Uno")
        self.assertNotContains(r, "Reciente Dos")


# ----------------------------------------------------------------------
# CA 4: botón de WhatsApp con el producto
# ----------------------------------------------------------------------

class HU28WhatsappTests(BaseConsultas):
    def test_ca4_abre_whatsapp_con_el_numero_y_el_producto_y_queda_contactada(self):
        c = self.consulta(whatsapp="320 444 5566")
        self.client.force_login(self.duena)
        r = self.client.get(reverse("admin:consultas_consulta_whatsapp", args=[c.pk]))
        self.assertTrue(r.url.startswith("https://wa.me/573204445566?text="))
        texto = unquote(r.url)
        self.assertIn("Carolina", texto)
        self.assertIn("Maxicollar Sagrado Corazón", texto)
        c.refresh_from_db()
        self.assertEqual(c.estado, Consulta.Estado.CONTACTADA)
        self.assertIsNotNone(c.contactada_en)

    def test_ca4_el_mensaje_menciona_el_curso_o_la_cotizacion(self):
        self.assertIn("el curso Taller Bendición del Hogar",
                      self.consulta(producto=None, curso=self.curso, origen="curso").mensaje_whatsapp())
        solicitud = SolicitudCotizacion.objects.create(nombre="Laura", whatsapp="3157654321")
        self.assertIn("pieza personalizada", self.consulta(producto=None, cotizacion=solicitud).mensaje_whatsapp())

    def test_ca4_el_boton_aparece_en_la_lista(self):
        c = self.consulta()
        self.client.force_login(self.duena)
        r = self.client.get(reverse("admin:consultas_consulta_changelist"))
        self.assertContains(r, reverse("admin:consultas_consulta_whatsapp", args=[c.pk]))

    def test_si_ya_compro_el_boton_no_cambia_el_estado(self):
        c = self.consulta(estado=Consulta.Estado.COMPRO)
        self.client.force_login(self.duena)
        self.client.get(reverse("admin:consultas_consulta_whatsapp", args=[c.pk]))
        c.refresh_from_db()
        self.assertEqual(c.estado, Consulta.Estado.COMPRO)


# ----------------------------------------------------------------------
# CA 5: consultas del mes que terminaron en compra (y "Compró" automático)
# ----------------------------------------------------------------------

class HU28CompraTests(BaseConsultas):
    def pedido(self, **datos):
        valores = {"nombre": "X", "telefono": "3000000000", "direccion": "Calle 1", "barrio": "Centro",
                   "ciudad": "Cali", "metodo_pago": "contra_entrega"}
        valores.update(datos)
        return Pedido.objects.create(**valores)

    def test_pasa_sola_a_compro_cuando_hace_un_pedido_con_el_mismo_whatsapp(self):
        c = self.consulta(whatsapp="320 444 5566")
        pedido = self.pedido(telefono="3204445566")
        c.refresh_from_db()
        self.assertEqual((c.estado, c.pedido), (Consulta.Estado.COMPRO, pedido))

    def test_pasa_sola_a_compro_con_el_mismo_correo_o_la_misma_cuenta(self):
        por_correo = self.consulta(whatsapp="", correo="laura@correo.com")
        cliente = iniciar_sesion_cliente(self, "paola@correo.com")
        por_cuenta = self.consulta(whatsapp="", usuario=cliente.usuario)
        self.pedido(correo="LAURA@correo.com")
        self.pedido(cliente=cliente.usuario)
        for c in (por_correo, por_cuenta):
            c.refresh_from_db()
            self.assertEqual(c.estado, Consulta.Estado.COMPRO)

    def test_pasa_sola_a_compro_cuando_paga_un_curso(self):
        c = self.consulta(producto=None, curso=self.curso, origen="curso", whatsapp="3016667788")
        inscripcion = Inscripcion.objects.create(curso=self.curso, nombre="Luisa", whatsapp="3016667788",
                                                 correo="luisa@correo.com", modalidad="presencial")
        c.refresh_from_db()
        self.assertEqual(c.estado, Consulta.Estado.NUEVA)  # inscrita pero sin pagar
        inscripcion.confirmar_pago()
        c.refresh_from_db()
        self.assertEqual(c.estado, Consulta.Estado.COMPRO)

    def test_no_cambia_las_descartadas_ni_las_de_otras_personas(self):
        descartada = self.consulta(estado=Consulta.Estado.DESCARTADA)
        otra = self.consulta(whatsapp="3110000000")
        self.pedido(telefono="3204445566")
        descartada.refresh_from_db()
        otra.refresh_from_db()
        self.assertEqual((descartada.estado, otra.estado), (Consulta.Estado.DESCARTADA, Consulta.Estado.NUEVA))

    def test_ca5_cuantas_consultas_del_mes_terminaron_en_compra(self):
        ahora = timezone.now()
        self.consulta(estado=Consulta.Estado.COMPRO)
        self.consulta(whatsapp="3001")
        self.consulta(estado=Consulta.Estado.DESCARTADA)
        self.consulta(estado=Consulta.Estado.COMPRO, fecha=ahora - timedelta(days=62))  # otro mes
        self.assertEqual(resumen_del_mes(), {"total": 3, "compraron": 1, "porcentaje": 33})
        self.client.force_login(self.duena)
        r = self.client.get(reverse("admin:consultas_consulta_changelist"))
        self.assertContains(r, "1 de 3")
        self.assertContains(r, "(33%)")

    def test_ca5_sin_consultas_en_el_mes(self):
        self.assertEqual(resumen_del_mes(), {"total": 0, "compraron": 0, "porcentaje": 0})
