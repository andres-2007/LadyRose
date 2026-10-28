"""Pruebas de los criterios de aceptación de las HU 18, HU 23, HU 25 y HU 31."""
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.urls import reverse

from catalogo.models import Categoria, Producto

from .models import ConfiguracionTienda, ContenidoHistoria, VisitaOrigen
from .tests_utils import PruebaConArchivos


class HU18NuestraHistoriaTests(PruebaConArchivos):
    def test_ca1_el_menu_tiene_la_seccion(self):
        r = self.client.get(reverse("core:inicio"))
        self.assertContains(r, reverse("core:historia"))
        self.assertContains(r, "Nuestra historia")

    def test_ca2_la_duena_edita_el_contenido(self):
        h = ContenidoHistoria.obtener()
        h.texto = "Empezamos en 2015 en la sala de la casa."
        h.save()
        self.assertContains(self.client.get(reverse("core:historia")), "Empezamos en 2015")

    def test_ca3_se_muestra_el_lema(self):
        self.assertContains(self.client.get(reverse("core:historia")), "Todo es posible")


class HU23AdaptableTests(PruebaConArchivos):
    def test_viewport_y_menu_hamburguesa(self):
        r = self.client.get(reverse("core:inicio"))
        self.assertContains(r, 'name="viewport"')
        self.assertContains(r, 'class="menu-boton"')

    def test_css_tiene_punto_de_quiebre_de_768(self):
        from django.contrib.staticfiles import finders
        css = open(finders.find("css/estilos.css"), encoding="utf-8").read()
        self.assertIn("min-width: 768px", css)
        self.assertIn("repeat(2, minmax(0, 1fr))", css)  # dos columnas en celular
        self.assertIn("overflow-x: hidden", css)


class HU25MontoMinimoTests(PruebaConArchivos):
    def test_ca1_valor_inicial_200000(self):
        self.assertEqual(ConfiguracionTienda.obtener().monto_minimo_mayorista, Decimal("200000"))

    def test_ca2_solo_acepta_valores_mayores_a_cero(self):
        conf = ConfiguracionTienda.obtener()
        for valor in (0, -5):
            conf.monto_minimo_mayorista = Decimal(valor)
            with self.assertRaises(ValidationError):
                conf.full_clean()

    def test_ca2_el_panel_rechaza_texto_y_cero(self):
        admin = User.objects.create_superuser("admin", "a@a.co", "x")
        self.client.force_login(admin)
        conf = ConfiguracionTienda.obtener()
        url = reverse("admin:core_configuraciontienda_change", args=[conf.pk])
        for valor in ("0", "abc"):
            r = self.client.post(url, {"monto_minimo_mayorista": valor})
            self.assertEqual(r.status_code, 200)
        r = self.client.post(url, {"monto_minimo_mayorista": "250000"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(ConfiguracionTienda.obtener().monto_minimo_mayorista, Decimal("250000"))

    def test_ca4_el_monto_se_muestra_en_el_modulo_mayorista(self):
        conf = ConfiguracionTienda.obtener()
        conf.monto_minimo_mayorista = Decimal("300000")
        conf.save()
        self.assertContains(self.client.get(reverse("core:mayorista")), "$300.000")


class HU31EnlacesRedesTests(PruebaConArchivos):
    def setUp(self):
        cat = Categoria.objects.create(nombre="Aretes")
        self.producto = Producto.objects.create(nombre="Aretes luna", categoria=cat, precio=32000)

    def test_ca1_boton_compartir_con_copiar_whatsapp_y_facebook(self):
        r = self.client.get(self.producto.get_absolute_url())
        self.assertContains(r, "data-copiar=")
        self.assertContains(r, "https://wa.me/?text=")
        self.assertContains(r, "facebook.com/sharer")
        self.assertContains(r, "utm_source%3Dwhatsapp")

    def test_ca2_el_enlace_lleva_a_la_ficha_con_el_boton_de_compra(self):
        r = self.client.get(self.producto.get_absolute_url() + "?utm_source=instagram")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Comprar por WhatsApp")

    def test_ca3_pie_de_pagina_con_redes_y_whatsapp(self):
        r = self.client.get(reverse("core:inicio"))
        for red in ("Instagram", "Facebook", "TikTok", "WhatsApp"):
            self.assertContains(r, red)

    def test_ca4_se_registra_el_canal_de_cada_visita(self):
        self.client.get(self.producto.get_absolute_url() + "?utm_source=instagram")
        self.assertEqual(VisitaOrigen.objects.get().canal, "instagram")
        # dentro de la misma visita no se vuelve a contar
        self.client.get(reverse("catalogo:lista"))
        self.assertEqual(VisitaOrigen.objects.count(), 1)

    def test_ca4_detecta_el_canal_por_el_sitio_de_origen(self):
        self.client.get(reverse("core:inicio"), HTTP_REFERER="https://l.facebook.com/l.php?u=x")
        self.assertEqual(VisitaOrigen.objects.get().canal, "facebook")

    def test_ca4_la_duena_ve_las_visitas_por_canal_en_el_panel(self):
        VisitaOrigen.objects.create(canal="tiktok", pagina="/")
        admin = User.objects.create_superuser("admin", "a@a.co", "x")
        self.client.force_login(admin)
        r = self.client.get(reverse("admin:core_visitaorigen_changelist"))
        self.assertContains(r, "Visitas por canal")
        self.assertContains(r, "TikTok")


class HU23FotosOptimizadasTests(PruebaConArchivos):
    def test_las_fotos_grandes_se_reducen_al_subirlas(self):
        from PIL import Image

        from catalogo.models import FotoProducto

        from .tests_utils import imagen

        cat = Categoria.objects.create(nombre="Collares")
        producto = Producto.objects.create(nombre="Collar sol", categoria=cat, precio=40000)
        foto = FotoProducto.objects.create(producto=producto, imagen=imagen("grande.jpg", tamano=(4000, 3000)))
        with Image.open(foto.imagen.path) as guardada:
            self.assertEqual(max(guardada.size), 1600)

    def test_las_imagenes_tienen_carga_diferida(self):
        cat = Categoria.objects.create(nombre="Collares")
        from catalogo.models import FotoProducto

        from .tests_utils import imagen

        for i in range(2):
            p = Producto.objects.create(nombre=f"Collar {i}", categoria=cat, precio=40000)
            FotoProducto.objects.create(producto=p, imagen=imagen())
        self.assertContains(self.client.get(reverse("catalogo:lista")), 'loading="lazy"')
