from django.urls import path

from . import views

app_name = "clientes"

urlpatterns = [
    path("crear/", views.registro, name="registro"),
    path("ingresar/", views.ingresar, name="ingresar"),
    path("salir/", views.salir, name="salir"),
    path("", views.mi_cuenta, name="mi_cuenta"),
]
