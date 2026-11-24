
import os
from datetime import datetime, timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.db import transaction
from django.db.models import Max, F, Value, CharField
from django.db.models.functions import Concat

from .models import (
    Usuario,
    Causa,
    Participante,
    ParticipanteCausa,
    Materia,
    CausaMateria,
    SesionMediacion,
    Asistencia,
    Documento,
    TipoDocumento
)


CLAVE_PRUEBA = os.environ.get("MEDFA_TEST_PASSWORD", "")

REGISTRO_CIVIL_SIMULADO = {
    "12351342-8": {
        "nombre": "Juan Carlos",
        "apellido": "Perez Gonzalez",
        "fecha_nacimiento": "1985-04-15"
    },
    "13526401-6": {
        "nombre": "Maria Fernanda",
        "apellido": "Lopez Ramirez",
        "fecha_nacimiento": "1990-08-22"
    }
}

MATERIAS_INICIALES = [
    "Pension de alimentos",
    "Pension de alimentos, aumento",
    "Pension de alimentos, rebaja",
    "Pension de alimentos, cesacion",
    "Cuidado personal",
    "Cuidado personal del niño, modificacion",
    "Relacion directa y regular"
]

FAMILIA_PENSION = [
    "Pension de alimentos",
    "Pension de alimentos, aumento",
    "Pension de alimentos, rebaja",
    "Pension de alimentos, cesacion"
]

FAMILIA_CUIDADO = [
    "Cuidado personal",
    "Cuidado personal del niño, modificacion"
]

ESTADOS_CAUSA_ABIERTA = [
    "Causa ingresada",
    "Causa en trámite"
]

DURACION_MEDIACION = 90

HORARIOS_MEDIACION = [
    "09:00",
    "10:30",
    "12:00",
    "13:30",
    "15:00"
]

DOCUMENTOS_DECLARACION = [
    "Declaración jurada simple del solicitante",
    "Declaración jurada simple del solicitado"
]

DOCUMENTO_FORMULARIO_INGRESO = "Formulario de ingreso espontáneo"
DOCUMENTO_CONSENTIMIENTO = "Consentimiento informado"


def normalizar_rut(rut):
    return rut.replace(".", "").replace(" ", "").upper()


def causa_permite_modificaciones(causa):
    return causa.estado in ESTADOS_CAUSA_ABIERTA


def crear_documento_causa(causa, nombre_documento):
    tipo_documento, creado = TipoDocumento.objects.get_or_create(
        nombre=nombre_documento
    )

    documento, creado = Documento.objects.get_or_create(
        causa=causa,
        tipo_documento=tipo_documento,
        defaults={
            "nombre": nombre_documento,
            "fecha_registro": timezone.localdate()
        }
    )

    return documento


def validar_materias(ids_materias):
    materias_seleccionadas = list(
        Materia.objects.filter(
            id__in=ids_materias,
            tipo__in=MATERIAS_INICIALES
        )
    )

    if (
        not ids_materias
        or len(materias_seleccionadas) != len(set(ids_materias))
    ):
        return None, "La selección de materias no es válida."

    nombres_seleccionados = [
        materia.tipo for materia in materias_seleccionadas
    ]

    seleccion_pension = [
        nombre for nombre in FAMILIA_PENSION
        if nombre in nombres_seleccionados
    ]

    seleccion_cuidado = [
        nombre for nombre in FAMILIA_CUIDADO
        if nombre in nombres_seleccionados
    ]

    if len(seleccion_pension) > 1:
        return None, (
            "No puedes combinar Pensión de alimentos con sus variantes "
            "de aumento, rebaja o cesación. Selecciona solamente una."
        )

    if len(seleccion_cuidado) > 1:
        return None, (
            "No puedes combinar Cuidado personal con Cuidado personal "
            "del niño, modificación. Selecciona solamente una."
        )

    return materias_seleccionadas, ""


