from django.urls import path

from . import views

app_name = "catalogo"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("colecciones/", views.colecciones, name="colecciones"),
    path("galeria/", views.galeria, name="galeria"),
    path("<slug:slug>/", views.detalle, name="detalle"),
]
