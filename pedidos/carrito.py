"""HU 24: carrito de compras guardado en la sesión del navegador.

Cada línea se identifica por producto + talla + color, así se pueden llevar
dos tallas del mismo producto como líneas distintas.

HU 14: el pedido al por mayor usa otro carrito (CarritoMayorista), separado del
carrito al detal, con el precio mayorista de cada referencia.
"""
from decimal import Decimal

from catalogo.models import Producto, TallaProducto

CLAVE_SESION = "carrito"
CLAVE_SESION_MAYORISTA = "carrito_mayorista"
MAXIMO_POR_LINEA = 20
MAXIMO_POR_LINEA_MAYORISTA = 500


class ErrorCarrito(Exception):
    pass


class Carrito:
    clave_sesion = CLAVE_SESION
    maximo_por_linea = MAXIMO_POR_LINEA
    mayorista = False

    def __init__(self, request):
        self.session = request.session
        self.lineas = self.session.get(self.clave_sesion, {})

    def _guardar(self):
        self.session[self.clave_sesion] = self.lineas
        self.session.modified = True

    # Lo que cambia entre el carrito al detal y el mayorista
    def disponible(self, producto):
        return producto.se_puede_comprar

    def precio(self, producto):
        return producto.precio_actual

    @staticmethod
    def clave(producto_id, talla_id=None, color=""):
        return f"{producto_id}|{talla_id or ''}|{color}"

    def agregar(self, producto, talla=None, color="", cantidad=1):
        if not self.disponible(producto):
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
        tope = 1 if producto.pieza_unica else self.maximo_por_linea
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
        self.lineas[clave] = min(cantidad, 1 if unica else self.maximo_por_linea)
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
            if not producto or not self.disponible(producto) or (talla_id and not talla):
                invalidas.append(clave)
                continue
            precio = self.precio(producto)
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


class CarritoMayorista(Carrito):
    """HU 14: carrito del módulo al por mayor, separado del carrito al detal."""

    clave_sesion = CLAVE_SESION_MAYORISTA
    maximo_por_linea = MAXIMO_POR_LINEA_MAYORISTA
    mayorista = True

    def disponible(self, producto):
        return producto.se_vende_al_por_mayor

    def precio(self, producto):
        return producto.precio_mayorista
