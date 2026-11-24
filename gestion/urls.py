
from django.urls import path
from . import views


urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("panel/", views.panel, name="panel"),
    path("causas/", views.causas, name="causas"),
    path("causas/ingresar/", views.ingresar_causa, name="ingresar_causa"),
    path(
        "causas/consultar-participante/",
        views.consultar_participante,
        name="consultar_participante"
    ),
    path(
        "causas/detalle/<int:id_causa>/",
        views.detalle_causa,
        name="detalle_causa"
    ),
]
