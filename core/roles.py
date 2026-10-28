"""Grupos de usuarios del panel (HU 15).

La dueña y la diseñadora de accesorios entran al panel cada una con su propio
usuario. Según el CA 1 de la HU 15:
- La dueña crea, edita y elimina productos, categorías y cursos.
- La diseñadora crea y edita productos, categorías y colecciones (HU 16), pero
  no puede eliminarlos ni modificar los cursos (solo los ve).
- Las dos ven el panel de producción de pedidos (HU 01).
La configuración de la tienda y las estadísticas de visitas son solo para la dueña.
"""
from django.contrib.auth.models import Group, Permission

GRUPO_DUENA = "Dueña"
GRUPO_DISENADORA = "Diseñadora de accesorios"

CRUD = ("add", "change", "delete", "view")
SIN_BORRAR = ("add", "change", "view")

PERMISOS = {
    GRUPO_DUENA: {
        "catalogo": {"categoria": CRUD, "producto": CRUD, "fotoproducto": CRUD, "tallaproducto": CRUD,
                     "coleccion": CRUD},
        "cursos": {"curso": CRUD, "fotocurso": CRUD, "inscripcion": CRUD},
        "cotizaciones": {"solicitudcotizacion": ("change", "view"), "imagenreferencia": ("view",)},
        "pedidos": {"pedido": CRUD, "detallepedido": CRUD, "tipoempaque": CRUD},
        "core": {
            "configuraciontienda": ("change", "view"),
            "contenidohistoria": ("change", "view"),
            "fototaller": CRUD,
            "visitaorigen": ("view",),
        },
    },
    GRUPO_DISENADORA: {
        # Fotos y tallas son parte de editar el producto, por eso sí puede quitarlas.
        "catalogo": {"categoria": SIN_BORRAR, "producto": SIN_BORRAR, "coleccion": SIN_BORRAR,
                     "fotoproducto": CRUD, "tallaproducto": CRUD},
        "cursos": {"curso": ("view",), "fotocurso": ("view",), "inscripcion": ("view",)},
        "cotizaciones": {"solicitudcotizacion": ("change", "view"), "imagenreferencia": ("view",)},
        # HU 01, 04 y 10: ve los pedidos y cambia su estado de producción, pero no los borra
        "pedidos": {"pedido": ("change", "view"), "detallepedido": ("view",), "tipoempaque": ("view",)},
    },
}


def crear_roles():
    for nombre_grupo, apps in PERMISOS.items():
        grupo, _ = Group.objects.get_or_create(name=nombre_grupo)
        permisos = []
        for app, modelos in apps.items():
            for modelo, acciones in modelos.items():
                for accion in acciones:
                    perm = Permission.objects.filter(
                        content_type__app_label=app, codename=f"{accion}_{modelo}"
                    ).first()
                    if perm:
                        permisos.append(perm)
        grupo.permissions.set(permisos)
