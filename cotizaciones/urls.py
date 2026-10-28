from django.urls import path

from . import views

app_name = "cotizaciones"

urlpatterns = [
    path("", views.cotizar, name="cotizar"),
    path("producto/<slug:slug>/", views.personalizar, name="personalizar"),
    path("inspirada/<slug:slug>/", views.inspirada, name="inspirada"),
    path("gracias/", views.gracias, name="gracias"),
]
