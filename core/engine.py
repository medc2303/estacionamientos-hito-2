"""
Motor Central de Reglas de Negocio SIGE (Hito 2).
Implementa las 6 funcionalidades exigidas (3 obligatorias + 3 propias), las reglas RN01-RN05,
la Regla de Oferta del Anexo D (umbral θ y margen 30/60 min), el cobro por minuto (Ley 20.967),
y el Sistema de Rotación Equitativa con Estacionamientos de Recambio.
"""

from __future__ import annotations
from datetime import datetime
import os
from typing import Dict, List, Optional, Tuple, Any

from core.models import (
    Estacionamiento,
    Reserva,
    EventoHistorial,
    TARIFA_MINUTO_BASE,
    COMPENSACION_CONTINGENCIA,
)
from core.persistence import GestorPersistenciaCSV
from core.seed_data import (
    BLOQUES_30_MIN,
    analizar_dataset_hito1,
    calcular_ventana_ofrecida,
)


# Tabla 5.1 de la Solemne 1 (Regla de oferta según el umbral θ sobre el dataset de 4 semanas)
TABLA_5_1_UMBRALES: Dict[str, Dict[str, Any]] = {
    "0.60": {"bloques_ofrecidos": 12889, "ingreso_posible": 8385000, "riesgo_2h": "14,0%"},
    "0.70": {"bloques_ofrecidos": 11544, "ingreso_posible": 7686000, "riesgo_2h": "11,8%"},
    "0.80": {"bloques_ofrecidos": 9388,  "ingreso_posible": 6285000, "riesgo_2h": "11,1%"},
    "0.90": {"bloques_ofrecidos": 4008,  "ingreso_posible": 2733000, "riesgo_2h": "9,4%"},
    "0.95": {"bloques_ofrecidos": 1688,  "ingreso_posible": 1189500, "riesgo_2h": "6,8%"},
}


def hora_a_minutos(hora_str: str) -> int:
    """Convierte 'HH:MM' a minutos desde las 00:00."""
    partes = hora_str.strip().split(":")
    return int(partes[0]) * 60 + int(partes[1])


