from django import forms
from django.core.exceptions import ValidationError

from clientes.models import CodigoDescuento, CodigoInvalido

from .envios import MENSAJE_SIN_CONTRA_ENTREGA, calcular_envio, permite_contra_entrega
from .models import MAX_NOTA, BarrioZona, Pedido, TipoEmpaque

OTRO_BARRIO = "otro"

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

    # HU 27: código de descuento asignado a la cuenta del cliente (opcional)
    codigo = forms.CharField(
        label="Código de descuento", max_length=30, required=False,
        widget=forms.TextInput(attrs={"placeholder": "Ej. CUMPLE-PAULA-7K3Q", "autocomplete": "off",
                                      "data-codigo-descuento": ""}),
    )

    # HU 30: en Cali el barrio se escoge de la lista de barrios con tarifa fija, o "Otro barrio"
    barrio_lista = forms.ChoiceField(label="Barrio", required=False)

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
            # HU 07: al escribir la ciudad se calcula el tiempo de envío (ver static/js/main.js)
            "ciudad": forms.TextInput(attrs={"autocomplete": "address-level2", "placeholder": "Cali",
                                             "list": "ciudades-envio", "data-ciudad-entrega": ""}),
            "nombre_recibe": forms.TextInput(),
            "telefono_recibe": forms.TextInput(attrs={"inputmode": "tel"}),
            "nota": forms.Textarea(attrs={"rows": 3, "maxlength": MAX_NOTA, "data-contador": MAX_NOTA,
                                          "placeholder": "Feliz cumpleaños, mamá. Te quiero mucho."}),
            "motivo": forms.Textarea(attrs={"rows": 2}),
            "metodo_pago": forms.RadioSelect,
            "comprobante": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,application/pdf"}),
        }

    def __init__(self, *args, usuario=None, items=None, **kwargs):
        self.usuario = usuario
        self.codigo_descuento = None
        self.items = items or []  # HU 30: (producto, cantidad) para calcular el envío
        self.envio = None
        super().__init__(*args, **kwargs)
        barrios = BarrioZona.objects.filter(zona__activa=True).values_list("nombre", flat=True)
        self.fields["barrio_lista"].choices = (
            [("", "Escoge tu barrio")] + [(b, b) for b in barrios] + [(OTRO_BARRIO, "Otro barrio")]
        )
        self.hay_barrios = bool(barrios)
        # HU 24 CA 1: datos obligatorios para el despacho
        for campo in ("nombre", "telefono", "direccion", "ciudad", "metodo_pago"):
            self.fields[campo].required = True
            self.fields[campo].error_messages["required"] = MENSAJE_OBLIGATORIO
        self.fields["metodo_pago"].error_messages["required"] = "Elige cómo vas a pagar."
        for campo in ("nombre_recibe", "telefono_recibe", "whatsapp", "comprobante"):
            self.fields[campo].required = False
        # El barrio se revisa en clean(): puede venir de la lista (HU 30) o escrito a mano
        self.fields["barrio"].required = False
        self.fields["barrio"].label = "Barrio"
        self.fields["metodo_pago"].choices = Pedido.MetodoPago.choices

    def clean_codigo(self):
        """HU 27 CA 2: solo con la cuenta a la que se asignó, sin usar y sin vencer."""
        texto = self.cleaned_data.get("codigo", "").strip().upper()
        if texto:
            try:
                self.codigo_descuento = CodigoDescuento.buscar(texto, self.usuario)
            except CodigoInvalido as error:
                raise ValidationError(str(error))
        return texto

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
        # HU 30: barrio de la lista (Cali) o escrito a mano
        elegido = datos.get("barrio_lista")
        if elegido and elegido != OTRO_BARRIO:
            datos["barrio"] = elegido
        if not (datos.get("barrio") or "").strip():
            self.add_error("barrio", MENSAJE_OBLIGATORIO)
        # HU 30: costo del envío según la zona o el peso
        if datos.get("ciudad"):
            self.envio = calcular_envio(self.items, datos["ciudad"], datos.get("barrio", ""))
        # HU 12 CA 5: a otras ciudades por transportadora no hay pago contra entrega
        if (datos.get("metodo_pago") == Pedido.MetodoPago.CONTRA_ENTREGA
                and not permite_contra_entrega(datos.get("ciudad", ""))):
            self.add_error("metodo_pago", MENSAJE_SIN_CONTRA_ENTREGA)
        # HU 24 CA 3: si paga antes por transferencia, adjunta el comprobante.
        # HU 30: si el envío está por confirmar, transfiere después, cuando se le confirme el valor.
        por_confirmar = self.envio is not None and self.envio.por_confirmar
        if (datos.get("metodo_pago") == Pedido.MetodoPago.TRANSFERENCIA and not datos.get("comprobante")
                and not por_confirmar):
            self.add_error("comprobante", "Adjunta el comprobante de la transferencia para confirmar el pedido.")
        return datos


class ComprobanteForm(forms.Form):
    """HU 30: el cliente sube el comprobante cuando ya conoce el valor del envío."""

    comprobante = forms.FileField(
        label="Comprobante de la transferencia",
        widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,application/pdf"}),
        error_messages={"required": "Adjunta el comprobante de la transferencia."},
    )

    def clean_comprobante(self):
        archivo = self.cleaned_data["comprobante"]
        if archivo.content_type not in FORMATOS_COMPROBANTE:
            raise ValidationError("El comprobante debe ser una imagen JPG o PNG, o un PDF.")
        if archivo.size > TAMANO_MAXIMO_MB * 1024 * 1024:
            raise ValidationError(f"El comprobante debe pesar máximo {TAMANO_MAXIMO_MB} MB.")
        return archivo


class AvisoClienteForm(forms.Form):
    """HU 10: mensaje al cliente cuando falta un insumo."""

    canal = forms.ChoiceField(choices=[("whatsapp", "WhatsApp"), ("correo", "Correo electrónico")])
    mensaje = forms.CharField(widget=forms.Textarea(attrs={"rows": 5}), max_length=1000)
