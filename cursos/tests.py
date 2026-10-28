"""Pruebas de los criterios de aceptación de las HU 13 y 21 (Sprint 1) y 26 (Sprint 2)."""
import threading
from datetime import date

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse

from core.tests_utils import PruebaConArchivos, imagen

from .models import Curso, CursoAgotado, FotoCurso, Inscripcion


def datos_curso(**extra):
    datos = dict(
        nombre="Taller Miyuki", tecnica="Tejido Miyuki", materiales_incluidos="Hilos y mostacillas",
        modalidad=Curso.Modalidad.PRESENCIAL, tipo_clase=Curso.TipoClase.GRUPAL,
        fecha=date(2026, 11, 20), horario="9:00 a.m. a 12:00 m.", precio=120000, cupos_maximos=2,
    )
    datos.update(extra)
    return datos


class HU13InformacionCursoTests(PruebaConArchivos):
    def test_ca1_la_pagina_muestra_los_datos_obligatorios(self):
        curso = Curso.objects.create(publicado=True, **datos_curso())
        FotoCurso.objects.create(curso=curso, imagen=imagen())
        r = self.client.get(curso.get_absolute_url())
        for texto in ("Tejido Miyuki", "Hilos y mostacillas", "Presencial", "Grupal",
                      "9:00 a.m. a 12:00 m.", "$120.000"):
            self.assertContains(r, texto)

    def test_ca2_galeria_con_fotos(self):
        curso = Curso.objects.create(publicado=True, **datos_curso())
        FotoCurso.objects.create(curso=curso, imagen=imagen("a.jpg"))
        FotoCurso.objects.create(curso=curso, imagen=imagen("b.jpg"))
        r = self.client.get(curso.get_absolute_url())
        self.assertEqual(r.content.decode().count("data-miniatura="), 2)
        self.assertEqual(curso.fotos.count(), 2)

    def test_ca3_no_se_publica_con_datos_faltantes(self):
        curso = Curso(publicado=True, **datos_curso(tecnica="", precio=None))
        with self.assertRaises(ValidationError):
            curso.full_clean()

    def test_ca3_no_se_publica_sin_foto_desde_el_panel(self):
        admin = User.objects.create_superuser("admin", "a@a.co", "x")
        self.client.force_login(admin)
        datos = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in datos_curso().items()}
        datos.update({
            "descripcion": "", "publicado": "on",
            "fotos-TOTAL_FORMS": "1", "fotos-INITIAL_FORMS": "0", "fotos-0-orden": "0",
            "inscripciones-TOTAL_FORMS": "0", "inscripciones-INITIAL_FORMS": "0",
        })
        r = self.client.post(reverse("admin:cursos_curso_add"), datos)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "No se puede publicar el curso sin al menos una foto.")
        self.assertFalse(Curso.objects.exists())

        datos["fotos-0-imagen"] = imagen()
        r = self.client.post(reverse("admin:cursos_curso_add"), datos)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Curso.objects.get().publicado)

    def test_curso_sin_publicar_no_se_ve(self):
        curso = Curso.objects.create(**datos_curso())
        self.assertEqual(self.client.get(curso.get_absolute_url()).status_code, 404)