def sesion_esta_realizada(sesion, causa):
    participantes_rut = list(
        ParticipanteCausa.objects.filter(
            causa=causa
        ).values_list(
            "participante_id",
            flat=True
        )
    )

    if len(participantes_rut) < 2:
        return False

    asistencias_registradas = Asistencia.objects.filter(
        sesion_mediacion=sesion,
        participante_id__in=participantes_rut
    ).values(
        "participante_id"
    ).distinct().count()

    return asistencias_registradas >= 2


def obtener_horarios_disponibles(fecha, excluir_sesion_id=None):
    if fecha.weekday() >= 5:
        return []

    sesiones = SesionMediacion.objects.filter(
        fecha=fecha
    )

    if excluir_sesion_id:
        sesiones = sesiones.exclude(
            id=excluir_sesion_id
        )

    horarios_disponibles = []

    for horario in HORARIOS_MEDIACION:
        inicio_nuevo = datetime.combine(
            fecha,
            datetime.strptime(horario, "%H:%M").time()
        )

        termino_nuevo = inicio_nuevo + timedelta(
            minutes=DURACION_MEDIACION
        )

        ocupado = False

        for sesion in sesiones:
            try:
                hora_existente = datetime.strptime(
                    sesion.hora_sesion,
                    "%H:%M"
                ).time()
            except (ValueError, TypeError):
                continue

            inicio_existente = datetime.combine(
                fecha,
                hora_existente
            )

            termino_existente = inicio_existente + timedelta(
                minutes=DURACION_MEDIACION
            )

            if (
                inicio_nuevo < termino_existente
                and inicio_existente < termino_nuevo
            ):
                ocupado = True
                break

        if not ocupado:
            horarios_disponibles.append(horario)

    return horarios_disponibles


def inicio(request):
    if request.method == "POST":
        rut = request.POST.get("rut", "").strip()
        password = request.POST.get("password", "")

        usuario = Usuario.objects.filter(
            rut=rut,
            estado="S"
        ).select_related("perfil").first()

        if usuario and CLAVE_PRUEBA and password == CLAVE_PRUEBA:
            request.session["medfa_usuario_id"] = usuario.id
            return redirect("panel")

        messages.error(
            request,
            "RUT o contraseña incorrectos, o usuario inactivo."
        )

    return render(request, "gestion/inicio.html")


def panel(request):
    usuario_id = request.session.get("medfa_usuario_id")

    usuario = Usuario.objects.filter(
        id=usuario_id,
        estado="S"
    ).select_related("perfil").first()

    if not usuario:
        request.session.flush()
        return redirect("inicio")

    return render(request, "gestion/panel.html", {"usuario": usuario})


