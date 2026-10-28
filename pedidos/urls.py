from django.urls import path

from . import views

app_name = "pedidos"

urlpatterns = [
    path("carrito/", views.carrito, name="carrito"),
    path("carrito/agregar/<int:producto_id>/", views.agregar, name="agregar"),
    path("carrito/actualizar/", views.actualizar, name="actualizar"),
    path("carrito/quitar/", views.quitar, name="quitar"),
    path("pagar/", views.pagar, name="pagar"),
    path("pedido/<int:pk>/confirmado/", views.confirmado, name="confirmado"),
    # Panel de producción
    path("panel/pedidos/", views.panel, name="panel"),
    path("panel/pedidos/<int:pk>/", views.panel_detalle, name="panel_detalle"),
    path("panel/pedidos/<int:pk>/estado/", views.cambiar_estado, name="cambiar_estado"),
    path("panel/pedidos/<int:pk>/avisar/", views.avisar_cliente, name="avisar"),
    path("panel/pedidos/<int:pk>/reanudar/", views.reanudar, name="reanudar"),
]
