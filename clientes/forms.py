from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Cliente

User = get_user_model()


class RegistroForm(forms.Form):
    """HU 27 CA 6 y CA 3: crear la cuenta con nombre, correo y contraseña; cumpleaños opcional."""

    nombre = forms.CharField(label="Nombre completo", max_length=150,
                             widget=forms.TextInput(attrs={"autocomplete": "name"}))
    correo = forms.EmailField(label="Correo electrónico",
                              widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    whatsapp = forms.CharField(
        label="WhatsApp (opcional)", max_length=20, required=False,
        widget=forms.TextInput(attrs={"inputmode": "tel", "placeholder": "3001234567"}),
        help_text="Por aquí te avisamos de tus pedidos y de tus descuentos.",
    )
    cumpleanos = forms.DateField(
        label="Fecha de cumpleaños (opcional)", required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        help_text="Para enviarte un regalo en tu cumpleaños.",
    )
    password1 = forms.CharField(label="Contraseña", strip=False,
                                widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                                help_text="Mínimo 8 caracteres, que no sean solo números.")
    password2 = forms.CharField(label="Repite la contraseña", strip=False,
                                widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def clean_correo(self):
        correo = self.cleaned_data["correo"].strip().lower()
        if User.objects.filter(username__iexact=correo).exists() or User.objects.filter(email__iexact=correo).exists():
            raise ValidationError("Ya hay una cuenta con este correo. Inicia sesión.")
        return correo

    def clean_cumpleanos(self):
        fecha = self.cleaned_data.get("cumpleanos")
        if fecha and fecha > timezone.localdate():
            raise ValidationError("La fecha de cumpleaños no puede estar en el futuro.")
        return fecha

    def clean_whatsapp(self):
        numero = self.cleaned_data.get("whatsapp", "").strip()
        if numero and len("".join(c for c in numero if c.isdigit())) < 7:
            raise ValidationError("Escribe un número de WhatsApp válido.")
        return numero

    def clean(self):
        datos = super().clean()
        p1, p2 = datos.get("password1"), datos.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Las contraseñas no coinciden.")
        elif p1:
            usuario = User(username=datos.get("correo", ""), email=datos.get("correo", ""),
                           first_name=datos.get("nombre", ""))
            try:
                validate_password(p1, usuario)
            except ValidationError as error:
                self.add_error("password1", error)
        return datos

    @transaction.atomic
    def save(self):
        d = self.cleaned_data
        usuario = User.objects.create_user(username=d["correo"], email=d["correo"], password=d["password1"],
                                           first_name=d["nombre"].strip())
        Cliente.objects.create(usuario=usuario, whatsapp=d.get("whatsapp", ""), cumpleanos=d.get("cumpleanos"))
        return usuario


class IngresarForm(forms.Form):
    """HU 27 CA 6: iniciar sesión con correo y contraseña."""

    correo = forms.EmailField(label="Correo electrónico", widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    password = forms.CharField(label="Contraseña", strip=False,
                               widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        self.usuario = None
        super().__init__(*args, **kwargs)

    def clean(self):
        datos = super().clean()
        correo, clave = (datos.get("correo") or "").lower(), datos.get("password")
        if correo and clave:
            self.usuario = authenticate(self.request, username=correo, password=clave)
            if self.usuario is None:
                raise ValidationError("El correo o la contraseña no son correctos.")
        return datos