def causas(request):
    usuario_id = request.session.get("medfa_usuario_id")

    usuario = Usuario.objects.filter(
        id=usuario_id,
        estado="S"
    ).select_related("perfil").first()

    if not usuario:
        request.session.flush()
        return redirect("inicio")

    if usuario.perfil.nombre not in [
        "Asistente Administrativo",
        "Mediador"
    ]:
        return redirect("panel")

    busqueda_realizada = request.GET.get("buscar") == "1"

    nic = request.GET.get("nic", "").strip()
    rut = request.GET.get("rut", "").strip()
    nombre = request.GET.get("nombre", "").strip()
    fecha_ingreso = request.GET.get("fecha_ingreso", "").strip()
    fecha_desde = request.GET.get("fecha_desde", "").strip()
    fecha_hasta = request.GET.get("fecha_hasta", "").strip()

    lista_causas = Causa.objects.none()
    error_busqueda = ""

    if busqueda_realizada:
        if not any([
            nic,
            rut,
            nombre,
            fecha_ingreso,
            fecha_desde,
            fecha_hasta
        ]):
            error_busqueda = "Debes ingresar al menos un criterio de busqueda."

        nic_validado = None

        if nic and not error_busqueda:
            if not nic.isdigit() or int(nic) < 1:
                error_busqueda = "El NIC debe ser un número entero mayor que cero."
            else:
                nic_validado = int(nic)

        fecha_ingreso_validada = None
        fecha_desde_validada = None
        fecha_hasta_validada = None

        try:
            if fecha_ingreso:
                fecha_ingreso_validada = datetime.strptime(
                    fecha_ingreso,
                    "%Y-%m-%d"
                ).date()

            if fecha_desde:
                fecha_desde_validada = datetime.strptime(
                    fecha_desde,
                    "%Y-%m-%d"
                ).date()

            if fecha_hasta:
                fecha_hasta_validada = datetime.strptime(
                    fecha_hasta,
                    "%Y-%m-%d"
                ).date()

        except ValueError:
            error_busqueda = "Una de las fechas ingresadas no es válida."

        if (
            not error_busqueda
            and fecha_desde_validada
            and fecha_hasta_validada
            and fecha_desde_validada > fecha_hasta_validada
        ):
            error_busqueda = "La fecha desde no puede ser posterior a la fecha hasta."

        if not error_busqueda:
            lista_causas = Causa.objects.all()

            if nic_validado is not None:
                lista_causas = lista_causas.filter(
                    nic=nic_validado
                )

            if rut:
                rut_normalizado = normalizar_rut(rut)

                lista_causas = lista_causas.filter(
                    participantecausa__participante__rut__icontains=rut_normalizado
                )

            if nombre:
                lista_causas = lista_causas.annotate(
                    nombre_participante=Concat(
                        F("participantecausa__participante__nombre"),
                        Value(" "),
                        F("participantecausa__participante__apellido"),
                        output_field=CharField()
                    )
                ).filter(
                    nombre_participante__icontains=nombre
                )

            if fecha_ingreso_validada:
                lista_causas = lista_causas.filter(
                    fecha_ingreso=fecha_ingreso_validada
                )

            if fecha_desde_validada:
                lista_causas = lista_causas.filter(
                    fecha_ingreso__gte=fecha_desde_validada
                )

            if fecha_hasta_validada:
                lista_causas = lista_causas.filter(
                    fecha_ingreso__lte=fecha_hasta_validada
                )

            lista_causas = lista_causas.order_by(
                "-id_causa"
            ).distinct().prefetch_related(
                "participantecausa_set__participante",
                "causamateria_set__materia"
            )

    return render(
        request,
        "gestion/causas.html",
        {
            "usuario": usuario,
            "causas": lista_causas,
            "busqueda_realizada": busqueda_realizada,
            "error_busqueda": error_busqueda,
            "nic": nic,
            "rut": rut,
            "nombre": nombre,
            "fecha_ingreso": fecha_ingreso,
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta
        }
    )


