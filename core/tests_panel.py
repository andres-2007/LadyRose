"""Pruebas de los criterios de aceptación de la HU 22: panel principal de la dueña.

Se usan datos de ejemplo de pedidos, cotizaciones y visitas. La fecha de "hoy" se
deja fija (15 de noviembre de 2026) para que las pruebas den lo mismo a cualquier hora.
"""
import re
from datetime import date, datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from consultas.models import Consulta, registrar_cotizacion
from cotizaciones.models import SolicitudCotizacion
from pedidos.models import Pedido

from . import resumen
from .models import VisitaOrigen
from .roles import GRUPO_DISENADORA, GRUPO_DUENA, crear_roles

COLOMBIA = ZoneInfo("America/Bogota")
HOY = date(2026, 11, 15)


def hora(dia, mes, h, m=0, anio=2026):
    return datetime(anio, mes, dia, h, m, tzinfo=COLOMBIA)


def nuevo_pedido(telefono, **datos):
    valores = dict(nombre="Cliente", telefono=telefono, direccion="Calle 5 # 38-25", barrio="San Fernando",
                   ciudad="Cali", metodo_pago=Pedido.MetodoPago.CONTRA_ENTREGA)
    valores.update(datos)
    return Pedido.objects.create(**valores)


def nueva_cotizacion(nombre, whatsapp, estado=Consulta.Estado.NUEVA):
    solicitud = SolicitudCotizacion.objects.create(nombre=nombre, whatsapp=whatsapp, descripcion="Un collar")
    consulta = getattr(solicitud, "consulta", None) or registrar_cotizacion(solicitud)
    if estado != Consulta.Estado.NUEVA:
        consulta.cambiar_estado(estado)
    return solicitud


def nuevas_visitas(canal, cuando, cantidad=1):
    for _ in range(cantidad):
        visita = VisitaOrigen.objects.create(canal=canal, pagina="/")
        VisitaOrigen.objects.filter(pk=visita.pk).update(fecha=cuando)


