"""HU 31: registra desde qué red social llega cada visita.

Se toma el canal del parámetro ?utm_source= que traen los enlaces compartidos
desde la página, o del sitio desde el que viene la persona (referer).
Solo se registra la primera página de cada visita (una vez por sesión).
"""
from urllib.parse import urlparse

from .models import VisitaOrigen

DOMINIOS = {
    "instagram.com": VisitaOrigen.Canal.INSTAGRAM,
    "facebook.com": VisitaOrigen.Canal.FACEBOOK,
    "fb.com": VisitaOrigen.Canal.FACEBOOK,
    "tiktok.com": VisitaOrigen.Canal.TIKTOK,
    "whatsapp.com": VisitaOrigen.Canal.WHATSAPP,
    "wa.me": VisitaOrigen.Canal.WHATSAPP,
}

RUTAS_IGNORADAS = ("/admin", "/static", "/media", "/favicon")


def detectar_canal(request):
    utm = (request.GET.get("utm_source") or "").lower().strip()
    if utm:
        validos = {c.value for c in VisitaOrigen.Canal}
        return utm if utm in validos else VisitaOrigen.Canal.OTRO

    referer = request.META.get("HTTP_REFERER", "")
    if not referer:
        return VisitaOrigen.Canal.DIRECTO
    host = (urlparse(referer).hostname or "").lower()
    if host == request.get_host().split(":")[0]:
        return None  # navegación interna, no es una visita nueva
    for dominio, canal in DOMINIOS.items():
        if host == dominio or host.endswith("." + dominio):
            return canal
    return VisitaOrigen.Canal.OTRO


class OrigenVisitaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "GET" and not request.path.startswith(RUTAS_IGNORADAS):
            sesion = request.session
            if not sesion.get("visita_registrada"):
                canal = detectar_canal(request)
                if canal:
                    VisitaOrigen.objects.create(canal=canal, pagina=request.path[:300])
                    sesion["visita_registrada"] = True
                    sesion["canal_origen"] = canal
        return self.get_response(request)
