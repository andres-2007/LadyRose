"""Pruebas de los criterios de aceptación de las HU 02 y 15 (Sprint 1) y 08, 16 y 19 (Sprint 2)."""
from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from core.roles import GRUPO_DISENADORA, GRUPO_DUENA, crear_roles
from core.tests_utils import PruebaConArchivos, imagen

from .models import AVISO_CUIDADOS, TEXTO_PH, Categoria, Coleccion, FotoProducto, Producto, TallaProducto


class BaseCatalogo(PruebaConArchivos):
    def setUp(self):
        self.categoria = Categoria.objects.create(nombre="Pulseras")
        self.producto = Producto.objects.create(
            nombre="Pulsera macramé", categoria=self.categoria, precio=28000,
            instrucciones_cuidado="Límpiala con un paño seco.",
        )


class HU02TallasYCuidadosTests(BaseCatalogo):
    def test_ca1_el_producto_registra_tallas_con_nombre_y_medida(self):
        TallaProducto.objects.create(producto=self.producto, nombre="S", medida="16 cm")
        talla = self.producto.tallas.get()
        self.assertEqual((talla.nombre, talla.medida), ("S", "16 cm"))
        self.assertEqual(self.producto.instrucciones_cuidado, "Límpiala con un paño seco.")

    def test_ca2_la_ficha_muestra_las_tallas_disponibles(self):
        TallaProducto.objects.create(producto=self.producto, nombre="S", medida="16 cm")
        TallaProducto.objects.create(producto=self.producto, nombre="M", medida="18 cm")
        r = self.client.get(self.producto.get_absolute_url())
        self.assertContains(r, "Tallas disponibles")
        self.assertContains(r, "16 cm")
        self.assertContains(r, "18 cm")

    def test_ca3_la_ficha_muestra_el_aviso_de_cuidados_por_defecto(self):
        r = self.client.get(self.producto.get_absolute_url())
        self.assertContains(r, AVISO_CUIDADOS)
        self.assertContains(r, "Límpiala con un paño seco.")

    def test_ca4_la_ficha_muestra_el_texto_del_ph(self):
        r = self.client.get(self.producto.get_absolute_url())
        self.assertContains(r, TEXTO_PH)


