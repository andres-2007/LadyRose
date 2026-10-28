"""Carga productos, colecciones, cursos, pedidos y contenido de ejemplo.

Uso:
    python manage.py cargar_datos_demo

Las imágenes son ilustraciones de ejemplo (carpeta core/demo). La dueña las
cambia por las fotos reales desde el panel.
"""
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from catalogo.models import Categoria, Coleccion, FotoProducto, Producto, TallaProducto
from core.models import ContenidoHistoria, FotoTaller, VisitaOrigen
from cotizaciones.models import SolicitudCotizacion
from cursos.models import Curso, FotoCurso, Inscripcion
from pedidos.models import DetallePedido, Pedido, TipoEmpaque

DEMO = Path(__file__).resolve().parents[2] / "demo"


def archivo(nombre):
    return ContentFile((DEMO / f"{nombre}.jpg").read_bytes(), name=f"{nombre}.jpg")


CUIDADO = "Guárdala sola en su bolsita para que no se raye y límpiala con un paño seco y suave."

COLECCIONES = [
    ("Flores del Valle", "portadaFlores",
     "Flores tejidas en mostacilla y flores secas atrapadas en resina, inspiradas en los jardines del Valle del Cauca."),
    ("Lunas y estrellas", "portadaLunas",
     "Lunas en alambre dorado y cielos de mostacilla para quienes viven de noche."),
    ("Novias y fiestas", "portadaNovias",
     "Perlas, tiaras y piezas delicadas para el día más importante."),
]

# nombre, categoría, imagen, precio, oferta, técnica, material, colores, días, tallas, colecciones, única, vendida, descripción
PRODUCTOS = [
    ("Collar Flores de Miyuki", "Collares", "collarFlores", 68000, None, "Tejido Miyuki",
     "Mostacillas Miyuki y cierre dorado", "Rosa, Lila, Coral", 4,
     [("40 cm", "Base del cuello"), ("45 cm", "Clavícula"), ("50 cm", "Debajo de la clavícula")],
     ["Flores del Valle"], False, False,
     "Tres flores tejidas a mano, mostacilla por mostacilla. Liviano y perfecto para el día a día."),
    ("Pulsera Macramé Tierra", "Pulseras", "pulseraMacrame", 32000, 26000, "Macramé",
     "Hilo encerado y piedras naturales", "", 2,
     [("XS", "14 cm"), ("S", "16 cm"), ("M", "18 cm"), ("L", "20 cm")], [], False, False,
     "Nudos de macramé en tonos tierra con una turquesa al centro. Se ajusta con un nudo corredizo."),
    ("Aretes Luna de Alambre", "Aretes", "aretesLuna", 42000, None, "Alambrismo",
     "Alambre de cobre bañado en oro y perla de río", "Dorado, Plateado", 3, [],
     ["Lunas y estrellas"], False, False,
     "Lunas moldeadas a mano en alambre, con una perlita que se mueve cuando caminas."),
    ("Aretes Gota de Resina", "Aretes", "aretesResina", 38000, None, "Resina",
     "Resina, flores secas y ganchos de acero", "", 5, [], ["Flores del Valle"], False, False,
     "Cada gota guarda una flor seca de verdad, así que ninguna es igual a otra."),
    ("Collar Perla Barroca", "Collares", "collarPerla", 85000, None, "Engarce",
     "Perla de río y cadena de acero dorado", "", 3, [("42 cm", "Clavícula"), ("45 cm", "Clavícula")],
     ["Novias y fiestas"], False, False,
     "Una perla de río de forma irregular colgando de una cadena fina. Elegante sin esfuerzo."),
    ("Pulsera Noche Estrellada", "Pulseras", "pulseraEstrellas", 45000, None, "Tejido Miyuki",
     "Mostacillas Miyuki y dijes de estrella", "", 3, [("S", "16 cm"), ("M", "18 cm")],
     ["Lunas y estrellas"], False, False,
     "Mostacilla azul noche con estrellitas doradas repartidas en toda la vuelta."),
    ("Anillo Espiral", "Anillos", "anilloEspiral", 28000, None, "Alambrismo",
     "Alambre de cobre bañado en oro y cuenta de cristal", "", 1,
     [("6", "16,5 mm"), ("7", "17,3 mm"), ("8", "18,1 mm"), ("4", "14,9 mm (talla especial)")], [], False, False,
     "Una espiral con una cuenta de cristal al centro. También lo hacemos en tallas pequeñas."),
    ("Tiara Rocío", "Novias", "tiara", 180000, None, "Alambrismo",
     "Alambre plateado, perlas y cristales", "", 8, [], ["Novias y fiestas"], True, False,
     "Pieza única para novia. Perlas y cristales montados uno a uno sobre alambre plateado."),
    # Galería de piezas vendidas (HU 08)
    ("Collar Árbol de la Vida", "Collares", "collarArbol", 95000, None, "Alambrismo",
     "Alambre dorado, cuarzo rosa y aventurina", "", 6, [], [], True, True,
     "Un árbol tejido en alambre con hojas de cuarzo rosa y aventurina."),
    ("Aretes Mariposa Monarca", "Aretes", "aretesMariposa", 48000, None, "Resina",
     "Resina pintada a mano y ganchos dorados", "", 5, [], ["Flores del Valle"], True, True,
     "Mariposas monarca pintadas a mano y selladas en resina."),
    ("Pulsera Iniciales de Familia", "Pulseras", "pulseraIniciales", 36000, None, "Engarce",
     "Mostacillas, cubos con letras e hilo elástico", "", 2, [], [], True, True,
     "Hecha para una mamá con las iniciales de sus tres hijos."),
]

