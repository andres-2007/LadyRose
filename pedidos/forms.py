from django import forms
from django.core.exceptions import ValidationError

from .models import MAX_NOTA, Pedido, TipoEmpaque

FORMATOS_COMPROBANTE = ("image/jpeg", "image/png", "application/pdf")
TAMANO_MAXIMO_MB = 5
MENSAJE_OBLIGATORIO = "Este dato es obligatorio para poder despachar tu pedido."


class EmpaqueChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.nombre


class PedidoForm(forms.ModelForm):
    """HU 24 y HU 11: formulario del proceso de pago."""

    empaque = EmpaqueChoiceField(
        queryset=TipoEmpaque.objects.filter(activo=True), required=False,
        empty_label="Empaque normal (sin costo)", widget=forms.RadioSelect,
        label="Empaque",
    )

    class Meta:
        model = Pedido
        fields = [
            "nombre", "correo", "telefono", "whatsapp_igual", "whatsapp",
            "direccion", "barrio", "ciudad", "indicaciones",
            "enviar_a_otra_persona", "nombre_recibe", "telefono_recibe",
            "empaque", "nota", "motivo",
            "metodo_pago", "comprobante",
        ]
        labels = {
            "nombre": "Nombre completo",
            "motivo": "¿Es para alguien especial? Cuéntanos (opcional)",
            "nota": "Nota para la tarjeta",
        }
        widgets = {
            "nombre": forms.TextInput(attrs={"autocomplete": "name"}),
            "correo": forms.EmailInput(attrs={"autocomplete": "email"}),
            "telefono": forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "tel", "placeholder": "3001234567"}),
            "whatsapp": forms.TextInput(attrs={"inputmode": "tel", "placeholder": "3001234567"}),
            "direccion": forms.TextInput(attrs={"autocomplete": "street-address", "placeholder": "Calle 5 # 38-25"}),
            "barrio": forms.TextInput(attrs={"placeholder": "San Fernando"}),
            "ciudad": forms.TextInput(attrs={"autocomplete": "address-level2", "placeholder": "Cali"}),
            "nombre_recibe": forms.TextInput(),
            "telefono_recibe": forms.TextInput(attrs={"inputmode": "tel"}),
            "nota": forms.Textarea(attrs={"rows": 3, "maxlength": MAX_NOTA, "data-contador": MAX_NOTA,
                                          "placeholder": "Feliz cumpleaños, mamá. Te quiero mucho."}),
            "motivo": forms.Textarea(attrs={"rows": 2}),
            "metodo_pago": forms.RadioSelect,
            "comprobante": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,application/pdf"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # HU 24 CA 1: datos obligatorios para el despacho
        for campo in ("nombre", "telefono", "direccion", "barrio", "ciudad", "metodo_pago"):
            self.fields[campo].required = True
            self.fields[campo].error_messages["required"] = MENSAJE_OBLIGATORIO
        self.fields["metodo_pago"].error_messages["required"] = "Elige cómo vas a pagar."
        for campo in ("nombre_recibe", "telefono_recibe", "whatsapp", "comprobante"):
            self.fields[campo].required = False
        self.fields["metodo_pago"].choices = Pedido.MetodoPago.choices

    def clean_comprobante(self):
        archivo = self.cleaned_data.get("comprobante")
        if archivo and hasattr(archivo, "content_type"):
            if archivo.content_type not in FORMATOS_COMPROBANTE:
                raise ValidationError("El comprobante debe ser una imagen JPG o PNG, o un PDF.")
            if archivo.size > TAMANO_MAXIMO_MB * 1024 * 1024:
                raise ValidationError(f"El comprobante debe pesar máximo {TAMANO_MAXIMO_MB} MB.")
        return archivo

    def clean(self):
        datos = super().clean()
        # HU 24 CA 2: WhatsApp igual al teléfono o uno distinto
        if not datos.get("whatsapp_igual") and not (datos.get("whatsapp") or "").strip():
            self.add_error("whatsapp", "Escribe tu número de WhatsApp o marca que es el mismo de llamadas.")
        # HU 11 CA 3: datos de la otra persona
        if datos.get("enviar_a_otra_persona"):
            for campo in ("nombre_recibe", "telefono_recibe"):
                if not (datos.get(campo) or "").strip():
                    self.add_error(campo, "Escribe los datos de la persona que recibe el regalo.")
        else:
            datos["nombre_recibe"] = datos.get("nombre", "")
            datos["telefono_recibe"] = datos.get("telefono", "")
        # HU 24 CA 3: si paga antes por transferencia, adjunta el comprobante
        if datos.get("metodo_pago") == Pedido.MetodoPago.TRANSFERENCIA and not datos.get("comprobante"):
            self.add_error("comprobante", "Adjunta el comprobante de la transferencia para confirmar el pedido.")
        return datos


class AvisoClienteForm(forms.Form):
    """HU 10: mensaje al cliente cuando falta un insumo."""

    canal = forms.ChoiceField(choices=[("whatsapp", "WhatsApp"), ("correo", "Correo electrónico")])
    mensaje = forms.CharField(widget=forms.Textarea(attrs={"rows": 5}), max_length=1000)
