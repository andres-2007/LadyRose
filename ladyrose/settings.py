"""
Configuración del proyecto Ladyrose.

Por defecto usa SQLite para que se pueda correr sin instalar nada más.
Para usar PostgreSQL (como dice el documento del proyecto) basta con definir
las variables de entorno DB_ENGINE=postgres, DB_NAME, DB_USER, DB_PASSWORD,
DB_HOST y DB_PORT (ver .env.example y el README).
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _cargar_env():
    """Lee el archivo .env (si existe) sin depender de librerías externas."""
    ruta = BASE_DIR / ".env"
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip())


_cargar_env()

SECRET_KEY = os.environ.get("SECRET_KEY", "solo-para-desarrollo-cambiar-en-produccion")
DEBUG = os.environ.get("DEBUG", "1") == "1"
ALLOWED_HOSTS = [h for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "catalogo",
    "cursos",
    "cotizaciones",
    "pedidos",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # HU 31: registra desde qué red social llega cada visita
    "core.middleware.OrigenVisitaMiddleware",
]

ROOT_URLCONF = "ladyrose.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.datos_tienda",
            ],
        },
    },
]

WSGI_APPLICATION = "ladyrose.wsgi.application"

if os.environ.get("DB_ENGINE", "sqlite") == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "ladyrose"),
            "USER": os.environ.get("DB_USER", "postgres"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# HU 15: en producción las fotos se guardan en la nube y no en el servidor.
# Funciona con cualquier almacenamiento compatible con S3 (Amazon S3,
# Cloudflare R2, Backblaze B2...). En desarrollo se queda en la carpeta media/.
if os.environ.get("MEDIA_STORAGE") == "s3":
    STORAGES = {
        "default": {"BACKEND": "storages.backends.s3.S3Storage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    AWS_STORAGE_BUCKET_NAME = os.environ.get("S3_BUCKET", "")
    AWS_ACCESS_KEY_ID = os.environ.get("S3_ACCESS_KEY", "")
    AWS_SECRET_ACCESS_KEY = os.environ.get("S3_SECRET_KEY", "")
    AWS_S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL") or None
    AWS_S3_REGION_NAME = os.environ.get("S3_REGION") or None
    AWS_QUERYSTRING_AUTH = False
    AWS_S3_FILE_OVERWRITE = False

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Datos de contacto de Ladyrose que se usan en el pie de página y en los botones
# de WhatsApp (HU 31). Se pueden cambiar en el archivo .env.
LADYROSE = {
    "WHATSAPP": os.environ.get("LADYROSE_WHATSAPP", "573000000000"),
    "INSTAGRAM": os.environ.get("LADYROSE_INSTAGRAM", "https://www.instagram.com/"),
    "FACEBOOK": os.environ.get("LADYROSE_FACEBOOK", "https://www.facebook.com/"),
    "TIKTOK": os.environ.get("LADYROSE_TIKTOK", "https://www.tiktok.com/"),
    # HU 34: tiempo estimado de respuesta que se le muestra al cliente
    "TIEMPO_RESPUESTA": os.environ.get("LADYROSE_TIEMPO_RESPUESTA", "24 horas hábiles"),
    # HU 24: datos que ve el cliente cuando elige pagar por transferencia
    "DATOS_TRANSFERENCIA": os.environ.get(
        "LADYROSE_DATOS_TRANSFERENCIA",
        "Nequi o Bancolombia a nombre de Ladyrose. Escríbenos por WhatsApp y te enviamos el número de cuenta.",
    ),
    "CORREO": os.environ.get("LADYROSE_CORREO", "hola@ladyrose.co"),
    "CIUDAD": os.environ.get("LADYROSE_CIUDAD", "Cali, Colombia"),
}

# Correos (HU 10 y HU 26). En desarrollo se muestran en la terminal en vez de enviarse.
# Para enviarlos de verdad pongan EMAIL_HOST y los demás datos en el .env (ver README).
if os.environ.get("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ["EMAIL_HOST"]
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "1") == "1"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "Ladyrose <hola@ladyrose.co>")

LOGIN_URL = "admin:login"
