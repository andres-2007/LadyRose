"""Carga los productos, la galería y los cursos reales de Ladyrose.

Uso:
    python manage.py cargar_datos_demo
    python manage.py cargar_datos_demo --reiniciar   # borra los datos anteriores y los vuelve a cargar

Las fotos son las de Ladyrose (carpeta core/demo), sacadas de su Instagram.
Los precios, tallas y materiales son una propuesta inicial: la dueña y la
diseñadora los ajustan desde el panel.

Los pedidos, la cotización, los inscritos y las visitas son de ejemplo (clientes
inventados) para poder mostrar el panel de producción y el panel de la dueña.
"""
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from django.contrib.auth import get_user_model

from catalogo.models import Categoria, Coleccion, FotoProducto, Producto, TallaProducto
from clientes.models import Cliente, CodigoDescuento
from core.models import ContenidoHistoria, FotoTaller, VisitaOrigen
from consultas.models import Consulta, registrar_cotizacion
from cotizaciones.models import SolicitudCotizacion
from cursos.models import Curso, FotoCurso, Inscripcion
from pedidos.models import DetallePedido, Pedido, TiempoEnvio, TipoEmpaque

DEMO = Path(__file__).resolve().parents[2] / "demo"


def archivo(nombre):
    return ContentFile((DEMO / f"{nombre}.jpg").read_bytes(), name=f"{nombre}.jpg")


# Instrucciones de cuidado según el material (HU 02)
CUIDADO_HILO = (
    "Evita mojarla y no la uses en la piscina o el mar. Si se ensucia, límpiala con un paño "
    "apenas húmedo y déjala secar al aire."
)
CUIDADO_CUENTAS = (
    "Guárdalo extendido o en su bolsita para que el hilo no se deforme. Límpialo con un paño seco "
    "y evita el contacto con agua y perfumes."
)
CUIDADO_CRISTAL = (
    "Guárdala sola, en su bolsita o tarjeta, para que los cristales no se rayen. Límpiala con un "
    "paño seco y suave."
)
CUIDADO_METAL = (
    "Guárdalos en un lugar seco y sepáralos de otras piezas. Límpialos con un paño suave y seco "
    "para que el dorado dure más."
)

AJUSTABLE = [("Única", "Ajustable con nudo corredizo")]
PULSERA_S_M = [("S", "16 cm"), ("M", "18 cm")]

