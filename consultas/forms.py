from django import forms
from django.core.exceptions import ValidationError

from .models import Consulta


class PreguntaForm(forms.ModelForm):
    """HU 28: formulario "Pregúntanos" de la ficha de un producto o de un curso."""

    class Meta:
        model = Consulta
        fields = ["nombre", "whatsapp", "mensaje"]
        labels = {"nombre": "Tu nombre", "whatsapp": "Tu WhatsApp", "mensaje": "Tu pregunta"}
        widgets = {
            "nombre": forms.TextInput(attrs={"autocomplete": "name"}),
            "whatsapp": forms.TextInput(attrs={"inputmode": "tel", "placeholder": "3001234567"}),
            "mensaje": forms.Textarea(attrs={"rows": 3, "placeholder": "¿Lo tienen en otro color? ¿Cuánto tarda en llegar a Bogotá?"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in ("nombre", "whatsapp", "mensaje"):
            self.fields[campo].required = True
            self.fields[campo].error_messages["required"] = "Este dato es obligatorio para poder responderte."

    def clean_whatsapp(self):
        numero = self.cleaned_data["whatsapp"].strip()
        if len("".join(c for c in numero if c.isdigit())) < 7:
            raise ValidationError("Escribe un número de WhatsApp válido para poder responderte.")
        return numero


def datos_iniciales(usuario):
    """Si el cliente inició sesión, el formulario se llena con su cuenta (HU 27)."""
    if not getattr(usuario, "is_authenticated", False):
        return {}
    cliente = getattr(usuario, "cliente", None)
    return {"nombre": usuario.get_full_name() or usuario.first_name,
            "whatsapp": cliente.whatsapp_contacto if cliente else ""}
