"""Pruebas de los criterios de aceptación de las HU 09, HU 20 y HU 34."""
from django.contrib.auth.models import Group, User
from django.urls import reverse

from catalogo.models import Categoria, FotoProducto, Producto
from core.roles import GRUPO_DISENADORA, GRUPO_DUENA, crear_roles
from core.tests_utils import PruebaConArchivos, imagen

from .models import AVISO_PIEZA_UNICA, SolicitudCotizacion


def datos_base(**extra):
    datos = {"nombre": "Ana", "whatsapp": "3001234567", "correo": "ana@correo.com",
             "descripcion": "Un collar con dije de luna", "motivo": "", "acepta_pieza_unica": "on"}
    datos.update(extra)
    return datos


class HU09HistoriaEnCotizacionTests(PruebaConArchivos):
    def test_ca1_el_motivo_es_opcional(self):
        r = self.client.post(reverse("cotizaciones:cotizar"), datos_base())
        self.assertRedirects(r, reverse("cotizaciones:gracias"))
        r = self.client.post(reverse("cotizaciones:cotizar"),
                             datos_base(motivo="Es para mi mamá, que cumple 60 años"))
        self.assertRedirects(r, reverse("cotizaciones:gracias"))
        self.assertEqual(SolicitudCotizacion.objects.filter(motivo__icontains="mamá").count(), 1)

    def test_ca2_permite_hasta_5_imagenes(self):
        datos = datos_base(imagenes=[imagen(f"{i}.jpg") for i in range(5)])
        r = self.client.post(reverse("cotizaciones:cotizar"), datos)
        self.assertRedirects(r, reverse("cotizaciones:gracias"))
        self.assertEqual(SolicitudCotizacion.objects.get().imagenes.count(), 5)

    def test_ca2_rechaza_6_imagenes_o_formatos_no_validos(self):
        r = self.client.post(reverse("cotizaciones:cotizar"),
                             datos_base(imagenes=[imagen(f"{i}.jpg") for i in range(6)]))
        self.assertContains(r, "máximo 5 imágenes")
        r = self.client.post(reverse("cotizaciones:cotizar"),
                             datos_base(imagenes=[imagen("a.gif", "GIF", "image/gif")]))
        self.assertContains(r, "JPG o PNG")
        self.assertFalse(SolicitudCotizacion.objects.exists())

    def test_ca3_el_motivo_aparece_destacado_en_el_panel(self):
        s = SolicitudCotizacion.objects.create(nombre="Ana", whatsapp="300", descripcion="x",
                                               motivo="Es para mi mamá", acepta_pieza_unica=True)
        admin = User.objects.create_superuser("admin", "a@a.co", "x")
        self.client.force_login(admin)
        r = self.client.get(reverse("admin:cotizaciones_solicitudcotizacion_change", args=[s.pk]))
        self.assertContains(r, "Historia o motivo")
        self.assertContains(r, "Es para mi mamá")


class HU20AvisoPiezaUnicaTests(PruebaConArchivos):
    def test_ca1_y_ca2_el_formulario_muestra_la_casilla_con_el_aviso(self):
        r = self.client.get(reverse("cotizaciones:cotizar"))
        self.assertContains(r, 'name="acepta_pieza_unica"')
        self.assertContains(r, "cada pieza es única e irrepetible")

    def test_ca3_sin_marcar_la_casilla_no_se_envia(self):
        datos = datos_base()
        datos.pop("acepta_pieza_unica")
        r = self.client.post(reverse("cotizaciones:cotizar"), datos)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Debes aceptar el aviso de pieza única")
        self.assertFalse(SolicitudCotizacion.objects.exists())

    def test_se_guarda_la_aceptacion(self):
        self.client.post(reverse("cotizaciones:cotizar"), datos_base())
        s = SolicitudCotizacion.objects.get()
        self.assertTrue(s.acepta_pieza_unica)
        self.assertIsNotNone(s.fecha_aceptacion)


class HU34PersonalizarProductoTests(PruebaConArchivos):
    def setUp(self):
        cat = Categoria.objects.create(nombre="Collares")
        self.producto = Producto.objects.create(nombre="Collar Miyuki", categoria=cat, precio=45000)
        FotoProducto.objects.create(producto=self.producto, imagen=imagen())
        self.url = reverse("cotizaciones:personalizar", args=[self.producto.slug])

    def test_ca1_la_ficha_tiene_el_boton_quiero_personalizarlo(self):
        r = self.client.get(self.producto.get_absolute_url())
        self.assertContains(r, "Quiero personalizarlo")
        self.assertContains(r, self.url)

    def test_ca2_el_formulario_trae_referencia_y_foto(self):
        r = self.client.get(self.url)
        self.assertContains(r, "Collar Miyuki")
        self.assertContains(r, self.producto.foto_principal.imagen.url)
        for campo in ("cambio_color", "cambio_talla", "cambio_material", "cambio_otro", "imagenes"):
            self.assertContains(r, f'name="{campo}"')

    def test_ca2_debe_indicar_al_menos_un_cambio(self):
        r = self.client.post(self.url, {"nombre": "Ana", "whatsapp": "300", "acepta_pieza_unica": "on"})
        self.assertContains(r, "al menos un cambio")

    def test_ca3_queda_como_cotizacion_ligada_al_producto_y_la_ven_las_dos(self):
        self.client.post(self.url, {"nombre": "Ana", "whatsapp": "300", "cambio_color": "Dorado",
                                    "acepta_pieza_unica": "on"})
        s = SolicitudCotizacion.objects.get()
        self.assertEqual(s.producto, self.producto)
        self.assertEqual(s.tipo, SolicitudCotizacion.Tipo.CAMBIOS_PRODUCTO)
        crear_roles()
        for grupo in (GRUPO_DUENA, GRUPO_DISENADORA):
            self.assertTrue(Group.objects.get(name=grupo).permissions.filter(
                codename="view_solicitudcotizacion").exists())

    def test_ca4_mensaje_de_confirmacion_con_tiempo_de_respuesta(self):
        r = self.client.post(self.url, {"nombre": "Ana", "whatsapp": "300", "cambio_talla": "S",
                                        "acepta_pieza_unica": "on"}, follow=True)
        self.assertContains(r, "Recibimos tu solicitud")
        self.assertContains(r, "24 horas hábiles")

    def test_tambien_pide_aceptar_el_aviso(self):
        self.assertIn("única e irrepetible", AVISO_PIEZA_UNICA)
