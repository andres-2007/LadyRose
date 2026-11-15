from django.urls import path

from . import views

app_name = "consultas"

urlpatterns = [
    path("producto/<slug:slug>/", views.preguntar_producto, name="preguntar_producto"),
    path("curso/<slug:slug>/", views.preguntar_curso, name="preguntar_curso"),
]