# nombre, categoría, imagen, precio, técnica, material, colores, días, tallas, cuidado, descripción
PRODUCTOS = [
    ("Pulsera Corazón Rojo", "Pulseras", "pulsera-corazon-rojo", 18000, "Macramé",
     "Hilo rojo, cuentas rojas y dije de corazón", "", 2, AJUSTABLE, CUIDADO_HILO,
     "Pulsera tejida en hilo rojo con un corazón rojo brillante como protagonista. Es liviana y "
     "sencilla, perfecta para usarla todos los días sola o junto a otras pulseras.\n\n"
     "Se ajusta con nudo corredizo, así que le queda bien a casi cualquier muñeca. Un detalle "
     "ideal para regalar en Amor y Amistad o en un cumpleaños."),
    ("Pulsera Ojo Turco", "Pulseras", "pulsera-ojo-turco", 22000, "Enfilado",
     "Cuentas verde menta, hilo elástico y dije de ojo turco con detalles dorados", "", 2, PULSERA_S_M,
     CUIDADO_CUENTAS,
     "Cuentas verde menta y, al centro, un ojo turco rodeado de detalles dorados. El ojo turco es "
     "un símbolo de protección y buenos deseos, por eso es una de las pulseras que más se regalan.\n\n"
     "Va enfilada en hilo elástico: se pone y se quita fácil, sin cierres."),
    ("Pulsera Cuarzo Rosa", "Pulseras", "pulsera-cuarzo-rosa", 25000, "Macramé",
     "Fragmentos de cuarzo rosa natural, hilo encerado y cuentas doradas", "", 2, AJUSTABLE,
     CUIDADO_HILO,
     "Fragmentos de cuarzo rosa natural montados sobre hilo encerado, con cierre de macramé "
     "ajustable. El cuarzo rosa es conocido como la piedra del amor y la calma.\n\n"
     "Como cada piedra es natural, el tono y la forma de los fragmentos cambian un poco de una "
     "pulsera a otra: la tuya será única."),
    ("Pulsera Escapulario Rojo", "Pulseras", "pulsera-escapulario-rojo", 32000, "Macramé",
     "Hilo rojo tejido en macramé, cuentas y escapulario", "", 3, AJUSTABLE, CUIDADO_HILO,
     "Una de las pulseras más pedidas de Ladyrose: macramé rojo con un escapulario, para llevar la "
     "fe siempre en la muñeca.\n\n"
     "La hemos hecho en todos los colores, pero el rojo es nuestro favorito. Si la quieres en otro "
     "tono, pídela con el botón \"Quiero personalizarlo\"."),
    ("Pulsera Escapulario Azul", "Pulseras", "pulsera-escapulario-azul", 35000, "Tejido en cristal",
     "Cristales facetados azul cielo, cruces doradas y escapulario tejido en cristal", "", 3,
     PULSERA_S_M, CUIDADO_CRISTAL,
     "Pulsera de cristales azul cielo con pequeñas cruces doradas y un escapulario tejido a mano "
     "en cristal alrededor de la imagen.\n\n"
     "No es solo un accesorio: es un recordatorio de fe y de que, incluso en los días difíciles, no "
     "estás sola."),
    ("Dúo Escapulario Virgen del Carmen", "Pulseras", "duo-escapulario", 38000,
     "Macramé y tejido en cristal",
     "Dos pulseras en hilo rojo con detalles dorados y escapulario tejido en cristal rojo", "", 3,
     AJUSTABLE, CUIDADO_CRISTAL,
     "Dos pulseras en hilo rojo con detalles dorados, acompañadas de un escapulario de la Virgen "
     "del Carmen tejido en cristal rojo. Puedes usarlas juntas o por separado.\n\n"
     "Llegan en su tarjeta de Ladyrose, listas para regalar. Un regalo especial para el Día de la Madre."),
    ("Maxicollar Sagrado Corazón", "Collares", "maxicollar-sagrado-corazon", 40000, "Enfilado",
     "Cuentas grandes turquesa y rojas, cuentas doradas y dije de Sagrado Corazón", "", 4,
     [("42 cm", "Clavícula")], CUIDADO_CUENTAS,
     "Maxicollar de cuentas grandes en turquesa y rojo, con un Sagrado Corazón como dije central. "
     "Es una pieza llamativa que le da vida a una camiseta básica o a un vestido sencillo.\n\n"
     "Algunos de sus materiales son difíciles de conseguir, por eso los maxicollares se hacen en "
     "cantidades pequeñas. Pregúntanos por otros colores."),
    ("Maxicollar Corazón Rosa", "Collares", "maxicollar-corazon-rosa", 38000, "Enfilado",
     "Cuentas grandes aguamarina, cuentas rosadas y dije de corazón rosa", "", 4,
     [("42 cm", "Clavícula")], CUIDADO_CUENTAS,
     "Maxicollar en cuentas color aguamarina con un corazón rosa pastel al centro. Sus tonos suaves "
     "lo hacen fácil de combinar y queda perfecto con una blusa básica.\n\n"
     "Si prefieres algo más sutil, mira nuestro choker o pídenos uno en cuentas más pequeñas."),
    ("Maxicollar Concha Fucsia", "Collares", "maxicollar-concha-fucsia", 38000, "Enfilado",
     "Cuentas grandes fucsia, cuentas doradas y dije de concha", "", 4,
     [("42 cm", "Clavícula")], CUIDADO_CUENTAS,
     "Cuentas fucsia brillante y una concha rosada como dije: un maxicollar alegre, con aire de "
     "verano, para los días en que quieres que el accesorio sea el centro de tu look."),
    ("Choker Sagrado Corazón Turquesa", "Collares", "choker-sagrado-corazon", 30000, "Enfilado",
     "Mostacilla turquesa, cuentas doradas y dije de Sagrado Corazón", "", 3,
     [("35 cm", "Base del cuello")], CUIDADO_CUENTAS,
     "Choker de mostacilla turquesa con un Sagrado Corazón rojo y turquesa al centro. Se lleva "
     "ajustado a la base del cuello y combina muy bien con escotes redondos o en V.\n\n"
     "También te lo hacemos en tu color favorito."),
    ("Aretes Dorados", "Aretes", "aretes-dorados", 22000, "Engarce",
     "Topos y dijes en tono dorado", "", 2, [], CUIDADO_METAL,
     "Aretes de topo en tono dorado con un dije colgante. Tenemos tres modelos: corazón, mano de "
     "Fátima y cruz. Son livianos y discretos, para usarlos a diario o regalarlos.\n\n"
     "Después de tu compra te escribimos por WhatsApp para confirmar el modelo que prefieres."),
    ("Portagafas Pastel", "Portagafas", "portagafas-pastel", 25000, "Enfilado",
     "Mostacilla y cuentas en colores pastel, con dijes de corazón y flor", "", 2,
     [("70 cm", "Largo total")], CUIDADO_CUENTAS,
     "Cadena para gafas de mostacilla en tonos pastel, con corazones y florecitas. Sujeta tus gafas "
     "de sol o de lectura para que no se caigan ni se pierdan, y le pone color hasta a los días más "
     "simples."),
    ("Portagafas Turquesa", "Portagafas", "portagafas-turquesa", 25000, "Enfilado",
     "Mostacilla turquesa con cuentas de colores", "", 2, [("70 cm", "Largo total")], CUIDADO_CUENTAS,
     "Cadena para gafas en mostacilla turquesa con pequeños detalles de colores. Práctica para tener "
     "tus gafas siempre a la mano y bonita para llevarla como accesorio con cualquier look."),
    ("Bendición del Hogar", "Bendiciones y denarios", "bendicion-del-hogar", 35000, "Macramé",
     "Hilos encerados, medallas religiosas, dijes y cuentas", "", 4, [], CUIDADO_HILO,
     "Colgante tejido en macramé con medallas religiosas, dijes y cuentas, hecho para proteger y "
     "bendecir tu casa. Se cuelga en la puerta de entrada y también lo puedes llevar en el carro.\n\n"
     "Lo personalizamos con tus colores y las medallas que elijas. Si quieres aprender a hacerlo, "
     "mira nuestro taller de Bendición del Hogar."),
    ("Mini Denario", "Bendiciones y denarios", "mini-denario", 20000, "Enfilado",
     "Perlas y cuentas de colores, dije de cruz o estrella y medalla religiosa",
     "Blanco y rosa, Lila y verde, Blanco y azul", 2, [], CUIDADO_CUENTAS,
     "Denario pequeño de diez cuentas con medalla religiosa, un recuerdo de fe para llevar contigo "
     "o para regalar. El precio es por unidad.\n\n"
     "También lo hacemos por cantidad como recordatorio para primeras comuniones y bautizos, con los "
     "colores de tu celebración: pídelo desde \"Quiero personalizarlo\" y te enviamos la cotización."),
]

