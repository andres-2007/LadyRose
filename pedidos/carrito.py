"""HU 24: carrito de compras guardado en la sesión del navegador.

Cada línea se identifica por producto + talla + color, así se pueden llevar
dos tallas del mismo producto como líneas distintas.
"""
from decimal import Decimal

from catalogo.models import Producto, TallaProducto

CLAVE_SESION = "carrito"
MAXIMO_POR_LINEA = 20


class ErrorCarrito(Exception):
    pass


class Carrito:
    def __init__(self, request):
        self.session = request.session
        self.lineas = self.session.get(CLAVE_SESION, {})

    def _guardar(self):
        self.session[CLAVE_SESION] = self.lineas
        self.session.modified = True

    @staticmethod
    def clave(producto_id, talla_id=None, color=""):
        return f"{producto_id}|{talla_id or ''}|{color}"

    def agregar(self, producto, talla=None, color="", cantidad=1):
        if not producto.se_puede_comprar:
            raise ErrorCarrito("Este producto ya no está disponible.")
        # HU 19: si el producto tiene tallas hay que elegir una disponible
        tallas = producto.tallas_disponibles
        if tallas and (talla is None or talla not in tallas):
            raise ErrorCarrito("Elige una talla antes de agregar el producto al carrito.")
        colores = producto.lista_colores
        if len(colores) > 1 and color not in colores:
            raise ErrorCarrito("Elige un color antes de agregar el producto al carrito.")
        if len(colores) == 1:
            color = colores[0]
        clave = self.clave(producto.pk, talla.pk if talla else None, color)
        nueva = self.lineas.get(clave, 0) + max(int(cantidad), 1)
        # Una pieza única solo se puede comprar una vez (HU 08)
        tope = 1 if producto.pieza_unica else MAXIMO_POR_LINEA
        self.lineas[clave] = min(nueva, tope)
        self._guardar()
        return clave

    def actualizar(self, clave, cantidad):
        if clave not in self.lineas:
            return
        cantidad = int(cantidad)
        if cantidad <= 0:
            self.quitar(clave)
            return
        producto_id = int(clave.split("|")[0])
        unica = Producto.objects.filter(pk=producto_id, pieza_unica=True).exists()
        self.lineas[clave] = min(cantidad, 1 if unica else MAXIMO_POR_LINEA)
        self._guardar()

    def quitar(self, clave):
        self.lineas.pop(clave, None)
        self._guardar()

    def vaciar(self):
        self.lineas = {}
        self._guardar()

    def items(self):
        """Devuelve las líneas con su producto. Quita lo que ya no se puede comprar."""
        ids = {int(c.split("|")[0]) for c in self.lineas}
        productos = Producto.objects.filter(pk__in=ids).prefetch_related("fotos", "tallas")
        productos = {p.pk: p for p in productos}
        tallas = {t.pk: t for t in TallaProducto.objects.filter(producto_id__in=ids)}
        resultado, invalidas = [], []
        for clave, cantidad in self.lineas.items():
            producto_id, talla_id, color = clave.split("|", 2)
            producto = productos.get(int(producto_id))
            talla = tallas.get(int(talla_id)) if talla_id else None
            if not producto or not producto.se_puede_comprar or (talla_id and not talla):
                invalidas.append(clave)
                continue
            precio = producto.precio_actual
            resultado.append({
                "clave": clave, "producto": producto, "talla": talla, "color": color,
                "cantidad": cantidad, "precio": precio, "subtotal": precio * cantidad,
            })
        if invalidas:
            for clave in invalidas:
                self.lineas.pop(clave, None)
            self._guardar()
        return resultado

    def subtotal(self):
        return sum((i["subtotal"] for i in self.items()), Decimal(0))

    def __len__(self):
        return sum(self.lineas.values())
