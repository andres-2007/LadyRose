from django.urls import path

from . import views

app_name = "pedidos"

urlpatterns = [
    path("carrito/", views.carrito, name="carrito"),
    path("carrito/agregar/<int:producto_id>/", views.agregar, name="agregar"),
    path("carrito/actualizar/", views.actualizar, name="actualizar"),
    path("carrito/quitar/", views.quitar, name="quitar"),
    path("pagar/", views.pagar, name="pagar"),
    # HU 14: pedido al por mayor, con su propio carrito
    path("al-por-mayor/pedido/", views.carrito_mayorista, name="carrito_mayorista"),
    path("al-por-mayor/pedido/agregar/<int:producto_id>/", views.agregar_mayorista, name="agregar_mayorista"),
    path("al-por-mayor/pedido/actualizar/", views.actualizar_mayorista, name="actualizar_mayorista"),
    path("al-por-mayor/pedido/quitar/", views.quitar_mayorista, name="quitar_mayorista"),
    path("al-por-mayor/pagar/", views.pagar_mayorista, name="pagar_mayorista"),
    path("al-por-mayor/pagar/tiempo-de-entrega/", views.estimar, {"mayorista": True}, name="estimar_entrega_mayorista"),
    path("al-por-mayor/pagar/codigo/", views.aplicar_codigo, {"mayorista": True}, name="aplicar_codigo_mayorista"),
    path("al-por-mayor/pagar/envio/", views.calcular_envio_vista, {"mayorista": True}, name="calcular_envio_mayorista"),
    path("pagar/tiempo-de-entrega/", views.estimar, name="estimar_entrega"),
    path("pagar/codigo/", views.aplicar_codigo, name="aplicar_codigo"),
    path("pagar/envio/", views.calcular_envio_vista, name="calcular_envio"),
    path("pedido/<int:pk>/confirmado/", views.confirmado, name="confirmado"),
    path("pedido/<int:pk>/", views.mi_pedido, name="mi_pedido"),
    # Panel de producción
    path("panel/pedidos/", views.panel, name="panel"),
    path("panel/pedidos/<int:pk>/", views.panel_detalle, name="panel_detalle"),
    path("panel/pedidos/<int:pk>/estado/", views.cambiar_estado, name="cambiar_estado"),
    path("panel/pedidos/<int:pk>/avisar/", views.avisar_cliente, name="avisar"),
    path("panel/pedidos/<int:pk>/reanudar/", views.reanudar, name="reanudar"),
]