# Galería de piezas vendidas (HU 08): pedidos especiales que ya se entregaron.
# El precio no se muestra en la galería.
GALERIA = [
    ("Correa para celular personalizada", "correa-celular", 25000, "Enfilado",
     "Cuentas de colores, florecitas y letras",
     "Correa para celular con cuentas de colores, florecitas y letras con un nombre. La hicimos para "
     "una mamá que quería llevar siempre cerca el nombre de alguien especial."),
    ("Collar con nombre", "collar-nombre", 35000, "Enfilado",
     "Perlas, mostacilla de colores, letras y dije de estrella",
     "Doble collar: uno de perlas y otro de mostacilla de colores con letras lila que forman un "
     "nombre, y una estrella al centro."),
    ("Manilla Miyuki con logo de marca", "manilla-fuxion", 20000, "Tejido Miyuki",
     "Mostacilla Miyuki",
     "Manilla tejida en mostacilla Miyuki con el logo de una marca. Personalizamos manillas con el "
     "logo de tu empresa o emprendimiento para eventos, equipos o regalos corporativos."),
    ("Llavero San Benito en macramé", "llavero-san-benito", 30000, "Macramé",
     "Hilo blanco y negro, medalla de San Benito y dijes",
     "Llavero tejido en macramé blanco y negro con medalla de San Benito y dijes. Una pieza "
     "personalizada, hecha a mano para una clienta muy especial."),
    ("Pulsera roja y dorada con dijes", "pulsera-roja-dorada", 45000, "Macramé",
     "Hilo rojo y blanco, argollas doradas y dijes",
     "Pulsera de hilo rojo y blanco envuelta en argollas doradas, con dijes de ojo turco, piña, "
     "estrella, ala y corazón. El rojo atrae fuerza y el dorado eleva la energía."),
    ("Pulseras \"Para mi persona favorita\"", "pulseras-persona-favorita", 40000, "Enfilado",
     "Mostacilla de colores, perlas, cruz turquesa y dijes dorados",
     "Juego de pulseras de amistad en mostacilla de colores, entregadas en tarjetas de \"Para mi "
     "persona favorita\". Con amigas todo es mejor."),
]

