"""Días hábiles en Colombia (HU 07 y HU 01).

Un día hábil es de lunes a viernes y que no sea festivo. Los festivos se
calculan para cualquier año según la ley colombiana, sin librerías externas:

- Fijos: 1 de enero, 1 de mayo, 20 de julio, 7 de agosto, 8 y 25 de diciembre.
- Ley Emiliani (Ley 51 de 1983): si no caen en lunes, se pasan al lunes siguiente:
  Reyes (6 ene), San José (19 mar), San Pedro y San Pablo (29 jun), Asunción (15 ago),
  Día de la Raza (12 oct), Todos los Santos (1 nov) e Independencia de Cartagena (11 nov).
- Según la Pascua: Jueves y Viernes Santo, y la Ascensión, el Corpus Christi y el
  Sagrado Corazón, que también se pasan al lunes.
"""
from datetime import date, timedelta
from functools import lru_cache


def domingo_de_pascua(anio):
    """Fecha del domingo de Pascua (algoritmo de Meeus/Jones/Butcher)."""
    a = anio % 19
    b, c = divmod(anio, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return date(anio, mes, dia)


def _al_lunes(fecha):
    """Ley Emiliani: si el festivo no cae en lunes, se celebra el lunes siguiente."""
    return fecha + timedelta(days=(7 - fecha.weekday()) % 7)


@lru_cache(maxsize=None)
def festivos_colombia(anio):
    """Conjunto con las fechas de los festivos de Colombia en ese año."""
    fijos = [date(anio, 1, 1), date(anio, 5, 1), date(anio, 7, 20), date(anio, 8, 7),
             date(anio, 12, 8), date(anio, 12, 25)]
    trasladables = [date(anio, 1, 6), date(anio, 3, 19), date(anio, 6, 29), date(anio, 8, 15),
                    date(anio, 10, 12), date(anio, 11, 1), date(anio, 11, 11)]
    pascua = domingo_de_pascua(anio)
    semana_santa = [pascua - timedelta(days=3), pascua - timedelta(days=2)]
    # Ascensión (+39), Corpus Christi (+60) y Sagrado Corazón (+68), pasados al lunes
    segun_pascua = [pascua + timedelta(days=n) for n in (39, 60, 68)]
    return frozenset(fijos + semana_santa + [_al_lunes(f) for f in trasladables + segun_pascua])


def es_dia_habil(fecha):
    return fecha.weekday() < 5 and fecha not in festivos_colombia(fecha.year)


def sumar_dias_habiles(fecha, dias):
    """Suma días hábiles a una fecha (sin contar la fecha de inicio).

    Se saltan los sábados, los domingos y los festivos de Colombia.
    """
    while dias > 0:
        fecha += timedelta(days=1)
        if es_dia_habil(fecha):
            dias -= 1
    return fecha
