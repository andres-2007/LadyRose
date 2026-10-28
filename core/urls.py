from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("nuestra-historia/", views.historia, name="historia"),
    path("al-por-mayor/", views.mayorista, name="mayorista"),
]