# HU 07: tiempos de envío por ciudad (propuesta inicial; la dueña los ajusta en el panel).
# Cali la crea la migración de pedidos: la entrega Ladyrose directamente, sin transportadora.
# ciudad, mínimo, máximo (días hábiles), por transportadora
TIEMPOS_ENVIO = [
    ("Jamundí", 1, 3, True),
    ("Palmira", 1, 3, True),
    ("Yumbo", 1, 3, True),
    ("Bogotá", 2, 4, True),
    ("Medellín", 2, 4, True),
]

EMPAQUES = [
    ("Caja de regalo con cinta", "Caja rígida con cinta de satín rosa", 8000),
    ("Bolsa de regalo", "Bolsa de papel con papel seda y sticker de Ladyrose", 5000),
]

# Cursos que Ladyrose ya realizó. Se muestran en "Ya realizados".
# nombre, fecha, horario, precio, materiales, imágenes, descripción
CURSOS = [
    ("Taller Bendición del Hogar", date(2026, 5, 16), "2:00 p.m. a 5:00 p.m.", 100000,
     "Todos los materiales para tu pieza: hilos, dijes, medallas y detalles especiales.",
     ["curso-bendicion-1", "curso-bendicion-2"],
     "Taller presencial en Cali para crear tu propia bendición del hogar en técnica macramé. "
     "Diseñas una pieza única, llena de fe, intención y protección para tu casa, con dijes, medallas "
     "y detalles especiales.\n\n"
     "Un espacio pensado para crear con calma, donde cada nudo lleva un significado. No necesitas "
     "experiencia.\n\n"
     "Lugar: Tienda Multimarca Regala'T, Valle del Lili."),
    ("Curso de Bisutería Básica", date(2025, 3, 8), "3:00 p.m. a 6:00 p.m.", 80000,
     "Materiales para la clase, certificado de participación, refrigerio y rifas.",
     ["curso-bisuteria-2"],
     "Curso presencial de tres horas para aprender las bases de la bisutería con la técnica "
     "macramé. Sales con tu propia pulsera terminada.\n\n"
     "Lugar: Cra. 97b #42-29, barrio Calicanto, Cali."),
    ("Curso de Bisutería Básica", date(2025, 3, 22), "3:00 p.m. a 6:00 p.m.", 80000,
     "Materiales e insumos para la clase, certificado de participación, refrigerio y regalo sorpresa.",
     ["curso-bisuteria-1"],
     "Si te apasionan los accesorios o quieres emprender en el mundo de la bisutería, este curso es "
     "para ti. Aprendes tres tipos de tejido en macramé, a usar las herramientas básicas, a elegir "
     "materiales e insumos y las medidas estándar de cada pieza.\n\n"
     "Lugar: Cra. 97b #42-29, Valle del Lili, Cali."),
]


