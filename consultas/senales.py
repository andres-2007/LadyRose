"""HU 28: una consulta pasa sola a "Compró" cuando esa persona compra.

Se reconoce a la persona por su cuenta, su correo o su número de WhatsApp.
Cuenta como compra un pedido de la tienda o una inscripción a un curso que
quedó pagada.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from cursos.models import Inscripcion
from pedidos.models import Pedido

from .models import Consulta


@receiver(post_save, sender=Pedido, dispatch_uid="consultas_pedido_compro")
def pedido_creado(sender, instance, created, **kwargs):
    if not created:
        return
    for consulta in Consulta.de_la_persona(instance.cliente, instance.correo,
                                           [instance.telefono, instance.whatsapp]).filter(fecha__lte=instance.creado):
        consulta.cambiar_estado(Consulta.Estado.COMPRO, pedido=instance)


@receiver(post_save, sender=Inscripcion, dispatch_uid="consultas_inscripcion_compro")
def inscripcion_pagada(sender, instance, **kwargs):
    if instance.estado_pago != Inscripcion.EstadoPago.PAGADO:
        return
    for consulta in Consulta.de_la_persona(instance.usuario, instance.correo, [instance.whatsapp]):
        consulta.cambiar_estado(Consulta.Estado.COMPRO)
