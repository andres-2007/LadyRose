# Ladyrose - Sprint 1 y Sprint 2

Página web de Ladyrose (bisutería artesanal) hecha en Django para el proyecto de Ingeniería de Requisitos.

- Sprint 1: HU 02, 09, 13, 15, 18, 20, 21, 23, 25, 31 y 34.
- Sprint 2: HU 01, 03, 04, 08, 10, 11, 16, 19, 24 y 26.

Equipo: Andres David Duarte y Alejandro Riomaña.

## Qué se necesita

- Python 3.11 a 3.14 (https://www.python.org/downloads/). En Windows, al instalarlo marquen la casilla "Add Python to PATH".
- Git, solo si lo van a subir a GitHub.

No hace falta instalar una base de datos: por defecto usa SQLite. Si el profesor pide PostgreSQL, más abajo está cómo cambiarlo. Las fuentes de la página vienen dentro del proyecto, así que se ve bien aunque no haya internet.

## Cómo correrlo

Abran una terminal dentro de la carpeta `ladyrose` (donde está `manage.py`).

```bash
# 1. Crear el entorno virtual
python -m venv venv

# 2. Activarlo
venv\Scripts\activate          # Windows
source venv/bin/activate       # Mac o Linux

# 3. Instalar las librerías
pip install -r requirements.txt

# 4. Crear la base de datos
python manage.py migrate

# 5. Crear los usuarios de la dueña y de la diseñadora de accesorios
python manage.py crear_usuarios --clave-duena "ClaveDuena123*" --clave-disenadora "ClaveDisena123*"

# 6. (Opcional) Cargar productos, colecciones, cursos y pedidos de ejemplo
python manage.py cargar_datos_demo

# 7. Prender el servidor
python manage.py runserver
```

Después abren:

- Página pública: http://127.0.0.1:8000
- Panel de pedidos de producción: http://127.0.0.1:8000/panel/pedidos/
- Panel completo: http://127.0.0.1:8000/admin

Los usuarios son `duena` y `disenadora`, con la clave que pusieron en el paso 5.

Para apagar el servidor: `Ctrl + C`. La próxima vez solo hay que activar el entorno (paso 2) y correr el paso 7.

### Si ya tenían el proyecto del Sprint 1

Reemplacen los archivos por los nuevos y corran:

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py cargar_datos_demo
```

Si quieren empezar con los datos de ejemplo limpios, borren antes el archivo `db.sqlite3` y la carpeta `media`, y repitan desde el paso 4.

## Pruebas

Cada criterio de aceptación tiene su prueba automática:

```bash
python manage.py test
```

Tienen que salir 102 pruebas en OK, con 1 "skipped" si están en SQLite. Esa es la prueba de dos pagos al mismo tiempo por el último cupo (HU 21), que solo corre en PostgreSQL porque SQLite no deja bloquear filas. Con PostgreSQL corren las 102.

Los nombres de las pruebas dicen la HU y el CA que revisan, por ejemplo `HU04EstadosTests.test_ca2_terminado_pasa_a_listos_para_envio`.

## Correos

La HU 10 (aviso al cliente) y la HU 26 (enlace del curso virtual) envían correos. Mientras están probando en su computador, los correos no se envían: salen escritos en la terminal donde corre el servidor, así se puede mostrar que funcionan. Para enviarlos de verdad, pongan en el `.env` los datos del servidor de correo (`EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`). Están de ejemplo en `.env.example`.

## Usar PostgreSQL (opcional)

1. Crear la base de datos `ladyrose` en PostgreSQL.
2. `pip install "psycopg[binary]"`
3. Copiar `.env.example` como `.env` y poner `DB_ENGINE=postgres` con el usuario y la clave.
4. Correr otra vez `python manage.py migrate` y `crear_usuarios`.

En el `.env` también se cambia el número de WhatsApp, los enlaces de las redes y el texto con los datos para transferencias.

## Fotos

Las imágenes de ejemplo son ilustraciones hechas para el proyecto. La dueña las cambia por las fotos reales desde el panel (Productos, Colecciones, Cursos y Nuestra historia). Las fotos de la portada están en `static/img` y se reemplazan con otra foto del mismo nombre.

Las fotos que se suben se reducen a máximo 1600 px y se comprimen, y en la página cargan de forma diferida para que en el celular no se gasten tantos datos. Para producción se pueden guardar en la nube con cualquier almacenamiento compatible con S3 (`pip install "django-storages[s3]"` y `MEDIA_STORAGE=s3` en el `.env`).

## Dónde está cada HU

### Sprint 1

| HU | Qué hace | Archivos principales |
|---|---|---|
| 02 | Tallas con nombre y medida, cuidados, aviso de lociones y texto del pH | `catalogo/models.py`, `templates/catalogo/detalle.html` |
| 09 | Historia o motivo opcional, hasta 5 imágenes, motivo destacado para la diseñadora | `cotizaciones/forms.py`, `cotizaciones/admin.py`, `templates/pedidos/panel/detalle.html` |
| 13 | Página del curso con todos los datos y galería; no se publica sin datos o sin foto | `cursos/models.py`, `cursos/admin.py` |
| 15 | Panel para productos, categorías y cursos; ofertas con fechas; ocultar sin borrar; roles | `catalogo/admin.py`, `cursos/admin.py`, `core/roles.py` |
| 18 | "Nuestra historia" editable con fotos del taller, video y el lema | `core/models.py`, `templates/core/historia.html` |
| 20 | Casilla obligatoria del aviso de pieza única | `cotizaciones/forms.py` |
| 21 | Cupos máximos; cada pago confirmado descuenta un cupo; "Agotado" | `cursos/models.py` |
| 23 | Diseño para celular (1 o 2 columnas bajo 768 px), menú hamburguesa, fotos optimizadas | `static/css/estilos.css`, `static/js/main.js`, `core/imagenes.py` |
| 25 | Monto mínimo mayorista ($200.000) editable y visible | `core/models.py`, `templates/core/mayorista.html` |
| 31 | Compartir, redes en el pie de página, canal de cada visita y de cada compra | `core/middleware.py`, `templates/partials/compartir.html`, `pedidos/views.py` |
| 34 | "Quiero personalizarlo" con la foto y la referencia del producto | `cotizaciones/views.py`, `templates/cotizaciones/formulario.html` |

### Sprint 2

| HU | Qué hace | Archivos principales |
|---|---|---|
| 01 | Panel de pedidos pendientes con número, foto, técnica y fecha límite; dos formas de ordenar; "No tienes pedidos pendientes" | `pedidos/views.py`, `templates/pedidos/panel/lista.html` |
| 03 | Detalle del pedido: imágenes de referencia, regalo y nota resaltados, historia, talla, color y material | `templates/pedidos/panel/detalle.html` |
| 04 | Estados Pendiente, En curso y Terminado sin salir del panel; "Listos para envío" | `pedidos/views.py`, `static/js/main.js` |
| 08 | Galería de piezas vendidas: la pieza única vendida pasa sola a la galería, sin botón de compra, con cotización de una inspirada | `catalogo/views.py`, `templates/catalogo/galeria.html` |
| 10 | Aviso al cliente por WhatsApp o correo; "En pausa - Esperando respuesta del cliente"; Reanudar | `pedidos/views.py`, `pedidos/forms.py` |
| 11 | Empaques de regalo con costo, nota de máximo 200 caracteres y envío a otra persona | `pedidos/models.py`, `templates/pedidos/pagar.html` |
| 16 | Colecciones con portada; un producto en varias; menú y filtro del catálogo | `catalogo/models.py`, `templates/catalogo/colecciones.html` |
| 19 | Selector con solo las tallas disponibles (también no estándar), guía de medidas y no deja agregar sin talla | `pedidos/carrito.py`, `templates/partials/guia_medidas.html` |
| 24 | Carrito, datos de envío obligatorios, WhatsApp igual al teléfono, contra entrega o transferencia con comprobante, todo en una vista del panel | `pedidos/`, `templates/pedidos/` |
| 26 | Inscripción con curso y modalidad, inscritos y cupos en el panel, cambio de pago a mano, Excel y enlace automático en cursos virtuales | `cursos/forms.py`, `cursos/admin.py`, `cursos/excel.py` |

Las pruebas de cada HU están en el `tests.py` de su carpeta (`catalogo`, `cursos`, `cotizaciones`, `pedidos` y `core`).

## Roles del panel

- Dueña: puede todo. Crea, edita y elimina productos, categorías, colecciones y cursos; maneja pedidos, empaques, inscripciones, la configuración de la tienda, la historia y las visitas por canal.
- Diseñadora de accesorios: crea y edita productos, categorías y colecciones, pero no puede eliminarlos. Los cursos solo los ve. Ve las cotizaciones y, en el panel de producción, cambia el estado de los pedidos y le escribe al cliente.

Los grupos se crean solos al correr `migrate`.

## Cosas que dependen del Sprint 3

- HU 25 (CA 3): el monto queda guardado y se muestra. La validación del pedido mayorista contra ese monto es de la HU 14.
- HU 31 (CA 4): el canal de cada visita y de cada compra ya se guarda y se ve en el panel. Las tarjetas del panel principal de la dueña son de la HU 22.

## Subirlo a GitHub

```bash
git init
git add .
git commit -m "Sprint 1 y 2 de Ladyrose"
git branch -M main
git remote add origin https://github.com/USUARIO/ladyrose.git
git push -u origin main
```

El `.gitignore` ya deja por fuera la base de datos, las imágenes subidas, el `.env` y el entorno virtual.
