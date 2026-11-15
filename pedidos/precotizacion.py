"""HU 14 CA 4: vista previa del pedido al por mayor como pre-cotización en PDF.

Se arma con ReportLab (no necesita programas externos, funciona igual en Windows).
"""
from io import BytesIO

from django.conf import settings
from django.contrib.staticfiles import finders
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.templatetags.ladyrose import pesos

VINO = colors.HexColor("#5a1a24")
FUCSIA = colors.HexColor("#c9336a")
ROSA_CLARO = colors.HexColor("#f9e3e8")
LINEA = colors.HexColor("#f0d3db")
GRIS = colors.HexColor("#745b62")


def _estilos():
    base = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle("titulo", parent=base["Title"], fontName="Helvetica-Bold", fontSize=18,
                                 textColor=VINO, alignment=0, spaceAfter=2),
        "normal": ParagraphStyle("normal", parent=base["Normal"], fontName="Helvetica", fontSize=9.5, leading=13),
        "suave": ParagraphStyle("suave", parent=base["Normal"], fontName="Helvetica", fontSize=8.5, leading=12,
                                textColor=GRIS),
        "derecha": ParagraphStyle("derecha", parent=base["Normal"], fontName="Helvetica", fontSize=9.5,
                                  leading=13, alignment=TA_RIGHT),
        "celda": ParagraphStyle("celda", parent=base["Normal"], fontName="Helvetica", fontSize=9, leading=12),
    }


def numero_precotizacion(ahora=None):
    ahora = ahora or timezone.localtime()
    return f"PC-{ahora:%Y%m%d-%H%M%S}"


def generar_pdf(items, estado, usuario=None, ahora=None):
    """Devuelve los bytes del PDF con las referencias, cantidades y precios mayoristas."""
    ahora = ahora or timezone.localtime()
    e = _estilos()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=1.6 * cm, bottomMargin=1.6 * cm,
                            title="Pre-cotización al por mayor - Ladyrose", author="Ladyrose")
    partes = []

    # Encabezado: logo a la izquierda, número y fecha a la derecha
    logo = finders.find("img/logo-ladyrose.png")
    izquierda = Image(logo, width=3.2 * cm, height=3.2 * cm * 240 / 317) if logo else Paragraph("Ladyrose", e["titulo"])
    derecha = [
        Paragraph("PRE-COTIZACIÓN AL POR MAYOR", ParagraphStyle("t", parent=e["derecha"], fontName="Helvetica-Bold",
                                                               textColor=VINO, fontSize=11)),
        Paragraph(f"N.° {numero_precotizacion(ahora)}", e["derecha"]),
        Paragraph(f"Fecha: {ahora:%d/%m/%Y %I:%M %p}", e["derecha"]),
    ]
    cabecera = Table([[izquierda, derecha]], colWidths=[8 * cm, 9.6 * cm])
    cabecera.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                  ("LINEBELOW", (0, 0), (-1, 0), 1.2, FUCSIA),
                                  ("BOTTOMPADDING", (0, 0), (-1, 0), 10)]))
    partes += [cabecera, Spacer(1, 12)]

    if usuario is not None and getattr(usuario, "is_authenticated", False):
        nombre = usuario.get_full_name() or usuario.first_name or usuario.username
        partes.append(Paragraph(f"<b>Cliente:</b> {nombre}" + (f" · {usuario.email}" if usuario.email else ""),
                                e["normal"]))
    partes.append(Paragraph(
        f"Tienda: Ladyrose · {settings.LADYROSE['CIUDAD']} · WhatsApp {settings.LADYROSE['WHATSAPP']} · "
        f"{settings.LADYROSE['CORREO']}", e["suave"]))
    partes.append(Spacer(1, 14))

    # Tabla de referencias
    filas = [["Referencia", "Detalle", "Cant.", "Precio mayorista", "Subtotal"]]
    for i in items:
        detalle = []
        if i["talla"]:
            detalle.append(f"Talla {i['talla'].nombre}")
        if i["color"]:
            detalle.append(i["color"])
        filas.append([
            Paragraph(i["producto"].nombre, e["celda"]),
            Paragraph(" · ".join(detalle) or "-", e["celda"]),
            str(i["cantidad"]),
            pesos(i["precio"]),
            pesos(i["subtotal"]),
        ])
    tabla = Table(filas, colWidths=[5.6 * cm, 3.8 * cm, 1.6 * cm, 3.2 * cm, 3.4 * cm], repeatRows=1)
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), VINO),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROSA_CLARO]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINEA),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    partes += [tabla, Spacer(1, 10)]

    # Totales y monto mínimo
    unidades = sum(i["cantidad"] for i in items)
    totales = [
        ["Unidades", str(unidades)],
        ["Subtotal de productos", pesos(estado.subtotal)],
        ["Monto mínimo de compra al por mayor", pesos(estado.minimo)],
    ]
    if not estado.alcanza:
        totales.append(["Falta para el monto mínimo", pesos(estado.falta)])
    resumen = Table(totales, colWidths=[7 * cm, 3.4 * cm], hAlign="RIGHT")
    resumen.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("LINEABOVE", (0, 1), (-1, 1), 0.6, VINO),
        ("TEXTCOLOR", (0, -1), (-1, -1), FUCSIA if not estado.alcanza else colors.black),
    ]))
    partes += [resumen, Spacer(1, 18)]

    notas = [
        "Esta pre-cotización es una vista previa de tu pedido: no reserva las piezas ni es una factura.",
        "El costo del envío se calcula cuando escribes la dirección al confirmar el pedido.",
        "Cada pieza es hecha a mano, por eso puede variar un poco de la foto.",
    ]
    if not estado.alcanza:
        notas.insert(0, f"Para confirmar el pedido te faltan {pesos(estado.falta)} para llegar al monto mínimo.")
    for nota in notas:
        partes.append(Paragraph("• " + nota, e["suave"]))

    doc.build(partes)
    return buffer.getvalue()