EMPAQUES = [
    ("Caja de regalo con cinta", "Caja rígida color crema con cinta de satín rosa", 8000),
    ("Bolsa de regalo kraft", "Bolsa de papel con papel seda y sticker de Ladyrose", 5000),
]

CURSOS = [
    ("Taller de tejido Miyuki", "Tejido Miyuki", Curso.Modalidad.PRESENCIAL, Curso.TipoClase.GRUPAL, 8, 120000,
     "cursoMiyuki", "Mostacillas Miyuki, hilo, agujas, telar pequeño y cierre dorado.", 14, "",
     "Aprende la técnica de tejido Miyuki y sal con tu propia pulsera de flores."),
    ("Alambrismo desde cero", "Alambrismo", Curso.Modalidad.VIRTUAL, Curso.TipoClase.INDIVIDUAL, 1, 90000,
     "cursoAlambre", "Kit enviado a tu casa: alambre de cobre, pinzas y cuentas.", 21, "https://meet.google.com/abc-defg-hij",
     "Clase personalizada por videollamada. Hacemos juntas unos aretes de luna."),
    ("Resina con flores secas", "Resina", Curso.Modalidad.AMBAS, Curso.TipoClase.GRUPAL, 6, 140000,
     "cursoResina", "Resina, moldes de silicona, flores secas, guantes y herrajes.", 28, "https://meet.google.com/xyz-abcd-efg",
     "Atrapa flores en resina y llévate un par de aretes y un dije terminados."),
]