def detalle_causa(request, id_causa):
    usuario_id = request.session.get("medfa_usuario_id")

    usuario = Usuario.objects.filter(
        id=usuario_id,
        estado="S"
    ).select_related("perfil").first()

    if not usuario:
        request.session.flush()
        return redirect("inicio")

    if usuario.perfil.nombre not in [
        "Asistente Administrativo",
        "Mediador"
    ]:
        return redirect("panel")

    causa = get_object_or_404(
        Causa,
        id_causa=id_causa
    )

    causa_abierta = causa_permite_modificaciones(causa)

    if request.method == "POST":
        if usuario.perfil.nombre != "Asistente Administrativo":
            messages.error(
                request,
                "Tu perfil no tiene permiso para modificar esta causa."
            )
            return redirect("detalle_causa", id_causa=causa.id_causa)

        if not causa_abierta:
            messages.error(
                request,
                "La causa está cerrada. No se permiten modificaciones."
            )
            return redirect("detalle_causa", id_causa=causa.id_causa)

        accion = request.POST.get("accion", "").strip()

        if accion == "registrar_asistencia":
            sesion_id = request.POST.get(
                "sesion_id",
                ""
            ).strip()

            participante_rut = normalizar_rut(
                request.POST.get(
                    "participante_rut",
                    ""
                ).strip()
            )

            estado_asistencia = request.POST.get(
                "estado_asistencia",
                ""
            ).strip().upper()

            sesion = SesionMediacion.objects.filter(
                id=sesion_id,
                causa=causa
            ).first()

            relacion_participante = ParticipanteCausa.objects.filter(
                causa=causa,
                participante_id=participante_rut
            ).select_related("participante").first()

            if not sesion:
                messages.error(
                    request,
                    "No se encontró la sesión seleccionada."
                )
                return redirect("detalle_causa", id_causa=causa.id_causa)

            if not relacion_participante:
                messages.error(
                    request,
                    "El participante seleccionado no pertenece a esta causa."
                )
                return redirect("detalle_causa", id_causa=causa.id_causa)

            if estado_asistencia not in ["S", "N"]:
                messages.error(
                    request,
                    "Debes seleccionar si el participante asistió o no asistió."
                )
                return redirect("detalle_causa", id_causa=causa.id_causa)

            if sesion_esta_realizada(sesion, causa):
                messages.error(
                    request,
                    "La sesión ya tiene registradas las asistencias de ambas partes y no puede modificarse."
                )
                return redirect("detalle_causa", id_causa=causa.id_causa)

            try:
                with transaction.atomic():
                    asistencia = Asistencia.objects.filter(
                        sesion_mediacion=sesion,
                        participante=relacion_participante.participante
                    ).first()

                    if asistencia:
                        asistencia.estado = estado_asistencia
                        asistencia.save(update_fields=["estado"])
                    else:
                        Asistencia.objects.create(
                            sesion_mediacion=sesion,
                            participante=relacion_participante.participante,
                            estado=estado_asistencia
                        )

                    asistencias_sesion = list(
                        Asistencia.objects.filter(
                            sesion_mediacion=sesion,
                            participante__in=Participante.objects.filter(
                                participantecausa__causa=causa
                            )
                        ).select_related("participante")
                    )

                    asistencias_por_rut = {
                        asistencia.participante_id: asistencia.estado
                        for asistencia in asistencias_sesion
                    }

                    participantes_rut = list(
                        ParticipanteCausa.objects.filter(
                            causa=causa
                        ).values_list(
                            "participante_id",
                            flat=True
                        )
                    )

                    ambas_asistencias_registradas = (
                        len(participantes_rut) == 2
                        and all(
                            rut in asistencias_por_rut
                            for rut in participantes_rut
                        )
                    )

                    if ambas_asistencias_registradas:
                        causa.estado = "Causa en trámite"
                        causa.save(update_fields=["estado"])

                        ambas_asistieron = all(
                            asistencias_por_rut[rut] == "S"
                            for rut in participantes_rut
                        )

                        if ambas_asistieron:
                            crear_documento_causa(
                                causa,
                                DOCUMENTO_CONSENTIMIENTO
                            )

                messages.success(
                    request,
                    "La asistencia fue registrada correctamente."
                )

            except Exception:
                messages.error(
                    request,
                    "No fue posible registrar la asistencia. Inténtalo nuevamente."
                )

            return redirect("detalle_causa", id_causa=causa.id_causa)

        if accion == "actualizar_materia":
            materia_actual_id = request.POST.get(
                "materia_actual",
                ""
            ).strip()

            materia_nueva_id = request.POST.get(
                "materia_nueva",
                ""
            ).strip()

            intercambiar_partes = (
                request.POST.get("intercambiar_partes") == "on"
            )

            relacion_actual = CausaMateria.objects.filter(
                causa=causa,
                materia_id=materia_actual_id
            ).first()

            if not relacion_actual:
                messages.error(
                    request,
                    "No se encontró la materia que intentas actualizar."
                )
                return redirect("detalle_causa", id_causa=causa.id_causa)

            ids_materias_resultantes = list(
                CausaMateria.objects.filter(
                    causa=causa
                ).exclude(
                    materia_id=materia_actual_id
                ).values_list(
                    "materia_id",
                    flat=True
                )
            )

            ids_materias_resultantes.append(materia_nueva_id)

            materias_resultantes, error_materias = validar_materias(
                ids_materias_resultantes
            )

            if error_materias:
                messages.error(request, error_materias)
                return redirect("detalle_causa", id_causa=causa.id_causa)

            relacion_solicitante = None
            relacion_solicitado = None

            if intercambiar_partes:
                relaciones_participantes = list(
                    ParticipanteCausa.objects.filter(
                        causa=causa
                    )
                )

                relacion_solicitante = next(
                    (
                        relacion for relacion in relaciones_participantes
                        if relacion.rol == "Solicitante"
                    ),
                    None
                )

                relacion_solicitado = next(
                    (
                        relacion for relacion in relaciones_participantes
                        if relacion.rol == "Solicitado"
                    ),
                    None
                )

                if not relacion_solicitante or not relacion_solicitado:
                    messages.error(
                        request,
                        "No fue posible identificar los roles de ambas partes para realizar el intercambio."
                    )
                    return redirect("detalle_causa", id_causa=causa.id_causa)

            try:
                with transaction.atomic():
                    if str(relacion_actual.materia_id) != materia_nueva_id:
                        relacion_actual.delete()

                        CausaMateria.objects.create(
                            causa=causa,
                            materia=materias_resultantes[-1]
                        )

                    if intercambiar_partes:
                        relacion_solicitante.rol = "Solicitado"
                        relacion_solicitado.rol = "Solicitante"

                        relacion_solicitante.save(
                            update_fields=["rol"]
                        )

                        relacion_solicitado.save(
                            update_fields=["rol"]
                        )

                if intercambiar_partes:
                    messages.success(
                        request,
                        "La materia fue actualizada y los roles de solicitante y solicitado fueron intercambiados."
                    )
                else:
                    messages.success(
                        request,
                        "La materia fue actualizada correctamente."
                    )

            except Exception:
                messages.error(
                    request,
                    "No fue posible actualizar la materia. Inténtalo nuevamente."
                )

            return redirect("detalle_causa", id_causa=causa.id_causa)

        if accion == "guardar_materias":
            ids_materias = request.POST.getlist("materias")

            materias_seleccionadas, error_materias = validar_materias(
                ids_materias
            )

            if error_materias:
                messages.error(request, error_materias)
            else:
                try:
                    with transaction.atomic():
                        CausaMateria.objects.filter(
                            causa=causa
                        ).delete()

                        for materia in materias_seleccionadas:
                            CausaMateria.objects.create(
                                materia=materia,
                                causa=causa
                            )

                    messages.success(
                        request,
                        "Las materias de la causa fueron actualizadas correctamente."
                    )

                except Exception:
                    messages.error(
                        request,
                        "No fue posible actualizar las materias de la causa."
                    )

            return redirect("detalle_causa", id_causa=causa.id_causa)

        if accion in [
            "guardar_agendamiento",
            "modificar_agendamiento"
        ]:
            fecha_texto = request.POST.get(
                "fecha_agenda",
                ""
            ).strip()

            hora_seleccionada = request.POST.get(
                "hora_sesion",
                ""
            ).strip()

            try:
                fecha_agenda = datetime.strptime(
                    fecha_texto,
                    "%Y-%m-%d"
                ).date()
            except ValueError:
                messages.error(
                    request,
                    "Debes seleccionar una fecha válida."
                )
                return redirect("detalle_causa", id_causa=causa.id_causa)

            if fecha_agenda.weekday() >= 5:
                messages.error(
                    request,
                    "Las mediaciones solamente se pueden agendar de lunes a viernes."
                )
                return redirect("detalle_causa", id_causa=causa.id_causa)

            if hora_seleccionada not in HORARIOS_MEDIACION:
                messages.error(
                    request,
                    "Debes seleccionar uno de los horarios disponibles."
                )
                return redirect("detalle_causa", id_causa=causa.id_causa)

            sesiones = list(
                SesionMediacion.objects.filter(
                    causa=causa
                ).order_by("fecha", "hora_sesion")
            )

            sesiones_pendientes = [
                sesion for sesion in sesiones
                if not sesion_esta_realizada(sesion, causa)
            ]

            if len(sesiones_pendientes) > 1:
                messages.error(
                    request,
                    "La causa tiene más de una sesión pendiente. No es posible realizar otro agendamiento hasta revisar esos registros."
                )
                return redirect("detalle_causa", id_causa=causa.id_causa)

            sesion_pendiente = (
                sesiones_pendientes[0]
                if sesiones_pendientes
                else None
            )

            if accion == "modificar_agendamiento":
                if not sesion_pendiente:
                    messages.error(
                        request,
                        "No existe una sesión pendiente que pueda modificarse."
                    )
                    return redirect("detalle_causa", id_causa=causa.id_causa)

                sesion_id = request.POST.get(
                    "sesion_id",
                    ""
                ).strip()

                if sesion_id != str(sesion_pendiente.id):
                    messages.error(
                        request,
                        "La sesión seleccionada ya no puede modificarse."
                    )
                    return redirect("detalle_causa", id_causa=causa.id_causa)

                sesion_a_guardar = sesion_pendiente

            else:
                if sesion_pendiente:
                    messages.error(
                        request,
                        "Ya existe una sesión pendiente. Debes modificar su fecha u hora en lugar de crear otra."
                    )
                    return redirect("detalle_causa", id_causa=causa.id_causa)

                sesion_a_guardar = None

            try:
                with transaction.atomic():
                    horarios_disponibles = obtener_horarios_disponibles(
                        fecha_agenda,
                        excluir_sesion_id=(
                            sesion_a_guardar.id
                            if sesion_a_guardar
                            else None
                        )
                    )

                    if hora_seleccionada not in horarios_disponibles:
                        messages.error(
                            request,
                            "El horario seleccionado ya no está disponible. Selecciona otro horario."
                        )
                    else:
                        if sesion_a_guardar:
                            sesion_a_guardar.fecha = fecha_agenda
                            sesion_a_guardar.hora_sesion = hora_seleccionada
                            sesion_a_guardar.save()

                            messages.success(
                                request,
                                "La fecha y hora de la sesión fueron modificadas correctamente."
                            )
                        else:
                            SesionMediacion.objects.create(
                                fecha=fecha_agenda,
                                hora_sesion=hora_seleccionada,
                                causa=causa
                            )

                            crear_documento_causa(
                                causa,
                                DOCUMENTO_FORMULARIO_INGRESO
                            )

                            messages.success(
                                request,
                                "La nueva sesión de mediación fue agendada y el formulario de ingreso espontáneo quedó disponible."
                            )

            except Exception:
                messages.error(
                    request,
                    "No fue posible guardar el agendamiento. Inténtalo nuevamente."
                )

            return redirect("detalle_causa", id_causa=causa.id_causa)

        messages.error(
            request,
            "La operación solicitada no es válida."
        )
        return redirect("detalle_causa", id_causa=causa.id_causa)

    materias_disponibles = []

    for nombre in MATERIAS_INICIALES:
        materia, creado = Materia.objects.get_or_create(
            tipo=nombre
        )
        materias_disponibles.append(materia)

    participantes_causa = ParticipanteCausa.objects.filter(
        causa=causa
    ).select_related("participante")

    materias_causa = CausaMateria.objects.filter(
        causa=causa
    ).select_related("materia")

    ids_materias_causa = list(
        materias_causa.values_list(
            "materia_id",
            flat=True
        )
    )

    sesiones_causa = list(
        SesionMediacion.objects.filter(
            causa=causa
        ).order_by("fecha", "hora_sesion")
    )

    sesiones_pendientes = []

    for sesion in sesiones_causa:
        sesion.realizada = sesion_esta_realizada(
            sesion,
            causa
        )

        sesion.pendiente = not sesion.realizada

        sesion.asistencias_registradas = list(
            Asistencia.objects.filter(
                sesion_mediacion=sesion
            ).select_related("participante")
        )

        if sesion.pendiente:
            sesiones_pendientes.append(sesion)

    sesion_pendiente = (
        sesiones_pendientes[0]
        if len(sesiones_pendientes) == 1
        else None
    )

    documentos_causa = Documento.objects.filter(
        causa=causa
    ).select_related(
        "tipo_documento"
    ).order_by(
        "fecha_registro",
        "id"
    )

    fecha_agenda_texto = request.GET.get(
        "fecha_agenda",
        ""
    ).strip()

    fecha_agenda = None
    horarios_disponibles = []
    error_agenda = ""

    if fecha_agenda_texto:
        try:
            fecha_agenda = datetime.strptime(
                fecha_agenda_texto,
                "%Y-%m-%d"
            ).date()

            if fecha_agenda.weekday() >= 5:
                error_agenda = "Selecciona un día de lunes a viernes."
            else:
                horarios_disponibles = obtener_horarios_disponibles(
                    fecha_agenda,
                    excluir_sesion_id=(
                        sesion_pendiente.id
                        if sesion_pendiente
                        else None
                    )
                )

                if not horarios_disponibles:
                    error_agenda = "No hay horarios disponibles para esta fecha."

        except ValueError:
            error_agenda = "La fecha seleccionada no es válida."

    return render(
        request,
        "gestion/detalle_causa.html",
        {
            "usuario": usuario,
            "causa": causa,
            "causa_abierta": causa_abierta,
            "participantes_causa": participantes_causa,
            "materias_causa": materias_causa,
            "materias_disponibles": materias_disponibles,
            "ids_materias_causa": ids_materias_causa,
            "sesiones_causa": sesiones_causa,
            "sesion_pendiente": sesion_pendiente,
            "sesiones_pendientes": sesiones_pendientes,
            "documentos_causa": documentos_causa,
            "fecha_agenda": fecha_agenda_texto,
            "horarios_disponibles": horarios_disponibles,
            "error_agenda": error_agenda,
            "duracion_mediacion": DURACION_MEDIACION
        }
    )


