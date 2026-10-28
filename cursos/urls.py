from django.urls import path

from . import views

app_name = "cursos"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("<int:pk>/inscritos.xlsx", views.descargar_inscritos, name="inscritos_excel"),
    path("<slug:slug>/", views.detalle, name="detalle"),
]