class Command(BaseCommand):
    help = "Carga datos de ejemplo para ver la página funcionando."

    @transaction.atomic
    def handle(self, *args, **opciones):
        hoy = timezone.localdate()

        colecciones = {}
        for i, (nombre, imagen, descripcion) in enumerate(COLECCIONES):
            c, creada = Coleccion.objects.get_or_create(nombre=nombre, defaults={"descripcion": descripcion, "orden": i,
                                                                                 "portada": archivo(imagen)})
            colecciones[nombre] = c

        productos = {}
        for (nombre, cat, imagen, precio, oferta, tecnica, material, colores, dias, tallas, cols,
             unica, vendida, descripcion) in PRODUCTOS:
            categoria, _ = Categoria.objects.get_or_create(nombre=cat)
            p, creado = Producto.objects.get_or_create(nombre=nombre, defaults={
                "categoria": categoria, "precio": precio, "descripcion": descripcion, "tecnica": tecnica,
                "material": material, "colores": colores, "dias_elaboracion": dias,
                "instrucciones_cuidado": CUIDADO, "pieza_unica": unica, "vendida": vendida,
            })
            productos[nombre] = p
            if not creado:
                continue
            if oferta:
                p.precio_oferta, p.oferta_inicio, p.oferta_fin = oferta, hoy - timedelta(days=2), hoy + timedelta(days=20)
                p.save()
            FotoProducto.objects.create(producto=p, imagen=archivo(f"{imagen}-1"), orden=0)
            FotoProducto.objects.create(producto=p, imagen=archivo(f"{imagen}-2"), orden=1)
            for i, (t, m) in enumerate(tallas):
                TallaProducto.objects.create(producto=p, nombre=t, medida=m, orden=i,
                                             disponible=not (nombre == "Pulsera Macramé Tierra" and t == "L"))
            p.colecciones.set([colecciones[c] for c in cols])

        for i, (nombre, descripcion, costo) in enumerate(EMPAQUES):
            TipoEmpaque.objects.get_or_create(nombre=nombre, defaults={"descripcion": descripcion, "costo": costo, "orden": i})

        for (nombre, tecnica, modalidad, tipo, cupos, precio, imagen, materiales, dias, enlace,
             descripcion) in CURSOS:
            c, creado = Curso.objects.get_or_create(nombre=nombre, defaults={
                "tecnica": tecnica, "modalidad": modalidad, "tipo_clase": tipo, "materiales_incluidos": materiales,
                "fecha": hoy + timedelta(days=dias), "horario": "9:00 a.m. a 12:00 m.", "precio": precio,
                "cupos_maximos": cupos, "descripcion": descripcion, "enlace_conexion": enlace,
            })
            if creado:
                FotoCurso.objects.create(curso=c, imagen=archivo(imagen))
                c.publicado = True
                c.full_clean()
                c.save()
        miyuki = Curso.objects.get(nombre="Taller de tejido Miyuki")
        if not miyuki.inscripciones.exists():
            for nombre, pago in [("Valentina Ríos", "pagado"), ("Camila Ortiz", "pagado"), ("Daniela Mejía", "pendiente")]:
                Inscripcion.objects.create(curso=miyuki, nombre=nombre, whatsapp="3001234567",
                                           correo=slugify(nombre.split()[0]) + "@correo.com",
                                           modalidad="presencial", estado_pago=pago)

        historia = ContenidoHistoria.obtener()
        if not historia.texto:
            historia.texto = (
                "Ladyrose empezó en la sala de una casa en Cali, con una caja de mostacillas y muchas ganas de "
                "hacer cosas bonitas con las manos. Primero fueron regalos para la familia; después, pedidos de "
                "amigas; y un día nos dimos cuenta de que esto ya era un taller.\n\n"
                "Hoy cada pieza se sigue haciendo a mano, una por una. Por eso ninguna sale igual a otra, y por "
                "eso nos gusta tanto escuchar para quién es cada accesorio que nos piden.\n\n"
                "Este texto es de ejemplo: la dueña lo cambia desde el panel."
            )
            historia.save()
            for imagen, texto in [("cursoMiyuki", "Mostacillas listas para tejer"),
                                  ("cursoAlambre", "Alambre, pinzas y paciencia"),
                                  ("cursoResina", "Flores secas atrapadas en resina")]:
                FotoTaller.objects.create(historia=historia, imagen=archivo(imagen), descripcion=texto)

        self._pedidos(productos)

        if not VisitaOrigen.objects.exists():
            for canal, n in [("instagram", 14), ("whatsapp", 8), ("facebook", 5), ("tiktok", 6), ("directo", 9)]:
                for _ in range(n):
                    VisitaOrigen.objects.create(canal=canal, pagina="/")

        self.stdout.write(self.style.SUCCESS("Datos de ejemplo cargados."))

    def _pedidos(self, productos):
        if Pedido.objects.exists():
            return
        caja = TipoEmpaque.objects.get(nombre="Caja de regalo con cinta")
        cotizacion = SolicitudCotizacion.objects.create(
            tipo=SolicitudCotizacion.Tipo.PERSONALIZADA, nombre="Laura Gómez", whatsapp="3157654321",
            correo="laura@correo.com", descripcion="Unos aretes de luna en plateado, un poco más pequeños.",
            motivo="Son para mi abuela, que siempre dice que la luna la acompaña. Cumple 80 años.",
            acepta_pieza_unica=True, fecha_aceptacion=timezone.now(),
        )
        ejemplos = [
            # comprador, producto, talla, color, regalo, nota, estado, motivo, canal
            ("Mariana López", "Collar Flores de Miyuki", "45 cm", "Rosa", caja,
             "Feliz día, mamá. Gracias por enseñarme que todo es posible.", "pendiente",
             "Es para mi mamá, le encantan las flores.", "instagram"),
            ("Sofía Cárdenas", "Pulsera Macramé Tierra", "S", "", None, "", "en_curso", "", "tiktok"),
            ("Andrea Patiño", "Aretes Gota de Resina", "", "", None, "", "en_pausa", "", "whatsapp"),
            ("Juliana Vélez", "Pulsera Noche Estrellada", "M", "", None, "", "terminado", "", "facebook"),
        ]
        for nombre, prod, talla, color, empaque, nota, estado, motivo, canal in ejemplos:
            p = productos[prod]
            pedido = Pedido.objects.create(
                nombre=nombre, correo=slugify(nombre.split()[0]) + "@correo.com", telefono="3001234567",
                direccion="Calle 5 # 38-25", barrio="San Fernando", ciudad="Cali",
                empaque=empaque, costo_empaque=empaque.costo if empaque else 0, nota=nota, motivo=motivo,
                metodo_pago=Pedido.MetodoPago.CONTRA_ENTREGA, canal_origen=canal,
                enviar_a_otra_persona=bool(empaque), nombre_recibe="Gloria López" if empaque else "",
                telefono_recibe="3109876543" if empaque else "",
            )
            DetallePedido.objects.create(pedido=pedido, producto=p, referencia=p.nombre, talla=talla, color=color,
                                         material=p.material, cantidad=1, precio_unitario=p.precio_actual)
            pedido.subtotal = p.precio_actual
            pedido.total = pedido.subtotal + pedido.costo_empaque
            pedido.calcular_produccion()
            pedido.estado_produccion = estado
            pedido.save()
        # Un pedido personalizado que viene de una cotización
        personal = Pedido.objects.create(
            nombre="Laura Gómez", correo="laura@correo.com", telefono="3157654321", direccion="Carrera 100 # 11-60",
            barrio="Ciudad Jardín", ciudad="Cali", metodo_pago=Pedido.MetodoPago.TRANSFERENCIA,
            cotizacion=cotizacion, motivo=cotizacion.motivo, tecnica="Alambrismo", dias_elaboracion=4,
            subtotal=Decimal("48000"), total=Decimal("48000"),
        )
        DetallePedido.objects.create(pedido=personal, referencia="Aretes luna personalizados", talla="Pequeños",
                                     color="Plateado", material="Alambre plateado", cantidad=1, precio_unitario=48000)
