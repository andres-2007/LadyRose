from django import forms
from django.core.exceptions import ValidationError

from .models import Curso, Inscripcion


class InscripcionForm(forms.ModelForm):
    """HU 26 CA 1: nombre, WhatsApp, correo, curso y modalidad."""

    curso = forms.ModelChoiceField(queryset=Curso.objects.publicados(), label="Curso", empty_label=None)

    class Meta:
        model = Inscripcion
        fields = ["nombre", "whatsapp", "correo", "curso", "modalidad"]
        widgets = {
            "nombre": forms.TextInput(attrs={"autocomplete": "name"}),
            "whatsapp": forms.TextInput(attrs={"inputmode": "tel", "placeholder": "3001234567"}),
            "correo": forms.EmailInput(attrs={"autocomplete": "email"}),
        }

    def __init__(self, *args, curso=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["modalidad"].required = True
        self.fields["modalidad"].choices = [("", "Elige la modalidad")] + list(Inscripcion.Modalidad.choices)
        if curso:
            self.fields["curso"].initial = curso.pk
            permitidas = curso.modalidades_permitidas
            if len(permitidas) == 1:
                self.fields["modalidad"].initial = permitidas[0]

    def clean(self):
        datos = super().clean()
        curso, modalidad = datos.get("curso"), datos.get("modalidad")
        if curso and modalidad and modalidad not in curso.modalidades_permitidas:
            self.add_error("modalidad", f"Este curso es {curso.get_modalidad_display().lower()}.")
        if curso and curso.agotado:
            self.add_error("curso", "Este curso ya no tiene cupos.")
        return datos