@mock.patch("django.utils.timezone.localdate", return_value=HOY)
class HU22PanelPrincipalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        crear_roles()
        cls.duena = User.objects.create_user("duena", password="ClaveSegura123*", is_staff=True)
        cls.duena.groups.add(Group.objects.get(name=GRUPO_DUENA))
        cls.disenadora = User.objects.create_user("disenadora", password="ClaveSegura123*", is_staff=True)
        cls.disenadora.groups.add(Group.objects.get(name=GRUPO_DISENADORA))

        # Pedidos: 3 por despachar (1 ya terminado), 1 despachado y 2 de pago en línea sin aprobar
        nuevo_pedido("3000000001")
        nuevo_pedido("3000000002", estado_produccion=Pedido.EstadoProduccion.EN_CURSO)
        nuevo_pedido("3000000003", estado_produccion=Pedido.EstadoProduccion.TERMINADO)
        nuevo_pedido("3000000004", estado_envio=Pedido.EstadoEnvio.DESPACHADO)
        nuevo_pedido("3000000005", metodo_pago=Pedido.MetodoPago.NEQUI, estado_pago=Pedido.EstadoPago.EN_PASARELA)
        nuevo_pedido("3000000006", metodo_pago=Pedido.MetodoPago.PSE, estado_pago=Pedido.EstadoPago.RECHAZADO)

        # Cotizaciones: 2 sin responder y 2 que ya se atendieron
        nueva_cotizacion("Paula", "3110000001")
        nueva_cotizacion("Marta", "3110000002")
        nueva_cotizacion("Sofía", "3110000003", Consulta.Estado.CONTACTADA)
        nueva_cotizacion("Laura", "3110000004", Consulta.Estado.DESCARTADA)

        # Visitas: hoy 6 (3 Instagram, 1 Facebook, 2 directas), más 4 antes en el mes y 5 del mes pasado
        nuevas_visitas(VisitaOrigen.Canal.INSTAGRAM, hora(15, 11, 9), 3)
        nuevas_visitas(VisitaOrigen.Canal.FACEBOOK, hora(15, 11, 0, 10))
        nuevas_visitas(VisitaOrigen.Canal.DIRECTO, hora(15, 11, 18), 2)
        nuevas_visitas(VisitaOrigen.Canal.TIKTOK, hora(14, 11, 23, 50), 3)
        nuevas_visitas(VisitaOrigen.Canal.WHATSAPP, hora(1, 11, 0, 5))
        nuevas_visitas(VisitaOrigen.Canal.INSTAGRAM, hora(31, 10, 23, 55), 5)

    def entrar(self, usuario=None):
        self.client.force_login(usuario or self.duena)
        return self.client.get(reverse("admin:index"))

    @staticmethod
    def numero(respuesta, titulo):
        html = respuesta.content.decode()
        encontrado = re.search(re.escape(titulo) + r'</span>\s*<strong class="lr-tarjeta__numero">(\d+)</strong>', html)
        return int(encontrado.group(1)) if encontrado else None

    # ----- CA 1: tarjetas de pedidos, cotizaciones y visitas -----
    def test_ca1_tarjeta_de_pedidos_por_despachar(self, _hoy):
        r = self.entrar()
        self.assertEqual(self.numero(r, "Pedidos por despachar"), 3)
        self.assertContains(r, "1 ya terminado, listo para enviar")

    def test_ca1_no_cuenta_pedidos_despachados_ni_pagos_en_linea_sin_aprobar(self, _hoy):
        self.assertEqual(resumen.pedidos_por_despachar().count(), 3)
        Pedido.objects.filter(telefono="3000000005").update(estado_pago=Pedido.EstadoPago.APROBADO)
        self.assertEqual(resumen.pedidos_por_despachar().count(), 4)

    def test_ca1_tarjeta_de_cotizaciones_sin_responder(self, _hoy):
        r = self.entrar()
        self.assertEqual(self.numero(r, "Cotizaciones sin responder"), 2)

    def test_ca1_cotizaciones_con_mas_de_24_horas_se_resaltan(self, _hoy):
        Consulta.objects.filter(nombre="Paula").update(fecha=hora(2, 11, 10))
        r = self.entrar()
        self.assertContains(r, "lr-tarjeta--alerta")
        self.assertContains(r, "1 con más de 24 horas hábiles")

    def test_ca1_tarjetas_de_visitas_del_dia_y_del_mes(self, _hoy):
        r = self.entrar()
        self.assertEqual(self.numero(r, "Visitas de hoy"), 6)
        self.assertEqual(self.numero(r, "Visitas de noviembre"), 10)

    def test_ca1_el_dia_empieza_a_la_medianoche_de_colombia(self, _hoy):
        # Las de las 11:50 p. m. del 14 son de ayer; la de las 12:10 a. m. del 15 es de hoy
        self.assertEqual(resumen.visitas_hoy()["total"], 6)
        self.assertEqual(resumen.visitas_mes()["total"], 10)

    # ----- CA 2: visitas separadas por canal -----
    def test_ca2_visitas_de_hoy_por_canal(self, _hoy):
        canales = {c["nombre"]: c["total"] for c in resumen.visitas_hoy()["canales"]}
        self.assertEqual(canales, {"Instagram": 3, "Facebook": 1, "TikTok": 0, "WhatsApp": 0, "Entrada directa": 2})

    def test_ca2_visitas_del_mes_por_canal(self, _hoy):
        canales = {c["nombre"]: c["total"] for c in resumen.visitas_mes()["canales"]}
        self.assertEqual(canales, {"Instagram": 3, "Facebook": 1, "TikTok": 3, "WhatsApp": 1, "Entrada directa": 2})

    def test_ca2_otro_canal_solo_sale_si_hubo_visitas(self, _hoy):
        self.assertNotIn("Otro", [c["nombre"] for c in resumen.visitas_hoy()["canales"]])
        nuevas_visitas(VisitaOrigen.Canal.OTRO, hora(15, 11, 12))
        self.assertIn("Otro", [c["nombre"] for c in resumen.visitas_hoy()["canales"]])

    def test_ca2_el_panel_muestra_cada_canal(self, _hoy):
        r = self.entrar()
        for canal in ("Instagram", "Facebook", "TikTok", "WhatsApp", "Entrada directa"):
            self.assertContains(r, f"<span>{canal}</span>")

    # ----- CA 3: cada tarjeta abre la lista con el detalle -----
    def test_ca3_pedidos_abre_la_lista_filtrada(self, _hoy):
        r = self.entrar()
        url = reverse("admin:pedidos_pedido_changelist") + "?despacho=pendientes"
        self.assertContains(r, f'href="{url}"')
        lista = self.client.get(url)
        self.assertEqual(lista.status_code, 200)
        self.assertEqual(lista.context["cl"].result_count, 3)

    def test_ca3_filtro_de_pedidos_terminados_listos_para_enviar(self, _hoy):
        self.client.force_login(self.duena)
        lista = self.client.get(reverse("admin:pedidos_pedido_changelist") + "?despacho=listos")
        self.assertEqual([p.telefono for p in lista.context["cl"].result_list], ["3000000003"])

    def test_ca3_cotizaciones_abre_las_solicitudes_sin_responder(self, _hoy):
        r = self.entrar()
        url = reverse("admin:cotizaciones_solicitudcotizacion_changelist") + "?consulta__estado__exact=nueva"
        self.assertContains(r, f'href="{url}"')
        lista = self.client.get(url)
        self.assertEqual(sorted(s.nombre for s in lista.context["cl"].result_list), ["Marta", "Paula"])

    def test_ca3_visitas_abren_la_lista_del_dia_y_del_mes(self, _hoy):
        r = self.entrar()
        visitas = reverse("admin:core_visitaorigen_changelist")
        hoy = visitas + "?fecha__year=2026&amp;fecha__month=11&amp;fecha__day=15"
        mes = visitas + "?fecha__year=2026&amp;fecha__month=11"
        self.assertContains(r, f'href="{hoy}"')
        self.assertContains(r, f'href="{mes}"')
        self.assertEqual(self.client.get(hoy.replace("&amp;", "&")).context["cl"].result_count, 6)
        self.assertEqual(self.client.get(mes.replace("&amp;", "&")).context["cl"].result_count, 10)

    def test_ca3_cada_canal_abre_sus_visitas(self, _hoy):
        self.entrar()
        url = (reverse("admin:core_visitaorigen_changelist")
               + "?fecha__year=2026&fecha__month=11&fecha__day=15&canal__exact=instagram")
        self.assertEqual(self.client.get(url).context["cl"].result_count, 3)

    # ----- CA 4: los datos se actualizan al entrar o recargar -----
    def test_ca4_al_recargar_se_ven_los_datos_nuevos(self, _hoy):
        r = self.entrar()
        self.assertEqual(self.numero(r, "Pedidos por despachar"), 3)
        self.assertEqual(self.numero(r, "Cotizaciones sin responder"), 2)
        nuevo_pedido("3000000007")
        nueva_cotizacion("Andrea", "3110000005")
        nuevas_visitas(VisitaOrigen.Canal.TIKTOK, hora(15, 11, 20))
        r = self.client.get(reverse("admin:index"))
        self.assertEqual(self.numero(r, "Pedidos por despachar"), 4)
        self.assertEqual(self.numero(r, "Cotizaciones sin responder"), 3)
        self.assertEqual(self.numero(r, "Visitas de hoy"), 7)

    def test_ca4_muestra_la_hora_de_los_datos(self, _hoy):
        self.assertContains(self.entrar(), "Datos al")

    # ----- Permisos -----
    def test_la_disenadora_no_ve_las_visitas(self, _hoy):
        r = self.entrar(self.disenadora)
        self.assertEqual(self.numero(r, "Pedidos por despachar"), 3)
        self.assertIsNone(self.numero(r, "Visitas de hoy"))

    def test_sin_sesion_no_se_ve_el_panel(self, _hoy):
        r = self.client.get(reverse("admin:index"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("admin:login"), r["Location"])