# HU 27: clientes de ejemplo (inventados) para mostrar el panel de cumpleaños y descuentos.
# Todos tienen la contraseña CLAVE_CLIENTES_DEMO.
CLAVE_CLIENTES_DEMO = "Cliente123*"
# nombre, correo, WhatsApp, días que faltan para su cumpleaños (None = no lo dejó)
CLIENTES_DEMO = [
    ("Mariana López", "mariana@correo.com", "3001234567", 3),
    ("Sofía Cárdenas", "sofia@correo.com", "", None),
    ("Valentina Ríos", "valentina@correo.com", "3112223344", 6),
    ("Daniela Mejía", "daniela@correo.com", "3123334455", 40),
]


class Command(BaseCommand):
    help = "Carga los productos, la galería y los cursos de Ladyrose, más pedidos de ejemplo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reiniciar", action="store_true",
            help="Borra productos, colecciones, cursos, pedidos, cotizaciones y visitas antes de cargar. "
                 "No toca los usuarios ni la configuración de la tienda.",
        )

    @transaction.atomic
    def handle(self, *args, **opciones):
        if opciones["reiniciar"]:
            self._borrar()

        productos = {}
        for (nombre, cat, imagen, precio, tecnica, material, colores, dias, tallas, cuidado,
             descripcion) in PRODUCTOS:
            productos[nombre] = self._producto(nombre, cat, imagen, precio, tecnica, material, colores,
                                               dias, tallas, cuidado, descripcion)

        for nombre, imagen, precio, tecnica, material, descripcion in GALERIA:
            self._producto(nombre, "Pedidos especiales", imagen, precio, tecnica, material, "", 5, [],
                           "", descripcion, unica=True, vendida=True)

        for ciudad, minimo, maximo, transportadora in TIEMPOS_ENVIO:
            if not TiempoEnvio.objects.filter(ciudad=ciudad).exists():
                TiempoEnvio.objects.create(ciudad=ciudad, dias_min=minimo, dias_max=maximo,
                                           por_transportadora=transportadora)

        for i, (nombre, descripcion, costo) in enumerate(EMPAQUES):
            TipoEmpaque.objects.get_or_create(nombre=nombre, defaults={"descripcion": descripcion, "costo": costo,
                                                                       "orden": i})

        cursos = []
        for nombre, fecha, horario, precio, materiales, imagenes, descripcion in CURSOS:
            c, creado = Curso.objects.get_or_create(nombre=nombre, fecha=fecha, defaults={
                "tecnica": "Macramé", "modalidad": Curso.Modalidad.PRESENCIAL,
                "tipo_clase": Curso.TipoClase.GRUPAL, "materiales_incluidos": materiales,
                "horario": horario, "precio": precio, "cupos_maximos": 20, "descripcion": descripcion,
            })
            if creado:
                for orden, imagen in enumerate(imagenes):
                    FotoCurso.objects.create(curso=c, imagen=archivo(imagen), orden=orden)
                c.publicado = True
                c.full_clean()
                c.save()
            cursos.append(c)

        # Inscritos de ejemplo para mostrar el panel (HU 26)
        taller = cursos[0]
        if not taller.inscripciones.exists():
            for nombre, pago in [("Valentina Ríos", "pagado"), ("Camila Ortiz", "pagado"),
                                 ("Daniela Mejía", "pendiente")]:
                Inscripcion.objects.create(curso=taller, nombre=nombre, whatsapp="3001234567",
                                           correo=slugify(nombre.split()[0]) + "@correo.com",
                                           modalidad="presencial", estado_pago=pago)

        self._historia()
        self._consultas(productos, cursos)
        self._pedidos(productos)
        self._clientes()

        if not VisitaOrigen.objects.exists():
            for canal, n in [("instagram", 14), ("whatsapp", 8), ("tiktok", 6), ("directo", 9)]:
                for _ in range(n):
                    VisitaOrigen.objects.create(canal=canal, pagina="/")

        self.stdout.write(self.style.SUCCESS("Datos de Ladyrose cargados."))

    # ------------------------------------------------------------------
    def _borrar(self):
        Consulta.objects.all().delete()
        # Solo se borran las cuentas de ejemplo, nunca las de clientes reales
        get_user_model().objects.filter(email__in=[c[1] for c in CLIENTES_DEMO], is_staff=False).delete()
        Pedido.objects.all().delete()
        SolicitudCotizacion.objects.all().delete()
        Curso.objects.all().delete()  # también borra fotos e inscripciones
        Producto.objects.all().delete()  # también borra fotos y tallas
        Categoria.objects.all().delete()
        Coleccion.objects.all().delete()
        TipoEmpaque.objects.all().delete()
        VisitaOrigen.objects.all().delete()
        historia = ContenidoHistoria.obtener()
        historia.fotos.all().delete()
        historia.texto = ""
        historia.save()
        self.stdout.write("Datos anteriores borrados.")

    def _producto(self, nombre, cat, imagen, precio, tecnica, material, colores, dias, tallas, cuidado,
                  descripcion, unica=False, vendida=False):
        categoria, _ = Categoria.objects.get_or_create(nombre=cat)
        p, creado = Producto.objects.get_or_create(nombre=nombre, defaults={
            "categoria": categoria, "precio": precio, "descripcion": descripcion, "tecnica": tecnica,
            "material": material, "colores": colores, "dias_elaboracion": dias,
            # HU 07: el mínimo es un día menos que el máximo (ej. "De 2 a 3 días hábiles")
            "dias_fabricacion_min": max(1, dias - 1),
            "instrucciones_cuidado": cuidado, "pieza_unica": unica, "vendida": vendida,
        })
        if creado:
            FotoProducto.objects.create(producto=p, imagen=archivo(imagen), orden=0)
            for i, (t, m) in enumerate(tallas):
                TallaProducto.objects.create(producto=p, nombre=t, medida=m, orden=i)
        return p

    def _historia(self):
        historia = ContenidoHistoria.obtener()
        if historia.texto:
            return
        historia.texto = (
            "Este texto es de ejemplo: la dueña lo cambia desde el panel con la historia real de "
            "Ladyrose.\n\n"
            "Ladyrose hace bisutería artesanal en Cali: pulseras, collares, escapularios, bendiciones "
            "del hogar y piezas personalizadas. Cada accesorio se hace a mano, uno por uno, y por eso "
            "ninguno sale igual a otro.\n\n"
            "También enseñamos lo que sabemos en nuestros talleres, porque tejer también es una forma "
            "de encontrar calma."
        )
        historia.save()
        for imagen, texto in [("pulsera-roja-dorada", "Hecho a mano, con mucho amor"),
                              ("duo-escapulario", "Cada pieza llega lista para regalar"),
                              ("pulseras-persona-favorita", "Detalles para las personas favoritas")]:
            FotoTaller.objects.create(historia=historia, imagen=archivo(imagen), descripcion=texto)

    def _consultas(self, productos, cursos):
        """HU 28: preguntas de ejemplo (personas inventadas) en distintos estados."""
        if Consulta.objects.exists():
            return
        ahora = timezone.now()
        # nombre, WhatsApp, producto o curso, pregunta, hace cuántas horas llegó, estado
        ejemplos = [
            ("Carolina Duque", "3204445566", productos["Maxicollar Sagrado Corazón"],
             "¿Lo tienen en rosado? Es para un regalo.", 80, Consulta.Estado.NUEVA),
            ("Natalia Herrera", "3115556677", productos["Bendición del Hogar"],
             "¿Me la pueden hacer con la medalla de San Benito?", 30, Consulta.Estado.NUEVA),
            ("Luisa Fernanda Ortiz", "3016667788", cursos[0],
             "¿Cuándo vuelven a abrir el taller de bendición del hogar?", 2, Consulta.Estado.NUEVA),
            ("Paola Martínez", "3127778899", productos["Pulsera Escapulario Azul"],
             "¿Hacen envíos a Pasto?", 50, Consulta.Estado.CONTACTADA),
            ("Jimena Rojas", "3138889900", productos["Portagafas Pastel"],
             "Quería saber el precio por mayor.", 120, Consulta.Estado.DESCARTADA),
        ]
        for nombre, whatsapp, objeto, pregunta, horas, estado in ejemplos:
            es_curso = isinstance(objeto, Curso)
            Consulta.objects.create(
                origen=Consulta.Origen.CURSO if es_curso else Consulta.Origen.PRODUCTO,
                nombre=nombre, whatsapp=whatsapp, mensaje=pregunta, estado=estado,
                curso=objeto if es_curso else None, producto=None if es_curso else objeto,
                fecha=ahora - timedelta(hours=horas),
                contactada_en=ahora - timedelta(hours=horas - 3) if estado != Consulta.Estado.NUEVA else None,
            )

    def _clientes(self):
        """HU 27: cuentas de ejemplo, ligadas a los pedidos de ejemplo con el mismo correo."""
        User = get_user_model()
        hoy = timezone.localdate()
        for nombre, correo, whatsapp, dias in CLIENTES_DEMO:
            if User.objects.filter(username=correo).exists():
                continue
            usuario = User.objects.create_user(username=correo, email=correo, password=CLAVE_CLIENTES_DEMO,
                                               first_name=nombre)
            cumple = (hoy + timedelta(days=dias)).replace(year=1995) if dias is not None else None
            cliente = Cliente.objects.create(usuario=usuario, whatsapp=whatsapp, cumpleanos=cumple)
            Pedido.objects.filter(correo__iexact=correo, cliente=None).update(cliente=usuario)
            if correo == "mariana@correo.com":
                CodigoDescuento.objects.create(
                    cliente=cliente, motivo=CodigoDescuento.Motivo.CUMPLEANOS, codigo="CUMPLE-MARIANA-DEMO",
                    tipo=CodigoDescuento.Tipo.PORCENTAJE, valor=15, vence=hoy + timedelta(days=20),
                )

    def _pedidos(self, productos):
        if Pedido.objects.exists():
            return
        caja = TipoEmpaque.objects.get(nombre="Caja de regalo con cinta")
        cotizacion = SolicitudCotizacion.objects.create(
            tipo=SolicitudCotizacion.Tipo.PERSONALIZADA, nombre="Laura Gómez", whatsapp="3157654321",
            correo="laura@correo.com",
            descripcion="Una correa para celular con cuentas en tonos lila y el nombre \"GLORIA\".",
            motivo="Es para mi mamá, que siempre deja el celular en cualquier parte. Cumple 60 años.",
            acepta_pieza_unica=True, fecha_aceptacion=timezone.now(),
        )
        # HU 28: la cotización queda como consulta; pasa a "Compró" con el pedido de Laura de más abajo
        consulta = registrar_cotizacion(cotizacion)
        Consulta.objects.filter(pk=consulta.pk).update(fecha=timezone.now() - timedelta(days=5))
        ejemplos = [
            # comprador, producto, talla, color, regalo, nota, estado, motivo, canal
            ("Mariana López", "Maxicollar Sagrado Corazón", "42 cm", "", caja,
             "Feliz día, mamá. Gracias por enseñarme que todo es posible.", "pendiente",
             "Es para mi mamá, le encantan los colores fuertes.", "instagram"),
            ("Sofía Cárdenas", "Pulsera Cuarzo Rosa", "Única", "", None, "", "en_curso", "", "tiktok"),
            ("Andrea Patiño", "Bendición del Hogar", "", "", None, "", "en_pausa", "", "whatsapp"),
            ("Juliana Vélez", "Pulsera Ojo Turco", "M", "", None, "", "terminado", "", "directo"),
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
            cotizacion=cotizacion, motivo=cotizacion.motivo, tecnica="Enfilado", dias_elaboracion=4,
            subtotal=Decimal("25000"), total=Decimal("25000"),
        )
        DetallePedido.objects.create(pedido=personal, referencia="Correa para celular personalizada",
                                     color="Lila", material="Cuentas de colores y letras", cantidad=1,
                                     precio_unitario=25000)