def consultar_participante(request):
    usuario_id = request.session.get("medfa_usuario_id")

    usuario = Usuario.objects.filter(
        id=usuario_id,
        estado="S"
    ).select_related("perfil").first()

    if not usuario or usuario.perfil.nombre != "Asistente Administrativo":
        return JsonResponse({"encontrado": False}, status=403)

    rut = normalizar_rut(request.GET.get("rut", "").strip())

    if not rut:
        return JsonResponse({
            "encontrado": False,
            "mensaje": "Ingresa un RUT para realizar la consulta."
        })

    datos = REGISTRO_CIVIL_SIMULADO.get(rut)

    if not datos:
        return JsonResponse({
            "encontrado": False,
            "mensaje": "No se encontraron antecedentes para el RUT ingresado."
        })

    return JsonResponse({
        "encontrado": True,
        "nombre_completo": f'{datos["nombre"]} {datos["apellido"]}',
        "fecha_nacimiento": datos["fecha_nacimiento"]
    })


def ingresar_causa(request):
    usuario_id = request.session.get("medfa_usuario_id")

    usuario = Usuario.objects.filter(
        id=usuario_id,
        estado="S"
    ).select_related("perfil").first()

    if not usuario:
        request.session.flush()
        return redirect("inicio")

    if usuario.perfil.nombre != "Asistente Administrativo":
        return redirect("panel")

    materias_disponibles = []

    for nombre in MATERIAS_INICIALES:
        materia, creado = Materia.objects.get_or_create(
            tipo=nombre
        )
        materias_disponibles.append(materia)

    contexto = {
        "usuario": usuario,
        "materias": materias_disponibles
    }

    if request.method == "POST":
        participantes = [
            {
                "rut": normalizar_rut(
                    request.POST.get("rut_solicitante", "").strip()
                ),
                "direccion": request.POST.get(
                    "direccion_solicitante", ""
                ).strip(),
                "telefono": request.POST.get(
                    "telefono_solicitante", ""
                ).strip(),
                "correo": request.POST.get(
                    "correo_solicitante", ""
                ).strip(),
                "rol": "Solicitante"
            },
            {
                "rut": normalizar_rut(
                    request.POST.get("rut_solicitado", "").strip()
                ),
                "direccion": request.POST.get(
                    "direccion_solicitado", ""
                ).strip(),
                "telefono": request.POST.get(
                    "telefono_solicitado", ""
                ).strip(),
                "correo": request.POST.get(
                    "correo_solicitado", ""
                ).strip(),
                "rol": "Solicitado"
            }
        ]

        for participante in participantes:
            if not all([
                participante["rut"],
                participante["direccion"],
                participante["telefono"],
                participante["correo"]
            ]):
                messages.error(
                    request,
                    "Debes completar el RUT y los datos de contacto de ambas personas."
                )
                return render(
                    request,
                    "gestion/ingresar_causa.html",
                    contexto
                )

            datos_registro = REGISTRO_CIVIL_SIMULADO.get(
                participante["rut"]
            )

            if not datos_registro:
                messages.error(
                    request,
                    f'No se encontraron antecedentes para el RUT {participante["rut"]}. '
                    "No es posible crear la causa."
                )
                return render(
                    request,
                    "gestion/ingresar_causa.html",
                    contexto
                )

            participante["nombre"] = datos_registro["nombre"]
            participante["apellido"] = datos_registro["apellido"]
            participante["fecha_nacimiento"] = datos_registro["fecha_nacimiento"]

        if participantes[0]["rut"] == participantes[1]["rut"]:
            messages.error(
                request,
                "El RUT del solicitante y del solicitado debe ser diferente."
            )
            return render(
                request,
                "gestion/ingresar_causa.html",
                contexto
            )

        ids_materias = request.POST.getlist("materias")

        materias_seleccionadas, error_materias = validar_materias(
            ids_materias
        )

        if error_materias:
            messages.error(request, error_materias)
            return render(
                request,
                "gestion/ingresar_causa.html",
                contexto
            )

        try:
            with transaction.atomic():
                ultimo_nic = Causa.objects.aggregate(
                    ultimo=Max("nic")
                )["ultimo"]

                nuevo_nic = (ultimo_nic or 0) + 1

                causa = Causa.objects.create(
                    nic=nuevo_nic,
                    fecha_ingreso=timezone.localdate(),
                    estado="Causa ingresada"
                )

                for datos in participantes:
                    participante = Participante.objects.filter(
                        rut=datos["rut"]
                    ).first()

                    if participante:
                        participante.nombre = datos["nombre"]
                        participante.apellido = datos["apellido"]
                        participante.fecha_nacimiento = datos["fecha_nacimiento"]
                        participante.direccion = datos["direccion"]
                        participante.telefono = datos["telefono"]
                        participante.correo = datos["correo"]
                        participante.save()
                    else:
                        participante = Participante.objects.create(
                            rut=datos["rut"],
                            nombre=datos["nombre"],
                            apellido=datos["apellido"],
                            fecha_nacimiento=datos["fecha_nacimiento"],
                            direccion=datos["direccion"],
                            telefono=datos["telefono"],
                            correo=datos["correo"]
                        )

                    ParticipanteCausa.objects.create(
                        participante=participante,
                        causa=causa,
                        rol=datos["rol"]
                    )

                for materia in materias_seleccionadas:
                    CausaMateria.objects.create(
                        materia=materia,
                        causa=causa
                    )

                for nombre_documento in DOCUMENTOS_DECLARACION:
                    crear_documento_causa(
                        causa,
                        nombre_documento
                    )

            messages.success(
                request,
                f"Causa creada correctamente. NIC: {nuevo_nic}."
            )
            return redirect("detalle_causa", id_causa=causa.id_causa)

        except Exception:
            messages.error(
                request,
                "No fue posible crear la causa. Revisa los datos e intentalo nuevamente."
            )

    return render(
        request,
        "gestion/ingresar_causa.html",
        contexto
    )