class HU21CuposTests(PruebaConArchivos):
    def setUp(self):
        self.curso = Curso.objects.create(publicado=True, **datos_curso(cupos_maximos=2))

    def inscribir(self, nombre):
        return Inscripcion.objects.create(curso=self.curso, nombre=nombre, whatsapp="3001234567",
                                          correo=f"{nombre}@correo.com")

    def test_ca1_cupos_maximos_obligatorio_y_mayor_a_cero(self):
        with self.assertRaises(ValidationError):
            Curso(**datos_curso(cupos_maximos=0)).full_clean()
        sin_cupos = datos_curso()
        sin_cupos.pop("cupos_maximos")
        with self.assertRaises(ValidationError):
            Curso(**sin_cupos).full_clean()

    def test_ca2_cada_pago_confirmado_descuenta_un_cupo(self):
        a = self.inscribir("ana")
        self.assertEqual(self.curso.cupos_disponibles, 2)  # pendiente no descuenta
        a.confirmar_pago()
        self.assertEqual(self.curso.cupos_disponibles, 1)

    def test_ca3_sin_cupos_se_muestra_agotado_y_no_deja_inscribir(self):
        self.inscribir("ana").confirmar_pago()
        self.inscribir("beto").confirmar_pago()
        self.assertTrue(self.curso.agotado)
        r = self.client.get(self.curso.get_absolute_url())
        self.assertContains(r, "Agotado")
        self.assertContains(r, "disabled")

        r = self.client.post(self.curso.get_absolute_url(),
                             {"nombre": "Caro", "whatsapp": "300", "correo": "c@c.co"})
        self.assertEqual(self.curso.inscripciones.count(), 2)

    def test_no_se_confirma_un_pago_si_no_hay_cupo(self):
        self.inscribir("ana").confirmar_pago()
        self.inscribir("beto").confirmar_pago()
        tercera = self.inscribir("caro")
        with self.assertRaises(CursoAgotado):
            tercera.confirmar_pago()
        tercera.estado_pago = Inscripcion.EstadoPago.PAGADO
        with self.assertRaises(ValidationError):
            tercera.full_clean()

    def test_inscripcion_desde_la_pagina(self):
        r = self.client.post(self.curso.get_absolute_url(),
                             {"nombre": "Ana", "whatsapp": "3001234567", "correo": "ana@correo.com"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.curso.inscripciones.get().estado_pago, Inscripcion.EstadoPago.PENDIENTE)


@skipUnlessDBFeature("has_select_for_update")
class HU21InscripcionesSimultaneasTests(TransactionTestCase):
    """Dos pagos confirmados al mismo tiempo por el último cupo.

    SQLite no permite bloquear filas, así que esta prueba solo corre con
    PostgreSQL (DB_ENGINE=postgres). Con SQLite aparece como "skipped".
    """

    def test_solo_una_toma_el_ultimo_cupo(self):
        curso = Curso.objects.create(publicado=True, **datos_curso(cupos_maximos=1))
        a = Inscripcion.objects.create(curso=curso, nombre="ana", whatsapp="300", correo="a@a.co")
        b = Inscripcion.objects.create(curso=curso, nombre="beto", whatsapp="301", correo="b@b.co")
        resultados = []
        barrera = threading.Barrier(2)

        def confirmar(inscripcion):
            barrera.wait()
            try:
                inscripcion.confirmar_pago()
                resultados.append("ok")
            except CursoAgotado:
                resultados.append("agotado")
            finally:
                connection.close()

        hilos = [threading.Thread(target=confirmar, args=(i,)) for i in (a, b)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        self.assertEqual(sorted(resultados), ["agotado", "ok"])
        self.assertEqual(curso.inscripciones.filter(estado_pago="pagado").count(), 1)


class HU26InscritosTests(PruebaConArchivos):
    def setUp(self):
        self.curso = Curso.objects.create(publicado=True, **datos_curso(
            nombre="Alambrismo", modalidad=Curso.Modalidad.VIRTUAL, cupos_maximos=3,
            enlace_conexion="https://meet.google.com/abc-defg-hij"))
        self.admin = User.objects.create_superuser("admin", "a@a.co", "x")

    def test_ca1_el_formulario_pide_nombre_whatsapp_correo_curso_y_modalidad(self):
        r = self.client.get(self.curso.get_absolute_url())
        for campo in ("nombre", "whatsapp", "correo", "curso", "modalidad"):
            self.assertContains(r, f'name="{campo}"')
        r = self.client.post(self.curso.get_absolute_url(), {
            "nombre": "Ana", "whatsapp": "300", "correo": "ana@correo.com",
            "curso": self.curso.pk, "modalidad": "presencial"})
        self.assertContains(r, "Este curso es virtual")
        self.client.post(self.curso.get_absolute_url(), {
            "nombre": "Ana", "whatsapp": "300", "correo": "ana@correo.com",
            "curso": self.curso.pk, "modalidad": "virtual"})
        self.assertEqual(self.curso.inscripciones.get().modalidad, "virtual")

    def test_ca2_el_panel_muestra_inscritos_estado_y_cupos(self):
        Inscripcion.objects.create(curso=self.curso, nombre="Ana", whatsapp="300", correo="a@a.co")
        self.client.force_login(self.admin)
        r = self.client.get(reverse("admin:cursos_curso_change", args=[self.curso.pk]))
        self.assertContains(r, "Ana")
        self.assertContains(r, "Pendiente")
        self.assertContains(r, "Quedan 3")

    def test_ca3_la_duena_cambia_el_estado_de_pago_a_mano(self):
        i = Inscripcion.objects.create(curso=self.curso, nombre="Ana", whatsapp="300", correo="a@a.co")
        self.client.force_login(self.admin)
        r = self.client.post(reverse("admin:cursos_inscripcion_changelist"), {
            "form-TOTAL_FORMS": "1", "form-INITIAL_FORMS": "1", "form-0-id": i.pk,
            "form-0-estado_pago": "pagado", "_save": "Guardar"})
        self.assertEqual(r.status_code, 302)
        i.refresh_from_db()
        self.assertEqual(i.estado_pago, "pagado")
        self.assertEqual(self.curso.cupos_disponibles, 2)

    def test_ca4_descarga_en_excel(self):
        from io import BytesIO

        from openpyxl import load_workbook
        Inscripcion.objects.create(curso=self.curso, nombre="Ana Ríos", whatsapp="300", correo="a@a.co")
        self.client.force_login(self.admin)
        r = self.client.get(reverse("cursos:inscritos_excel", args=[self.curso.pk]))
        self.assertEqual(r["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        hoja = load_workbook(BytesIO(r.content)).active
        self.assertEqual(hoja["A4"].value, "Nombre completo")
        self.assertEqual(hoja["A5"].value, "Ana Ríos")
        self.client.logout()
        self.assertNotEqual(self.client.get(reverse("cursos:inscritos_excel", args=[self.curso.pk])).status_code, 200)

    def test_ca5_al_pasar_a_pagado_se_envia_el_enlace_en_cursos_virtuales(self):
        from django.core import mail
        i = Inscripcion.objects.create(curso=self.curso, nombre="Ana Ríos", whatsapp="300", correo="ana@correo.com")
        self.assertEqual(len(mail.outbox), 0)
        i.confirmar_pago()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("https://meet.google.com/abc-defg-hij", mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, ["ana@correo.com"])
        i.refresh_from_db()
        self.assertIsNotNone(i.enlace_enviado)
        i.save()  # guardar otra vez no repite el correo
        self.assertEqual(len(mail.outbox), 1)

    def test_ca5_en_presencial_no_se_envia_enlace(self):
        from django.core import mail
        curso = Curso.objects.create(publicado=True, **datos_curso(nombre="Miyuki", cupos_maximos=2))
        Inscripcion.objects.create(curso=curso, nombre="Ana", whatsapp="300", correo="a@a.co").confirmar_pago()
        self.assertEqual(len(mail.outbox), 0)