def minutos_a_hora(minutos: int) -> str:
    """Convierte minutos desde las 00:00 a formato 'HH:MM'."""
    h = max(0, min(23, minutos // 60))
    m = max(0, min(59, minutos % 60))
    return f"{h:02d}:{m:02d}"


def bloques_en_rango(hora_inicio: str, hora_fin: str) -> List[str]:
    """Devuelve la lista de bloques de 30 min comprendidos en [hora_inicio, hora_fin)."""
    ini_m = hora_a_minutos(hora_inicio)
    fin_m = hora_a_minutos(hora_fin)
    resultado: List[str] = []
    for b in BLOQUES_30_MIN:
        bm = hora_a_minutos(b)
        if ini_m <= bm < fin_m:
            resultado.append(b)
    return resultado


def rangos_se_superponen(ini1: str, fin1: str, ini2: str, fin2: str) -> bool:
    """Retorna True si [ini1, fin1) y [ini2, fin2) tienen intersección horaria."""
    return max(hora_a_minutos(ini1), hora_a_minutos(ini2)) < min(
        hora_a_minutos(fin1), hora_a_minutos(fin2)
    )


class MotorSIGE:
    """Coordina todas las operaciones, validaciones y persistencia del sistema SIGE."""

    def __init__(self, data_dir: str) -> None:
        self.data_dir = data_dir
        self.persistencia = GestorPersistenciaCSV(data_dir)
        dataset_path = os.path.join(data_dir, "dataset_historico_hito1.csv")
        self.stats_hist, self.prob_por_bloque = analizar_dataset_hito1(dataset_path)
        self.estacionamientos, self.reservas, self.eventos, self.config = (
            self.persistencia.cargar_todo()
        )

    @property
    def theta(self) -> float:
        return float(self.config.get("theta", "0.80"))

    def recargar(self) -> None:
        self.estacionamientos, self.reservas, self.eventos, self.config = (
            self.persistencia.cargar_todo()
        )

    def guardar(self) -> None:
        self._sincronizar_estados_visuales()
        self.persistencia.guardar_todo(
            self.estacionamientos, self.reservas, self.eventos, self.config
        )

    def obtener_estacionamiento(self, spot_id: str) -> Optional[Estacionamiento]:
        for e in self.estacionamientos:
            if e.id_estacionamiento == spot_id:
                return e
        return None

    def obtener_reserva(self, res_id: str) -> Optional[Reserva]:
        for r in self.reservas:
            if r.id_reserva == res_id:
                return r
        return None

    def _registrar_evento(
        self,
        tipo_evento: str,
        rol_actor: str,
        id_estacionamiento: str,
        id_reserva: str,
        propietario: str,
        cliente: str,
        fecha_operacion: str,
        hora_inicio: str,
        hora_fin: str,
        estado_resultante: str,
        valor_operacion: int,
        detalle: str,
    ) -> EventoHistorial:
        nuevo_id = f"EVT-{len(self.eventos) + 1:04d}"
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ev = EventoHistorial(
            id_evento=nuevo_id,
            fecha_hora_registro=ahora,
            tipo_evento=tipo_evento,
            rol_actor=rol_actor,
            id_estacionamiento=id_estacionamiento,
            id_reserva=id_reserva,
            propietario=propietario,
            cliente=cliente,
            fecha_operacion=fecha_operacion,
            hora_inicio=hora_inicio,
            hora_fin=hora_fin,
            estado_resultante=estado_resultante,
            valor_operacion=valor_operacion,
            detalle=detalle,
        )
        self.eventos.append(ev)
        return ev

    def _sincronizar_estados_visuales(self) -> None:
        """
        RN04 (Consistencia de estados): Actualiza el estado_actual de cada estacionamiento
        según sus bloqueos y las reservas activas vigentes.
        """
        for e in self.estacionamientos:
            if e.estado_actual == "BLOQUEADO" or e.bloques_bloqueados == "TODO":
                e.estado_actual = "BLOQUEADO"
                continue
            if not e.semana_confirmada or e.hora_inicio_ofrecida == "Sin oferta":
                e.estado_actual = "OCUPADO_DUENO"
                continue

            res_activas = [
                r
                for r in self.reservas
                if r.id_estacionamiento == e.id_estacionamiento
                and r.estado in ("CONFIRMADA", "EN_CURSO", "SOBREESTADIA")
            ]
            if any(r.estado == "SOBREESTADIA" for r in res_activas):
                e.estado_actual = "SOBREESTADIA"
            elif res_activas:
                e.estado_actual = "ARRENDADO"
            else:
                e.estado_actual = "LIBRE"

    # =========================================================================
    # VALIDACIÓN CENTRAL DE DISPONIBILIDAD, MARGEN (30/60m) Y NO SUPERPOSICIÓN
    # =========================================================================
    def verificar_compatibilidad_estacionamiento(
        self,
        est: Estacionamiento,
        fecha: str,
        hora_inicio: str,
        hora_fin: str,
        ignorar_reserva_id: str = "",
        exigir_umbral_hist: bool = True,
    ) -> Tuple[bool, str]:
        """
        Verifica si `est` puede recibir una reserva en [hora_inicio, hora_fin) cumpliendo:
        - RN01 y RN03: Semana confirmada y no bloqueado por el propietario en esos bloques.
        - Regla propia 1 (Solemne 1): Probabilidad histórica >= θ en los bloques solicitados
          MÁS los bloques de margen de seguridad (30 min si es puntual, 60 min si es irregular).
        - Regla propia 2 (Solemne 1): Duración máxima según índice de regularidad del dueño.
        - RN02: No superposición con ninguna otra reserva vigente (incluyendo margen de seguridad).
        """
        ini_m = hora_a_minutos(hora_inicio)
        fin_m = hora_a_minutos(hora_fin)
        duracion = fin_m - ini_m

        if duracion <= 0:
            return False, "La hora de salida debe ser posterior a la hora de llegada."

        if not est.semana_confirmada:
            return False, f"{est.id_estacionamiento} no tiene disponibilidad semanal confirmada."

        if est.estado_actual == "BLOQUEADO" or est.bloques_bloqueados == "TODO":
            return False, f"{est.id_estacionamiento} está bloqueado por su propietario."

        if duracion > est.max_duracion_reserva_min:
            return (
                False,
                f"El propietario de {est.id_estacionamiento} tiene perfil {est.perfil_regularidad} "
                f"(máx. {est.max_duracion_reserva_min} min por reserva).",
            )

        bloques_solicitados = bloques_en_rango(hora_inicio, hora_fin)
        if not bloques_solicitados:
            return False, "Rango horario fuera de los bloques operativos (06:00 a 23:30)."

        # Verificar bloques bloqueados manualmente por el propietario
        bloqueados_dueno = set(est.lista_bloques_bloqueados)
        conflicto_bloqueo = [b for b in bloques_solicitados if b in bloqueados_dueno]
        if conflicto_bloqueo:
            return (
                False,
                f"{est.id_estacionamiento} tiene bloqueados los bloques: {', '.join(conflicto_bloqueo)}.",
            )

        # Verificar margen de seguridad (30 min = 1 bloque puntual; 60 min = 2 bloques irregular)
        fin_con_margen_m = fin_m + est.margen_seguridad_min
        hora_fin_con_margen = minutos_a_hora(fin_con_margen_m)
        bloques_totales_con_margen = bloques_en_rango(hora_inicio, hora_fin_con_margen)

        if exigir_umbral_hist:
            probs = self.prob_por_bloque.get(est.id_estacionamiento, {})
            umbral = self.theta
            for b in bloques_totales_con_margen:
                p = probs.get(b, 0.0)
                if p < umbral:
                    return (
                        False,
                        f"Bloque {b} (incluyendo margen de {est.margen_seguridad_min} min) tiene "
                        f"disponibilidad histórica {p:.0%} < umbral θ={umbral:.0%}.",
                    )

        # RN02: Verificar no superposición con otras reservas activas en la misma fecha
        for r in self.reservas:
            if r.id_reserva == ignorar_reserva_id:
                continue
            if r.id_estacionamiento != est.id_estacionamiento or r.fecha != fecha:
                continue
            if r.estado not in ("CONFIRMADA", "EN_CURSO", "SOBREESTADIA"):
                continue

            # Se protege también el margen entre reservas o regreso
            if rangos_se_superponen(hora_inicio, hora_fin, r.hora_inicio, r.hora_fin):
                return (
                    False,
                    f"Superposición horaria con reserva vigente {r.id_reserva} ({r.hora_inicio} a {r.hora_fin}).",
                )

        return True, "Compatible"

    # =========================================================================
    # MOTOR DE SELECCIÓN EQUITATIVA Y COLA DE RECAMBIO
    # =========================================================================
    def buscar_candidatos_ordenados(
        self,
        fecha: str,
        hora_inicio: str,
        hora_fin: str,
        ignorar_reserva_id: str = "",
        excluir_estacionamientos: Optional[List[str]] = None,
        preferir_pool_recambio: bool = False,
    ) -> List[Tuple[Estacionamiento, str]]:
        """
        Retorna todos los estacionamientos compatibles ordenados según la política de negocio:
        - En una reserva normal (`preferir_pool_recambio=False`):
          1° Prioriza propietarios que AÚN NO HAN SIDO ELEGIDOS (`en_recambio=False`),
             ordenados por mayor disponibilidad histórica y confiabilidad (premiando a quienes
             ofrecen más horas libres al sistema).
          2° Los propietarios cuyos lotes ya fueron elegidos (`en_recambio=True`) bajan su prioridad
             y quedan en la Cola de Estacionamientos de Recambio para que todos los estacionamientos
             se ocupen de la misma manera.
        - En una contingencia/reasignación de emergencia (`preferir_pool_recambio=True`):
          Puede usar directamente los lotes de recambio o los libres con menor uso.
        """
        excluir = set(excluir_estacionamientos or [])
        compatibles: List[Estacionamiento] = []

        for est in self.estacionamientos:
            if est.id_estacionamiento in excluir:
                continue
            ok, _ = self.verificar_compatibilidad_estacionamiento(
                est, fecha, hora_inicio, hora_fin, ignorar_reserva_id=ignorar_reserva_id
            )
            if ok:
                compatibles.append(est)

        if not compatibles:
            return []

        if preferir_pool_recambio:
            # Para contingencias: usar primero estacionamientos de recambio libres (o menor uso)
            compatibles.sort(
                key=lambda e: (
                    0 if e.en_recambio else 1,
                    e.veces_asignado,
                    -e.horas_libres_dia_hist,
                    -e.indice_confiabilidad,
                )
            )
        else:
            # Para nuevas reservas:
            # Primero los NO usados en este ciclo (en_recambio=False), premiando mayor disponibilidad
            compatibles.sort(
                key=lambda e: (
                    1 if e.en_recambio else 0,
                    e.veces_asignado,
                    -e.puntaje_prioridad_asignacion(),
                    -e.horas_libres_dia_hist,
                )
            )

        resultado: List[Tuple[Estacionamiento, str]] = []
        todos_en_recambio = all(e.en_recambio for e in compatibles)
        for e in compatibles:
            if not e.en_recambio:
                motivo = (
                    f"Prioridad Alta (Aporte {e.horas_libres_dia_hist} h/día, "
                    f"Confiabilidad {e.indice_confiabilidad:.0f}%, 0 usos en ciclo actual) -> "
                    f"Al elegirse pasa a Estacionamiento de Recambio"
                )
            elif preferir_pool_recambio:
                motivo = (
                    f"Tomado del Pool de Recambio ({e.horas_libres_dia_hist} h/día, "
                    f"usos previos: {e.veces_asignado}) para resolver contingencia"
                )
            elif todos_en_recambio:
                motivo = (
                    f"Ciclo de rotación completado entre lotes compatibles -> "
                    f"Seleccionado de Cola de Recambio con menor uso ({e.veces_asignado})"
                )
            else:
                motivo = (
                    f"En Cola de Recambio (Prioridad reducida, usos previos: {e.veces_asignado}, "
                    f"disponibilidad {e.horas_libres_dia_hist} h/día)"
                )
            resultado.append((e, motivo))

        return resultado

    def _marcar_lote_en_recambio(self, est: Estacionamiento) -> None:
        """
        Cuando un estacionamiento es seleccionado, incrementa su contador de uso,
        baja su prioridad y lo deja como Estacionamiento de Recambio.
        Si todos los estacionamientos con oferta confirmada ya están en recambio,
        reinicia la bandera en_recambio de los demás para comenzar una nueva vuelta equitativa.
        """
        est.veces_asignado += 1
        est.en_recambio = True

        confirmados = [
            e
            for e in self.estacionamientos
            if e.semana_confirmada and e.hora_inicio_ofrecida != "Sin oferta"
        ]
        if confirmados and all(e.en_recambio for e in confirmados):
            for e in confirmados:
                if e.id_estacionamiento != est.id_estacionamiento:
                    e.en_recambio = False

    # =========================================================================
    # 1. PROPIETARIO · FUNCIONALIDAD OBLIGATORIA: LIBERAR Y BLOQUEAR (+ ¡LLEGUÉ ANTES!)
    # =========================================================================
    def propietario_liberar_estacionamiento(
        self, spot_id: str, limpiar_bloqueos: bool = True
    ) -> Tuple[bool, str]:
        """El propietario declara su estacionamiento disponible y desbloquea sus bloques."""
        est = self.obtener_estacionamiento(spot_id)
        if not est:
            return False, "Estacionamiento no encontrado."

        est.semana_confirmada = True
        if limpiar_bloqueos:
            est.bloques_bloqueados = ""
        if est.hora_inicio_ofrecida == "Sin oferta":
            est.hora_inicio_ofrecida = "09:00"
            est.hora_fin_ofrecida = "17:30"
        est.estado_actual = "LIBRE"

        self._registrar_evento(
            tipo_evento="LIBERACION_PROPIETARIO",
            rol_actor="Propietario",
            id_estacionamiento=est.id_estacionamiento,
            id_reserva="-",
            propietario=est.propietario,
            cliente="-",
            fecha_operacion=self.config.get("fecha_operacion_actual", "2026-08-28"),
            hora_inicio=est.hora_inicio_ofrecida,
            hora_fin=est.hora_fin_ofrecida,
            estado_resultante="LIBRE",
            valor_operacion=0,
            detalle=f"Propietario {est.propietario} liberó su estacionamiento ({est.hora_inicio_ofrecida}-{est.hora_fin_ofrecida}).",
        )
        self.guardar()
        return (
            True,
            f"Estacionamiento {est.id_estacionamiento} liberado y habilitado entre {est.hora_inicio_ofrecida} y {est.hora_fin_ofrecida}.",
        )

    def propietario_bloquear_o_llegue_antes(
        self,
        spot_id: str,
        fecha: str,
        hora_inicio_bloqueo: str,
        hora_fin_bloqueo: str,
        es_emergencia_llegue_antes: bool = False,
    ) -> Tuple[bool, str]:
        """
        El propietario bloquea un período horario o presiona el botón rojo '¡Llegué antes!'.
        RN01 (Prioridad del propietario) + Tabla 3.1 (Contingencias):
        - Verifica si existe una reserva vigente (CONFIRMADA o EN_CURSO) en ese período.
        - Si existe, intenta reasignarla automáticamente a otro estacionamiento compatible
          (usando el Pool de Recambio / disponibles) sin afectar al cliente.
        - Si no hay ningún estacionamiento compatible disponible, cancela la reserva,
          devuelve el dinero y compensa al cliente ($1.500), reduciendo el índice de
          confiabilidad del propietario si canceló una disponibilidad reservada.
        """
        est = self.obtener_estacionamiento(spot_id)
        if not est:
            return False, "Estacionamiento no encontrado."

        if hora_a_minutos(hora_fin_bloqueo) <= hora_a_minutos(hora_inicio_bloqueo):
            return False, "La hora de término del bloqueo debe ser posterior a la hora de inicio."

        bloques_a_bloquear = bloques_en_rango(hora_inicio_bloqueo, hora_fin_bloqueo)
        actuales = set(est.lista_bloques_bloqueados)
        actuales.update(bloques_a_bloquear)
        if es_emergencia_llegue_antes:
            est.bloques_bloqueados = "TODO"
            est.estado_actual = "BLOQUEADO"
        else:
            est.bloques_bloqueados = ",".join(sorted(actuales))

        # Buscar reservas activas que entren en conflicto con el bloqueo del dueño
        reservas_afectadas = [
            r
            for r in self.reservas
            if r.id_estacionamiento == spot_id
            and r.fecha == fecha
            and r.estado in ("CONFIRMADA", "EN_CURSO", "SOBREESTADIA")
            and rangos_se_superponen(hora_inicio_bloqueo, hora_fin_bloqueo, r.hora_inicio, r.hora_fin)
        ]

        mensajes_contingencia: List[str] = []
        for res in reservas_afectadas:
            candidatos = self.buscar_candidatos_ordenados(
                fecha=res.fecha,
                hora_inicio=res.hora_inicio,
                hora_fin=res.hora_fin,
                ignorar_reserva_id=res.id_reserva,
                excluir_estacionamientos=[spot_id],
                preferir_pool_recambio=True,
            )
            if candidatos:
                nuevo_est, motivo_rec = candidatos[0]
                est_anterior = res.id_estacionamiento
                res.estacionamiento_original = est_anterior
                res.id_estacionamiento = nuevo_est.id_estacionamiento
                res.propietario = nuevo_est.propietario
                res.criterio_asignacion = (
                    f"Reasignación automática desde {est_anterior} por retorno/bloqueo del dueño ({motivo_rec})"
                )
                self._marcar_lote_en_recambio(nuevo_est)
                if not es_emergencia_llegue_antes:
                    est.indice_confiabilidad = round(max(40.0, est.indice_confiabilidad - 3.0), 1)

                self._registrar_evento(
                    tipo_evento="REASIGNACION_AUTOMATICA",
                    rol_actor="Propietario/Sistema",
                    id_estacionamiento=nuevo_est.id_estacionamiento,
                    id_reserva=res.id_reserva,
                    propietario=nuevo_est.propietario,
                    cliente=res.cliente,
                    fecha_operacion=fecha,
                    hora_inicio=res.hora_inicio,
                    hora_fin=res.hora_fin,
                    estado_resultante=res.estado,
                    valor_operacion=res.monto_total,
                    detalle=(
                        f"Prioridad del propietario en {est_anterior}: Reserva {res.id_reserva} "
                        f"reasignada automáticamente al estacionamiento {nuevo_est.id_estacionamiento} ({nuevo_est.propietario})."
                    ),
                )
                mensajes_contingencia.append(
                    f"⚡ Contingencia resuelta: La reserva vigente {res.id_reserva} ({res.cliente}) fue "
                    f"reasignada automáticamente a {nuevo_est.id_estacionamiento} ({nuevo_est.propietario})."
                )
            else:
                # No hay estacionamiento compatible: devolución + compensación y baja confiabilidad
                res.estado = "CANCELADA"
                res.monto_base = 0
                res.monto_total = 0
                res.compensacion_cliente = COMPENSACION_CONTINGENCIA
                res.pago_propietario_60 = 0
                res.aporte_admin_30 = 0
                res.bono_guardia_5 = 0
                res.ingreso_operacion_5 = 0
                est.indice_confiabilidad = round(max(40.0, est.indice_confiabilidad - 5.0), 1)

                self._registrar_evento(
                    tipo_evento="CANCELACION_POR_PRIORIDAD_DUENO",
                    rol_actor="Propietario/Sistema",
                    id_estacionamiento=spot_id,
                    id_reserva=res.id_reserva,
                    propietario=est.propietario,
                    cliente=res.cliente,
                    fecha_operacion=fecha,
                    hora_inicio=res.hora_inicio,
                    hora_fin=res.hora_fin,
                    estado_resultante="CANCELADA",
                    valor_operacion=-COMPENSACION_CONTINGENCIA,
                    detalle=(
                        f"Dueño recuperó {spot_id} sin cupos de recambio disponibles. "
                        f"Se devolvió el 100% y se compensó al cliente con ${COMPENSACION_CONTINGENCIA}. "
                        f"Confiabilidad del dueño ajustada a {est.indice_confiabilidad}%."
                    ),
                )
                mensajes_contingencia.append(
                    f"⚠️ Sin cupo de recambio para {res.id_reserva}: se priorizó al propietario, "
                    f"se devolvió el dinero y se compensó a {res.cliente} con ${COMPENSACION_CONTINGENCIA:,}."
                )

        tipo_evt = "LLEGUE_ANTES_EMERGENCIA" if es_emergencia_llegue_antes else "BLOQUEO_PROPIETARIO"
        self._registrar_evento(
            tipo_evento=tipo_evt,
            rol_actor="Propietario",
            id_estacionamiento=spot_id,
            id_reserva="-",
            propietario=est.propietario,
            cliente="-",
            fecha_operacion=fecha,
            hora_inicio=hora_inicio_bloqueo,
            hora_fin=hora_fin_bloqueo,
            estado_resultante=est.estado_actual,
            valor_operacion=0,
            detalle=(
                f"Propietario {est.propietario} activó {'¡Llegué antes!' if es_emergencia_llegue_antes else 'bloqueo horario'} "
                f"({hora_inicio_bloqueo}-{hora_fin_bloqueo}). Reservas afectadas: {len(reservas_afectadas)}."
            ),
        )
        self.guardar()

        resumen = (
            f"🛑 ¡Prioridad del propietario activada en {spot_id}! Espacio recuperado de inmediato."
            if es_emergencia_llegue_antes
            else f"🔒 Bloqueo aplicado en {spot_id} para el tramo {hora_inicio_bloqueo} - {hora_fin_bloqueo}."
        )
        if mensajes_contingencia:
            resumen += "\n\n" + "\n".join(mensajes_contingencia)
        return True, resumen

    # =========================================================================
    # 2. PROPIETARIO · FUNCIONALIDAD PROPIA (F1): CONFIRMAR SEMANA Y PERFIL DE REGULARIDAD
    # =========================================================================
    def propietario_confirmar_semana_mixta(
        self, spot_id: str, nuevo_perfil: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        F1 (Confirmar la semana con un clic - Disponibilidad Mixta):
        Recalcula la ventana horaria sugerida para el propietario usando su historial de 20 días,
        el umbral θ vigente y su margen de seguridad (30 min puntual / 60 min irregular),
        confirmando su oferta semanal y limpiando bloqueos temporales.
        """
        est = self.obtener_estacionamiento(spot_id)
        if not est:
            return False, "Estacionamiento no encontrado."

        if nuevo_perfil in ("PUNTUAL", "IRREGULAR"):
            est.perfil_regularidad = nuevo_perfil
            est.margen_seguridad_min = 30 if nuevo_perfil == "PUNTUAL" else 60

        inicio_of, fin_of, bloques_of = calcular_ventana_ofrecida(
            self.prob_por_bloque[spot_id],
            margen_bloques=est.bloques_margen,
            theta=self.theta,
        )
        est.hora_inicio_ofrecida = inicio_of
        est.hora_fin_ofrecida = fin_of
        est.bloques_bloqueados = ""
        est.semana_confirmada = len(bloques_of) > 0
        est.estado_actual = "LIBRE" if est.semana_confirmada else "OCUPADO_DUENO"

        self._registrar_evento(
            tipo_evento="CONFIRMACION_SEMANA",
            rol_actor="Propietario",
            id_estacionamiento=spot_id,
            id_reserva="-",
            propietario=est.propietario,
            cliente="-",
            fecha_operacion=self.config.get("fecha_operacion_actual", "2026-08-28"),
            hora_inicio=inicio_of,
            hora_fin=fin_of,
            estado_resultante=est.estado_actual,
            valor_operacion=0,
            detalle=(
                f"Disponibilidad mixta confirmada con 1 clic (θ={self.theta:.2f}, perfil {est.perfil_regularidad}, "
                f"margen {est.margen_seguridad_min} min -> {len(bloques_of)} bloques ofrecidos/día)."
            ),
        )
        self.guardar()

        if not bloques_of:
            return (
                False,
                f"Con el umbral θ={self.theta:.2f} y margen de {est.margen_seguridad_min} min, "
                f"{spot_id} no alcanza el 80% histórico en ningún bloque continuo.",
            )

        ingreso_potencial_sem = int(len(bloques_of) * 5 * 750 * 0.60)
        return (
            True,
            f"✅ Semana confirmada para {spot_id} ({est.propietario}): disponible de {inicio_of} a {fin_of} "
            f"(margen de seguridad: {est.margen_seguridad_min} min · ingreso potencial 60% dueño: ${ingreso_potencial_sem:,}/semana).",
        )

    # =========================================================================
    # 3. CLIENTE · FUNCIONALIDAD OBLIGATORIA (F4): RESERVAR Y CANCELAR/LIBERAR
    # =========================================================================
    def cliente_crear_reserva(
        self,
        cliente: str,
        patente: str,
        fecha: str,
        hora_inicio: str,
        hora_fin: str,
    ) -> Tuple[bool, str, Optional[Reserva]]:
        """
        F4 (Buscar y reservar un tiempo - Asignación ciega + Rotación de Recambio):
        El cliente NO elige el estacionamiento. El sistema verifica disponibilidad (θ, margen 30/60 min,
        no bloqueo, no superposición), elige el estacionamiento óptimo según la cola de prioridad/recambio,
        baja la prioridad del lote elegido pasándolo a Recambio, y genera el código QR.
        """
        cliente_limpio = cliente.strip()
        patente_limpia = patente.strip().upper() or "S/P"
        if not cliente_limpio:
            return False, "Debes ingresar el nombre del cliente.", None

        ini_m = hora_a_minutos(hora_inicio)
        fin_m = hora_a_minutos(hora_fin)
        duracion_min = fin_m - ini_m
        if duracion_min < 30:
            return False, "La reserva mínima en grilla es de 30 minutos (el cobro real en portería es por minuto).", None

        candidatos = self.buscar_candidatos_ordenados(
            fecha=fecha,
            hora_inicio=hora_inicio,
            hora_fin=hora_fin,
            preferir_pool_recambio=False,
        )
        if not candidatos:
            self._registrar_evento(
                tipo_evento="INTENTO_RESERVA_RECHAZADO",
                rol_actor="Cliente",
                id_estacionamiento="-",
                id_reserva="-",
                propietario="-",
                cliente=cliente_limpio,
                fecha_operacion=fecha,
                hora_inicio=hora_inicio,
                hora_fin=hora_fin,
                estado_resultante="RECHAZADA",
                valor_operacion=0,
                detalle=f"Sin estacionamientos compatibles para {hora_inicio}-{hora_fin} (θ={self.theta:.2f} + margen).",
            )
            self.guardar()
            return (
                False,
                f"No hay estacionamientos compatibles entre {hora_inicio} y {hora_fin} que cumplan "
                f"el umbral θ={self.theta:.0%} y el margen de seguridad del propietario.",
                None,
            )

        est_elegido, motivo_seleccion = candidatos[0]
        nuevo_num = 1001 + len(self.reservas)
        res_id = f"RES-{nuevo_num}"
        codigo_qr = f"SIGE-QR-RES{nuevo_num}-{est_elegido.id_estacionamiento}"

        nueva_res = Reserva(
            id_reserva=res_id,
            id_estacionamiento=est_elegido.id_estacionamiento,
            propietario=est_elegido.propietario,
            cliente=cliente_limpio,
            patente=patente_limpia,
            fecha=fecha,
            hora_inicio=hora_inicio,
            hora_fin=hora_fin,
            duracion_reservada_min=duracion_min,
            minutos_reales_usados=duracion_min,
            minutos_sobreestadia=0,
            estado="CONFIRMADA",
            codigo_qr=codigo_qr,
            criterio_asignacion=motivo_seleccion,
            creada_en=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        nueva_res.calcular_cobro_y_reparto(minutos_efectivos=duracion_min, minutos_exceso=0)
        self.reservas.append(nueva_res)

        # Aplicar política de rotación: el lote elegido baja su prioridad y pasa a Estacionamiento de Recambio
        self._marcar_lote_en_recambio(est_elegido)

        self._registrar_evento(
            tipo_evento="CREACION_RESERVA",
            rol_actor="Cliente",
            id_estacionamiento=est_elegido.id_estacionamiento,
            id_reserva=res_id,
            propietario=est_elegido.propietario,
            cliente=cliente_limpio,
            fecha_operacion=fecha,
            hora_inicio=hora_inicio,
            hora_fin=hora_fin,
            estado_resultante="CONFIRMADA",
            valor_operacion=nueva_res.monto_total,
            detalle=(
                f"Reserva {res_id} asignada a {est_elegido.id_estacionamiento}. "
                f"Criterio: {motivo_seleccion}. Tarifa est.: ${nueva_res.monto_total}."
            ),
        )
        self.guardar()
        return (
            True,
            f"✅ Reserva {res_id} confirmada ({hora_inicio} a {hora_fin}). "
            f"Espacio asignado por el sistema: {est_elegido.id_estacionamiento} · "
            f"El lote {est_elegido.id_estacionamiento} pasa ahora a la Cola de Recambio para rotar equitativamente los demás estacionamientos.",
            nueva_res,
        )

    def cliente_cancelar_o_liberar_reserva(
        self, res_id: str, minutos_usados_si_anticipada: Optional[int] = None
    ) -> Tuple[bool, str]:
        """
        Permite al cliente:
        - Cancelar una reserva CONFIRMADA antes de ingresar ($0 cobro, libera el espacio y revierte uso si no entró).
        - Liberar anticipadamente una reserva EN_CURSO cobrando solo los minutos efectivos (Ley N° 20.967).
        """
        res = self.obtener_reserva(res_id)
        if not res:
            return False, "Reserva no encontrada."

        if res.estado in ("FINALIZADA", "CANCELADA"):
            return False, f"La reserva {res_id} ya se encuentra en estado {res.estado}."

        est = self.obtener_estacionamiento(res.id_estacionamiento)

        if res.estado == "CONFIRMADA" and not minutos_usados_si_anticipada:
            res.estado = "CANCELADA"
            res.minutos_reales_usados = 0
            res.calcular_cobro_y_reparto(0, 0)
            self._registrar_evento(
                tipo_evento="CANCELACION_CLIENTE",
                rol_actor="Cliente",
                id_estacionamiento=res.id_estacionamiento,
                id_reserva=res.id_reserva,
                propietario=res.propietario,
                cliente=res.cliente,
                fecha_operacion=res.fecha,
                hora_inicio=res.hora_inicio,
                hora_fin=res.hora_fin,
                estado_resultante="CANCELADA",
                valor_operacion=0,
                detalle=f"Cliente {res.cliente} canceló la reserva antes de ingresar. Espacio {res.id_estacionamiento} liberado.",
            )
            self.guardar()
            return True, f"Reserva {res_id} cancelada sin costo. El estacionamiento {res.id_estacionamiento} quedó libre."

        # Liberación anticipada con cobro por minuto real (Ley 20.967)
        min_efectivos = (
            minutos_usados_si_anticipada
            if minutos_usados_si_anticipada is not None
            else max(15, res.duracion_reservada_min // 2)
        )
        res.calcular_cobro_y_reparto(minutos_efectivos=min_efectivos, minutos_exceso=0)
        res.estado = "FINALIZADA"
        if est:
            est.ingresos_acumulados += res.pago_propietario_60

        self._registrar_evento(
            tipo_evento="LIBERACION_ANTICIPADA",
            rol_actor="Cliente",
            id_estacionamiento=res.id_estacionamiento,
            id_reserva=res.id_reserva,
            propietario=res.propietario,
            cliente=res.cliente,
            fecha_operacion=res.fecha,
            hora_inicio=res.hora_inicio,
            hora_fin=res.hora_fin,
            estado_resultante="FINALIZADA",
            valor_operacion=res.monto_total,
            detalle=(
                f"Liberación anticipada de {res_id}: se cobraron exactamente {min_efectivos} min "
                f"(Ley 20.967: ${res.monto_total:,}, ahorro de {res.duracion_reservada_min - min_efectivos} min)."
            ),
        )
        self.guardar()
        return (
            True,
            f"✅ Reserva {res_id} liberada anticipadamente. "
            f"Cobro por minuto efectivo (Ley 20.967): {min_efectivos} min × $25 = ${res.monto_total:,} "
            f"(Propietario 60%: ${res.pago_propietario_60:,} | Admin 30%: ${res.aporte_admin_30:,}).",
        )

    # =========================================================================
    # 4. CLIENTE · FUNCIONALIDAD PROPIA (F5 + F10): ACCESO QR Y COBRO POR MINUTO
    # =========================================================================
    def cliente_procesar_qr_porteria(
        self,
        codigo_qr_o_id: str,
        accion: str,
        minutos_reales: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """
        F5 (Código QR de entrada y salida) + F10 (Cobro por minuto Ley 20.967 y reparto 60/30/5/5):
        - accion == 'CHECK_IN': Valida el QR en portería, inicia la ocupación (EN_CURSO) y el cronómetro.
        - accion == 'CHECK_OUT': Valida el QR al salir, calcula los minutos reales usados y si hubo
          exceso sobre la duración reservada (aplicando multa x5 = $125/min), reparte los ingresos
          y libera el estacionamiento.
        """
        clave = codigo_qr_o_id.strip()
        res = next(
            (r for r in self.reservas if r.codigo_qr == clave or r.id_reserva == clave),
            None,
        )
        if not res:
            return False, f"Código QR o Reserva '{clave}' no válido en el sistema."

        est = self.obtener_estacionamiento(res.id_estacionamiento)

        if accion == "CHECK_IN":
            if res.estado != "CONFIRMADA":
                return False, f"La reserva {res.id_reserva} no puede hacer Check-in porque su estado es {res.estado}."
            res.estado = "EN_CURSO"
            self._registrar_evento(
                tipo_evento="CHECK_IN_QR",
                rol_actor="Cliente/Guardia",
                id_estacionamiento=res.id_estacionamiento,
                id_reserva=res.id_reserva,
                propietario=res.propietario,
                cliente=res.cliente,
                fecha_operacion=res.fecha,
                hora_inicio=res.hora_inicio,
                hora_fin=res.hora_fin,
                estado_resultante="EN_CURSO",
                valor_operacion=res.monto_total,
                detalle=f"QR '{res.codigo_qr}' validado en portería. Ingreso autorizado a {res.id_estacionamiento}.",
            )
            self.guardar()
            return (
                True,
                f"🟢 Check-in QR validado: Vehículo {res.patente} ({res.cliente}) ingresó a {res.id_estacionamiento}. Comienza el cobro por minuto.",
            )

        elif accion == "CHECK_OUT":
            if res.estado not in ("EN_CURSO", "CONFIRMADA", "SOBREESTADIA"):
                return False, f"La reserva {res.id_reserva} ya fue cerrada ({res.estado})."

            usados_total = minutos_reales if minutos_reales is not None else res.duracion_reservada_min
            if usados_total <= res.duracion_reservada_min:
                min_base = usados_total
                min_exceso = 0
            else:
                min_base = res.duracion_reservada_min
                min_exceso = usados_total - res.duracion_reservada_min

            res.calcular_cobro_y_reparto(minutos_efectivos=min_base, minutos_exceso=min_exceso)
            res.estado = "FINALIZADA"
            if est:
                est.ingresos_acumulados += res.pago_propietario_60

            self._registrar_evento(
                tipo_evento="CHECK_OUT_QR",
                rol_actor="Cliente/Guardia",
                id_estacionamiento=res.id_estacionamiento,
                id_reserva=res.id_reserva,
                propietario=res.propietario,
                cliente=res.cliente,
                fecha_operacion=res.fecha,
                hora_inicio=res.hora_inicio,
                hora_fin=res.hora_fin,
                estado_resultante="FINALIZADA",
                valor_operacion=res.monto_total,
                detalle=(
                    f"Salida QR '{res.codigo_qr}': {min_base} min normales (${res.monto_base}) + "
                    f"{min_exceso} min sobreestadía x5 (${res.multa_sobreestadia}) = Total ${res.monto_total}. "
                    f"Reparto 60/30/5/5 acreditado."
                ),
            )
            self.guardar()
            msg_exceso = (
                f" (incluye {min_exceso} min de sobreestadía con tarifa ×5 = ${res.multa_sobreestadia:,})"
                if min_exceso > 0
                else " (sin sobreestadía)"
            )
            return (
                True,
                f"🏁 Check-out QR completado para {res.id_reserva}{msg_exceso}.\n"
                f"• Total cobrado (Ley 20.967): **${res.monto_total:,}**\n"
                f"• Reparto: Propietario (60%): **${res.pago_propietario_60:,}** | "
                f"Administración (30%): **${res.aporte_admin_30:,}** | "
                f"Guardia (5%): **${res.bono_guardia_5:,}** | Operación (5%): **${res.ingreso_operacion_5:,}**.",
            )

        return False, "Acción QR no reconocida."

    # =========================================================================
    # 5. ADMINISTRADOR · FUNCIONALIDAD OBLIGATORIA (F6 + F9): ASIGNAR Y REASIGNAR
    # =========================================================================
    def admin_reasignar_reserva(
        self,
        res_id: str,
        nuevo_spot_id: str,
        motivo: str = "Reasignación operativa por Administración",
    ) -> Tuple[bool, str]:
        """
        F9 (Asignar y reasignar estacionamientos):
        El administrador asocia o reasigna una reserva vigente a otro estacionamiento compatible.
        Verifica antes que no existan conflictos de disponibilidad, bloqueo ni superposición,
        y actualiza el estado de recambio de ambos estacionamientos.
        """
        res = self.obtener_reserva(res_id)
        if not res:
            return False, "Reserva no encontrada."

        if res.estado not in ("CONFIRMADA", "EN_CURSO", "SOBREESTADIA"):
            return False, f"Solo se pueden reasignar reservas activas (estado actual: {res.estado})."

        if res.id_estacionamiento == nuevo_spot_id:
            return False, f"La reserva {res_id} ya está asignada al estacionamiento {nuevo_spot_id}."

        nuevo_est = self.obtener_estacionamiento(nuevo_spot_id)
        if not nuevo_est:
            return False, f"Estacionamiento destino {nuevo_spot_id} no existe."

        ok, razon = self.verificar_compatibilidad_estacionamiento(
            nuevo_est,
            fecha=res.fecha,
            hora_inicio=res.hora_inicio,
            hora_fin=res.hora_fin,
            ignorar_reserva_id=res.id_reserva,
        )
        if not ok:
            self._registrar_evento(
                tipo_evento="INTENTO_REASIGNACION_FALLIDO",
                rol_actor="Administrador",
                id_estacionamiento=nuevo_spot_id,
                id_reserva=res.id_reserva,
                propietario=nuevo_est.propietario,
                cliente=res.cliente,
                fecha_operacion=res.fecha,
                hora_inicio=res.hora_inicio,
                hora_fin=res.hora_fin,
                estado_resultante=res.estado,
                valor_operacion=0,
                detalle=f"Reasignación rechazada hacia {nuevo_spot_id}: {razon}",
            )
            self.guardar()
            return False, f"❌ Reasignación rechazada por validación de reglas: {razon}"

        spot_anterior = res.id_estacionamiento
        res.estacionamiento_original = spot_anterior
        res.id_estacionamiento = nuevo_est.id_estacionamiento
        res.propietario = nuevo_est.propietario
        res.codigo_qr = f"SIGE-QR-{res.id_reserva.replace('-', '')}-{nuevo_est.id_estacionamiento}"
        res.criterio_asignacion = f"Reasignado desde {spot_anterior} -> {nuevo_spot_id} ({motivo})"

        self._marcar_lote_en_recambio(nuevo_est)

        self._registrar_evento(
            tipo_evento="REASIGNACION_ADMIN",
            rol_actor="Administrador",
            id_estacionamiento=nuevo_spot_id,
            id_reserva=res.id_reserva,
            propietario=nuevo_est.propietario,
            cliente=res.cliente,
            fecha_operacion=res.fecha,
            hora_inicio=res.hora_inicio,
            hora_fin=res.hora_fin,
            estado_resultante=res.estado,
            valor_operacion=res.monto_total,
            detalle=f"Reserva {res.id_reserva} reasignada de {spot_anterior} a {nuevo_spot_id}. Motivo: {motivo}.",
        )
        self.guardar()
        return (
            True,
            f"✅ Reserva {res.id_reserva} ({res.cliente}) reasignada con éxito de **{spot_anterior}** a **{nuevo_spot_id}** ({nuevo_est.propietario}). "
            f"El lote {nuevo_spot_id} quedó marcado en la Cola de Recambio.",
        )

    # =========================================================================
    # 6. ADMINISTRADOR · FUNCIONALIDAD PROPIA (F7 + F8): CONTINGENCIAS, SOBREESTADÍA Y UMBRAL θ
    # =========================================================================
    def admin_declarar_o_resolver_sobreestadia(
        self, res_id: str, minutos_exceso: int, finalizar_ahora: bool = False
    ) -> Tuple[bool, str]:
        """
        F7 (Alertas de exceso de tiempo y tarifa penalizada x5 - Tabla 3.1 Solemne 1):
        Permite registrar un exceso de tiempo sobre una reserva activa, aplicando la tarifa x5
        ($125/min) y opcionalmente cerrando/liberando el espacio o reasignando si hay conflicto.
        """
        res = self.obtener_reserva(res_id)
        if not res:
            return False, "Reserva no encontrada."

        if minutos_exceso <= 0:
            return False, "Los minutos de exceso deben ser mayores a 0."

        res.calcular_cobro_y_reparto(
            minutos_efectivos=res.duracion_reservada_min,
            minutos_exceso=minutos_exceso,
        )
        est = self.obtener_estacionamiento(res.id_estacionamiento)

        if finalizar_ahora:
            res.estado = "FINALIZADA"
            if est:
                est.ingresos_acumulados += res.pago_propietario_60
            estado_ev = "FINALIZADA"
            accion_txt = "liquidada y liberada"
        else:
            res.estado = "SOBREESTADIA"
            estado_ev = "SOBREESTADIA"
            accion_txt = "marcada en ALERTA DE SOBREESTADÍA"

        self._registrar_evento(
            tipo_evento="GESTION_SOBREESTADIA_X5",
            rol_actor="Administrador",
            id_estacionamiento=res.id_estacionamiento,
            id_reserva=res.id_reserva,
            propietario=res.propietario,
            cliente=res.cliente,
            fecha_operacion=res.fecha,
            hora_inicio=res.hora_inicio,
            hora_fin=res.hora_fin,
            estado_resultante=estado_ev,
            valor_operacion=res.monto_total,
            detalle=(
                f"Sobreestadía de {minutos_exceso} min en {res.id_estacionamiento} ({accion_txt}). "
                f"Multa x5 ($125/min) = ${res.multa_sobreestadia}. Total actualizado: ${res.monto_total}."
            ),
        )
        self.guardar()
        return (
            True,
            f"🚨 Reserva {res.id_reserva} ({res.id_estacionamiento}) {accion_txt} con {minutos_exceso} min de exceso.\n"
            f"• Multa sobreestadía (×5 = $125/min): **${res.multa_sobreestadia:,}** | "
            f"Nuevo total: **${res.monto_total:,}**.",
        )

    def admin_actualizar_umbral_theta(self, nuevo_theta: float) -> Tuple[bool, str]:
        """
        F8 (Motor de disponibilidad - Tabla 5.1 Solemne 1):
        Modifica el umbral θ de probabilidad histórica exigida (ej. 0.60, 0.70, 0.80, 0.90, 0.95)
        y recalcula automáticamente las ventanas horarias ofrecidas de los 50 estacionamientos.
        """
        if not (0.50 <= nuevo_theta <= 0.99):
            return False, "El umbral θ debe estar entre 0.50 y 0.99."

        self.config["theta"] = f"{nuevo_theta:.2f}"
        con_oferta = 0
        bloques_totales_dia = 0

        for est in self.estacionamientos:
            inicio_of, fin_of, bloques_of = calcular_ventana_ofrecida(
                self.prob_por_bloque[est.id_estacionamiento],
                margen_bloques=est.bloques_margen,
                theta=nuevo_theta,
            )
            est.hora_inicio_ofrecida = inicio_of
            est.hora_fin_ofrecida = fin_of
            if bloques_of:
                con_oferta += 1
                bloques_totales_dia += len(bloques_of)
            else:
                est.semana_confirmada = False

        self._registrar_evento(
            tipo_evento="CAMBIO_UMBRAL_THETA",
            rol_actor="Administrador",
            id_estacionamiento="TODOS",
            id_reserva="-",
            propietario="-",
            cliente="-",
            fecha_operacion=self.config.get("fecha_operacion_actual", "2026-08-28"),
            hora_inicio="06:00",
            hora_fin="23:30",
            estado_resultante=f"THETA={nuevo_theta:.2f}",
            valor_operacion=0,
            detalle=(
                f"Umbral θ actualizado a {nuevo_theta:.2f}. Estacionamientos con oferta válida: "
                f"{con_oferta}/50 ({bloques_totales_dia} bloques/día)."
            ),
        )
        self.guardar()
        return (
            True,
            f"⚙️ Motor de disponibilidad recalibrado a **θ = {nuevo_theta:.2f}**: "
            f"**{con_oferta} de 50 estacionamientos** califican con oferta activa ({bloques_totales_dia} bloques/día protegidos con margen de 30/60 min).",
        )

    def admin_reiniciar_ciclo_recambio(self) -> Tuple[bool, str]:
        """Reinicia la bandera en_recambio de todos los lotes para comenzar un nuevo ciclo de rotación."""
        for e in self.estacionamientos:
            e.en_recambio = False
        self._registrar_evento(
            tipo_evento="ROTACION_RECAMBIO",
            rol_actor="Administrador",
            id_estacionamiento="TODOS",
            id_reserva="-",
            propietario="-",
            cliente="-",
            fecha_operacion=self.config.get("fecha_operacion_actual", "2026-08-28"),
            hora_inicio="06:00",
            hora_fin="23:30",
            estado_resultante="CICLO_REINICIADO",
            valor_operacion=0,
            detalle="Cola de recambio reiniciada: todos los estacionamientos vuelven a prioridad principal según disponibilidad.",
        )
        self.guardar()
        return True, "🔄 Ciclo de rotación reiniciado: todos los estacionamientos confirmados vuelven a Prioridad Principal ordenados por mayor disponibilidad."

    def obtener_resumen_kpis(self) -> Dict[str, Any]:
        """Calcula indicadores en vivo a partir de los CSV para mostrar en el monitor y preparar Entrega 3."""
        libres = sum(1 for e in self.estacionamientos if e.estado_actual == "LIBRE")
        arrendados = sum(1 for e in self.estacionamientos if e.estado_actual == "ARRENDADO")
        sobreestadia = sum(1 for e in self.estacionamientos if e.estado_actual == "SOBREESTADIA")
        dueno_o_bloq = sum(
            1 for e in self.estacionamientos if e.estado_actual in ("OCUPADO_DUENO", "BLOQUEADO")
        )
        en_recambio_cnt = sum(1 for e in self.estacionamientos if e.en_recambio)

        res_validas = [r for r in self.reservas if r.estado != "CANCELADA"]
        ingreso_bruto = sum(r.monto_total for r in res_validas)
        pago_duenos = sum(r.pago_propietario_60 for r in res_validas)
        aporte_comunidad = sum(r.aporte_admin_30 for r in res_validas)
        bono_guardia = sum(r.bono_guardia_5 for r in res_validas)
        ingreso_operador = sum(r.ingreso_operacion_5 for r in res_validas)
        reasignaciones = sum(1 for r in self.reservas if r.estacionamiento_original)

        return {
            "libres": libres,
            "arrendados": arrendados,
            "sobreestadia": sobreestadia,
            "dueno_o_bloq": dueno_o_bloq,
            "en_recambio": en_recambio_cnt,
            "ingreso_bruto": ingreso_bruto,
            "pago_duenos": pago_duenos,
            "aporte_comunidad": aporte_comunidad,
            "bono_guardia": bono_guardia,
            "ingreso_operador": ingreso_operador,
            "total_reservas": len(self.reservas),
            "reasignaciones": reasignaciones,
        }
