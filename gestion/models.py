
from django.db import models


class Perfil(models.Model):
    id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=50)
    descripcion = models.CharField(max_length=150)

    class Meta:
        db_table = "perfil"


class Usuario(models.Model):
    id = models.AutoField(primary_key=True)
    rut = models.CharField(max_length=12)
    nombres = models.CharField(max_length=50)
    apellidos = models.CharField(max_length=50)
    correo = models.CharField(max_length=100)
    estado = models.CharField(max_length=1)
    perfil = models.ForeignKey(
        Perfil,
        on_delete=models.PROTECT,
        db_column="perfil_id"
    )

    class Meta:
        db_table = "usuario"


class Causa(models.Model):
    id_causa = models.AutoField(primary_key=True)
    nic = models.IntegerField()
    fecha_ingreso = models.DateField()
    estado = models.CharField(max_length=70)
    fecha_cierre = models.DateField(null=True, blank=True)
    fecha_extension = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "causa"


class Participante(models.Model):
    rut = models.CharField(max_length=12, primary_key=True)
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    fecha_nacimiento = models.DateField()
    direccion = models.CharField(max_length=200)
    telefono = models.CharField(max_length=20)
    correo = models.CharField(max_length=100)

    class Meta:
        db_table = "participante"


class ParticipanteCausa(models.Model):
    pk = models.CompositePrimaryKey("participante", "causa")
    rol = models.CharField(max_length=20)
    participante = models.ForeignKey(
        Participante,
        on_delete=models.PROTECT,
        db_column="rut"
    )
    causa = models.ForeignKey(
        Causa,
        on_delete=models.PROTECT,
        db_column="id_causa"
    )

    class Meta:
        db_table = "participante_causa"


class Materia(models.Model):
    id = models.AutoField(primary_key=True)
    tipo = models.CharField(max_length=100)

    class Meta:
        db_table = "materia"


class CausaMateria(models.Model):
    pk = models.CompositePrimaryKey("materia", "causa")
    materia = models.ForeignKey(
        Materia,
        on_delete=models.PROTECT,
        db_column="id_materia"
    )
    causa = models.ForeignKey(
        Causa,
        on_delete=models.PROTECT,
        db_column="id_causa"
    )

    class Meta:
        db_table = "causa_materia"


class TipoDocumento(models.Model):
    id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=150)

    class Meta:
        db_table = "tipo_documento"


class Documento(models.Model):
    id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=150)
    fecha_registro = models.DateField()
    causa = models.ForeignKey(
        Causa,
        on_delete=models.PROTECT,
        db_column="causa_id"
    )
    tipo_documento = models.ForeignKey(
        TipoDocumento,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="tipo_documento_id"
    )

    class Meta:
        db_table = "documento"


class SesionMediacion(models.Model):
    id = models.AutoField(primary_key=True)
    fecha = models.DateField()
    hora_sesion = models.CharField(max_length=5)
    causa = models.ForeignKey(
        Causa,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="causa_id"
    )

    class Meta:
        db_table = "sesion_mediacion"


class Asistencia(models.Model):
    id = models.AutoField(primary_key=True)
    estado = models.CharField(max_length=1)
    sesion_mediacion = models.ForeignKey(
        SesionMediacion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="sesion_mediacion_id"
    )
    participante = models.ForeignKey(
        Participante,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="participante_rut"
    )

    class Meta:
        db_table = "asistencia"


class Alerta(models.Model):
    id = models.AutoField(primary_key=True)
    fecha_deteccion = models.DateField()
    tipo = models.CharField(max_length=50)
    motivo = models.CharField(max_length=250)
    prioridad = models.CharField(max_length=40)
    causa = models.ForeignKey(
        Causa,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="causa_id"
    )

    class Meta:
        db_table = "alerta"


class RegistroSeguimiento(models.Model):
    id = models.AutoField(primary_key=True)
    fecha = models.DateField()
    descripcion = models.CharField(max_length=250)
    causa = models.ForeignKey(
        Causa,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="causa_id"
    )
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="usuario_id"
    )

    class Meta:
        db_table = "registro_seguimiento"