class HU15AdministracionCatalogoTests(BaseCatalogo):
    def setUp(self):
        super().setUp()
        crear_roles()
        self.duena = User.objects.create_user("duena", password="x", is_staff=True)
        self.duena.groups.add(Group.objects.get(name=GRUPO_DUENA))
        self.disenadora = User.objects.create_user("disenadora", password="x", is_staff=True)
        self.disenadora.groups.add(Group.objects.get(name=GRUPO_DISENADORA))

    def test_ca1_la_duena_crea_edita_y_elimina_productos_categorias_y_cursos(self):
        for modelo in ("producto", "categoria"):
            for accion in ("add", "change", "delete"):
                self.assertTrue(self.duena.has_perm(f"catalogo.{accion}_{modelo}"))
        for accion in ("add", "change", "delete"):
            self.assertTrue(self.duena.has_perm(f"cursos.{accion}_curso"))

    def test_ca1_la_disenadora_crea_y_edita_pero_no_elimina_ni_toca_cursos(self):
        for modelo in ("producto", "categoria"):
            self.assertTrue(self.disenadora.has_perm(f"catalogo.add_{modelo}"))
            self.assertTrue(self.disenadora.has_perm(f"catalogo.change_{modelo}"))
            self.assertFalse(self.disenadora.has_perm(f"catalogo.delete_{modelo}"))
        for accion in ("add", "change", "delete"):
            self.assertFalse(self.disenadora.has_perm(f"cursos.{accion}_curso"))
        self.assertTrue(self.disenadora.has_perm("cursos.view_curso"))

    def test_ca1_la_disenadora_no_puede_borrar_desde_el_panel(self):
        self.client.force_login(self.disenadora)
        url = reverse("admin:catalogo_producto_delete", args=[self.producto.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.post(url, {"post": "yes"})
        self.assertTrue(Producto.objects.filter(pk=self.producto.pk).exists())

    def test_ca1_crear_producto_desde_el_panel(self):
        self.client.force_login(self.disenadora)
        datos = {
            "nombre": "Aretes luna", "categoria": self.categoria.pk, "descripcion": "", "precio": "30000",
            "visible": "on", "precio_oferta": "", "oferta_inicio": "", "oferta_fin": "",
            "instrucciones_cuidado": "", "material": "", "colores": "", "tecnica": "",
            "dias_elaboracion": "3",
            "fotos-TOTAL_FORMS": "1", "fotos-INITIAL_FORMS": "0",
            "fotos-0-imagen": imagen(), "fotos-0-orden": "0",
            "tallas-TOTAL_FORMS": "0", "tallas-INITIAL_FORMS": "0",
        }
        r = self.client.post(reverse("admin:catalogo_producto_add"), datos)
        self.assertEqual(r.status_code, 302)
        nuevo = Producto.objects.get(nombre="Aretes luna")
        self.assertEqual(nuevo.fotos.count(), 1)

    def test_ca2_oferta_con_fecha_de_inicio_y_fin(self):
        hoy = timezone.localdate()
        self.producto.precio_oferta = 20000
        self.producto.oferta_inicio = hoy - timedelta(days=1)
        self.producto.oferta_fin = hoy + timedelta(days=1)
        self.producto.full_clean()
        self.producto.save()
        self.assertTrue(self.producto.en_oferta)
        self.assertEqual(self.producto.precio_actual, 20000)

        self.producto.oferta_fin = hoy - timedelta(days=1)
        self.producto.oferta_inicio = hoy - timedelta(days=5)
        self.assertFalse(self.producto.en_oferta)
        self.assertEqual(self.producto.precio_actual, 28000)

    def test_ca2_oferta_invalida(self):
        self.producto.precio_oferta = 20000  # sin fechas
        with self.assertRaises(ValidationError):
            self.producto.full_clean()

    def test_ca3_producto_oculto_no_se_ve_pero_no_se_borra(self):
        self.producto.visible = False
        self.producto.save()
        self.assertEqual(self.client.get(self.producto.get_absolute_url()).status_code, 404)
        self.assertNotContains(self.client.get(reverse("catalogo:lista")), "Pulsera macramé")
        self.assertTrue(Producto.objects.filter(pk=self.producto.pk).exists())

        self.producto.visible = True
        self.producto.save()
        self.assertEqual(self.client.get(self.producto.get_absolute_url()).status_code, 200)

    def test_ca4_los_cambios_se_ven_al_recargar(self):
        self.producto.precio = 35000
        self.producto.save()
        self.assertContains(self.client.get(self.producto.get_absolute_url()), "$35.000")

    def test_foto_del_producto(self):
        FotoProducto.objects.create(producto=self.producto, imagen=imagen())
        self.assertContains(self.client.get(self.producto.get_absolute_url()), "<img")


# ---------------------------------------------------------------------------
# Sprint 2
# ---------------------------------------------------------------------------

def _datos_envio():
    return {"nombre": "Ana", "telefono": "3001234567", "whatsapp_igual": "on", "direccion": "Calle 1",
            "barrio": "Centro", "ciudad": "Cali", "metodo_pago": "contra_entrega"}


class HU08GaleriaTests(BaseCatalogo):
    def setUp(self):
        super().setUp()
        self.unica = Producto.objects.create(nombre="Collar Árbol", categoria=self.categoria, precio=95000,
                                             pieza_unica=True)

    def test_ca1_al_venderse_pasa_a_la_galeria_en_vez_de_desaparecer(self):
        self.client.post(reverse("pedidos:agregar", args=[self.unica.pk]))
        self.client.post(reverse("pedidos:pagar"), _datos_envio())
        self.unica.refresh_from_db()
        self.assertTrue(self.unica.vendida)
        self.assertNotIn(self.unica, self.client.get(reverse("catalogo:lista")).context["productos"])
        self.assertContains(self.client.get(reverse("catalogo:galeria")), "Collar Árbol")
        self.assertEqual(self.client.get(self.unica.get_absolute_url()).status_code, 200)

    def test_ca2_sin_boton_de_comprar_y_con_aviso_de_insumos(self):
        self.unica.vendida = True
        self.unica.save()
        r = self.client.get(self.unica.get_absolute_url())
        self.assertNotContains(r, "Agregar al carrito")
        self.assertNotContains(r, "Comprar por WhatsApp")
        self.assertContains(r, "depende de que los insumos todavía existan en el mercado")
        r = self.client.post(reverse("pedidos:agregar", args=[self.unica.pk]))
        self.assertEqual(self.client.session.get("carrito", {}), {})

    def test_ca3_boton_para_cotizar_una_inspirada(self):
        self.unica.vendida = True
        self.unica.save()
        url = reverse("cotizaciones:inspirada", args=[self.unica.slug])
        self.assertContains(self.client.get(self.unica.get_absolute_url()), url)
        r = self.client.post(url, {"nombre": "Ana", "whatsapp": "300", "acepta_pieza_unica": "on"})
        self.assertEqual(r.status_code, 302)
        from cotizaciones.models import SolicitudCotizacion
        s = SolicitudCotizacion.objects.get()
        self.assertEqual((s.producto, s.tipo), (self.unica, SolicitudCotizacion.Tipo.INSPIRADA))

    def test_una_pieza_unica_no_se_puede_llevar_dos_veces(self):
        self.client.post(reverse("pedidos:agregar", args=[self.unica.pk]), {"cantidad": 5})
        self.assertEqual(list(self.client.session["carrito"].values()), [1])


class HU16ColeccionesTests(BaseCatalogo):
    def setUp(self):
        super().setUp()
        crear_roles()
        self.verano = Coleccion.objects.create(nombre="Verano", descripcion="Colores vivos", portada=imagen("v.jpg"))
        self.novias = Coleccion.objects.create(nombre="Novias", portada=imagen("n.jpg"))

    def test_ca1_la_disenadora_crea_colecciones_con_nombre_descripcion_y_portada(self):
        disenadora = User.objects.create_user("disenadora", password="x", is_staff=True)
        disenadora.groups.add(Group.objects.get(name=GRUPO_DISENADORA))
        self.assertTrue(disenadora.has_perm("catalogo.add_coleccion"))
        self.client.force_login(disenadora)
        r = self.client.post(reverse("admin:catalogo_coleccion_add"), {
            "nombre": "Día de la madre", "descripcion": "Para mamá", "portada": imagen("p.jpg"),
            "visible": "on", "orden": "0"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Coleccion.objects.filter(nombre="Día de la madre").exists())

    def test_ca2_un_producto_en_varias_colecciones(self):
        self.producto.colecciones.set([self.verano, self.novias])
        self.assertEqual(self.producto.colecciones.count(), 2)
        for c in (self.verano, self.novias):
            self.assertContains(self.client.get(c.get_absolute_url()), "Pulsera macramé")

    def test_ca3_menu_con_colecciones_y_filtro_del_catalogo(self):
        otro = Producto.objects.create(nombre="Aretes sol", categoria=self.categoria, precio=1000)
        self.producto.colecciones.add(self.verano)
        r = self.client.get(reverse("core:inicio"))
        self.assertContains(r, reverse("catalogo:colecciones"))
        self.assertContains(self.client.get(reverse("catalogo:colecciones")), "Verano")
        r = self.client.get(reverse("catalogo:lista") + "?coleccion=" + self.verano.slug)
        self.assertContains(r, "Pulsera macramé")
        self.assertNotContains(r, otro.nombre)


class HU19TallasTests(BaseCatalogo):
    def setUp(self):
        super().setUp()
        self.xs = TallaProducto.objects.create(producto=self.producto, nombre="XS", medida="13 cm")
        self.m = TallaProducto.objects.create(producto=self.producto, nombre="M", medida="18 cm", disponible=False)

    def test_ca1_y_ca2_el_selector_solo_muestra_las_tallas_disponibles_incluso_no_estandar(self):
        r = self.client.get(self.producto.get_absolute_url())
        self.assertContains(r, f'name="talla" value="{self.xs.pk}"')
        self.assertNotContains(r, f'name="talla" value="{self.m.pk}"')
        self.assertContains(r, "13 cm")

    def test_ca3_guia_de_medidas_junto_al_selector(self):
        r = self.client.get(self.producto.get_absolute_url())
        self.assertContains(r, "Guía de medidas")
        self.assertContains(r, "muñeca")
        self.assertContains(r, "Largo del cuello")

    def test_ca4_no_se_agrega_al_carrito_sin_talla(self):
        url = reverse("pedidos:agregar", args=[self.producto.pk])
        r = self.client.post(url, follow=True)
        self.assertContains(r, "Elige una talla")
        self.assertEqual(self.client.session.get("carrito", {}), {})
        self.client.post(url, {"talla": self.m.pk})  # agotada
        self.assertEqual(self.client.session.get("carrito", {}), {})
        self.client.post(url, {"talla": self.xs.pk})
        self.assertEqual(sum(self.client.session["carrito"].values()), 1)

    def test_producto_sin_tallas_se_agrega_directo(self):
        sin = Producto.objects.create(nombre="Aretes", categoria=self.categoria, precio=1000)
        self.client.post(reverse("pedidos:agregar", args=[sin.pk]))
        self.assertEqual(sum(self.client.session["carrito"].values()), 1)
