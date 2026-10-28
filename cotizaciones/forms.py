from django import forms
from django.core.exceptions import ValidationError

from .models import AVISO_PIEZA_UNICA, MAX_IMAGENES, SolicitudCotizacion

FORMATOS_PERMITIDOS = ("image/jpeg", "image/png")
TAMANO_MAXIMO_MB = 5


class VariosArchivosInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class VariasImagenesField(forms.ImageField):
    """Campo que acepta varias imágenes en un solo input."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", VariosArchivosInput(attrs={"accept": "image/jpeg,image/png"}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        if not data:
            return []
        archivos = data if isinstance(data, (list, tuple)) else [data]
        if len(archivos) > MAX_IMAGENES:
            raise ValidationError(f"Puedes adjuntar máximo {MAX_IMAGENES} imágenes.")
        limpios = []
        for archivo in archivos:
            limpio = super().clean(archivo, initial)
            tipo = getattr(archivo, "content_type", "")
            if tipo not in FORMATOS_PERMITIDOS:
                raise ValidationError("Solo se aceptan imágenes JPG o PNG.")
            if archivo.size > TAMANO_MAXIMO_MB * 1024 * 1024:
                raise ValidationError(f"Cada imagen debe pesar máximo {TAMANO_MAXIMO_MB} MB.")
            limpios.append(limpio)
        return limpios


class BaseCotizacionForm(forms.ModelForm):
    imagenes = VariasImagenesField(
        label=f"Imágenes de referencia (máximo {MAX_IMAGENES}, JPG o PNG)", required=False,
    )
    # HU 20: casilla obligatoria. Sin marcarla, el formulario no se envía.
    acepta_pieza_unica = forms.BooleanField(
        label=AVISO_PIEZA_UNICA,
        required=True,
        error_messages={"required": "Debes aceptar el aviso de pieza única para enviar la solicitud."},
    )


class CotizacionForm(BaseCotizacionForm):
    """HU 09 y HU 20: solicitud de una pieza personalizada."""

    class Meta:
        model = SolicitudCotizacion
        fields = ["nombre", "whatsapp", "correo", "descripcion", "motivo"]
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 4}),
            "motivo": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["descripcion"].required = True


class InspiradaForm(CotizacionForm):
    """HU 08: cotización de una pieza inspirada en otra de la galería."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["descripcion"].required = False
        self.fields["descripcion"].label = "¿Qué te gustaría cambiar o mantener? (opcional)"


class PersonalizarProductoForm(BaseCotizacionForm):
    """HU 34: cambios sobre un producto del catálogo."""

    class Meta:
        model = SolicitudCotizacion
        fields = ["nombre", "whatsapp", "correo", "cambio_color", "cambio_talla",
                  "cambio_material", "cambio_otro", "motivo"]
        widgets = {
            "cambio_otro": forms.Textarea(attrs={"rows": 3}),
            "motivo": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        datos = super().clean()
        cambios = ("cambio_color", "cambio_talla", "cambio_material", "cambio_otro")
        if not any((datos.get(c) or "").strip() for c in cambios):
            raise ValidationError("Cuéntanos al menos un cambio (color, talla, material u otro).")
        return datos
