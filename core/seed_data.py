"""
Generador de datos semilla para SIGE (Hito 2) a partir del dataset real de la Solemne 1
(dataset_historico_hito1.csv: 720 registros, 20 días hábiles, 50 estacionamientos E01-E50).
Calcula exactamente:
- Fracción histórica de disponibilidad por bloque (06:00 a 23:30) para cada estacionamiento.
- Variación de la hora de regreso del propietario (< 1.5h -> Puntual 30 min; >= 1.5h -> Irregular 60 min).
- Curva polinomial de grado 4 de la Tabla B.1 del informe:
  f(x) = 0.00407x^4 - 0.20420x^3 + 2.90174x^2 - 7.35067x - 22.31389
"""

from __future__ import annotations
import csv
import os
import statistics
from typing import Dict, List, Tuple
from core.models import Estacionamiento, Reserva, EventoHistorial

BLOQUES_30_MIN: List[str] = [
    f"{h:02d}:{m:02d}" for h in range(6, 24) for m in (0, 30)
]

NOMBRES_PROPIETARIOS: List[str] = [
    "Claudio González", "Sebastián Aro", "Martín Díaz", "Matías Soto", "Camila Vargas",
    "Javiera Muñoz", "Valentina Rojas", "Francisca Pérez", "Constanza Contreras", "Catalina Silva",
    "Diego Martínez", "Nicolás Sepúlveda", "Matías Morales", "Alejandro Rodríguez", "Cristóbal López",
    "Fernanda Fuentes", "Isidora Hernández", "Martina Torres", "Antonia Araya", "Sofía Flores",
    "Benjamín Espinoza", "Lucas Valenzuela", "Tomás Castillo", "Joaquín Tapia", "Maximiliano Reyes",
    "Daniela Gutiérrez", "Macarena Castro", "Natalia Pizarro", "Carolina Álvarez", "Paulina Vásquez",
    "Rodrigo Sánchez", "Felipe Fernández", "Ignacio Carrasco", "Gonzalo Gómez", "Pablo Cortés",
    "Andrea Herrera", "Lorena Núñez", "Claudia Jara", "Marcela Vergara", "Patricia Rivera",
    "Mauricio Figueroa", "Eduardo Riquelme", "Hernán García", "Roberto Miranda", "Carlos Bravo",
    "Verónica Vera", "Mónica Molina", "Cecilia Vega", "Paola Campos", "Beatriz Sandoval"
]


def evaluar_curva_grado_4(hora_str: str) -> float:
    """Evalúa la curva polinomial de grado 4 de la Tabla B.1 de la Solemne 1."""
    partes = hora_str.split(":")
    x = int(partes[0]) + (int(partes[1]) / 60.0)
    val = (
        0.00407 * (x ** 4)
        - 0.20420 * (x ** 3)
        + 2.90174 * (x ** 2)
        - 7.35067 * x
        - 22.31389
    )
    return round(val, 1)


def analizar_dataset_hito1(csv_dataset_path: str) -> Tuple[Dict[str, Dict[str, float]], Dict[str, Dict[str, float]]]:
    """
    Lee dataset_historico_hito1.csv y retorna:
    1. stats_por_est: { 'E01': {'horas_dia': 9.0, 'std_regreso': 0.68, ...}, ... }
    2. prob_por_bloque: { 'E01': {'06:00': 0.0, ..., '15:30': 1.0}, ... }
    """
    with open(csv_dataset_path, mode="r", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    header = rows[0]
    data = rows[1:]
    spots = header[4:54]  # E01 .. E50
    days = [data[d : d + 36] for d in range(0, len(data), 36)]
    num_days = len(days)

    stats_por_est: Dict[str, Dict[str, float]] = {}
    prob_por_bloque: Dict[str, Dict[str, float]] = {}

    for idx, spot_id in enumerate(spots):
        col = 4 + idx
        free_blocks_total = sum(int(r[col]) for r in data)
        horas_dia = round((free_blocks_total * 0.5) / num_days, 2)

        # Calcular variación de hora de regreso (Anexo D Solemne 1)
        ret_hours: List[float] = []
        for day in days:
            ones = [b for b in range(len(day)) if int(day[b][col]) == 1]
            if ones:
                ret_b = ones[-1] + 1
                ret_hours.append(6.0 + ret_b * 0.5)
        std_ret = round(statistics.pstdev(ret_hours), 2) if len(ret_hours) > 1 else 0.0

        # Probabilidad histórica de estar libre en cada bloque (06:00 a 23:30)
        probs: Dict[str, float] = {}
        for b_idx, hora in enumerate(BLOQUES_30_MIN):
            libres_bloque = sum(int(day[b_idx][col]) for day in days)
            probs[hora] = round(libres_bloque / float(num_days), 4)

        prob_por_bloque[spot_id] = probs
        stats_por_est[spot_id] = {
            "horas_dia": horas_dia,
            "std_regreso": std_ret,
            "bloques_libres_total": free_blocks_total,
        }

    return stats_por_est, prob_por_bloque


def calcular_ventana_ofrecida(
    probs: Dict[str, float], margen_bloques: int, theta: float = 0.80
) -> Tuple[str, str, List[str]]:
    """
    Aplica la Regla de Oferta del Anexo D de la Solemne 1:
    Un bloque b se ofrece si su fracción histórica de disponibilidad >= theta
    en el bloque b y en los bloques siguientes del margen de seguridad (1 o 2 bloques).
    """
    ofrecidos: List[str] = []
    n = len(BLOQUES_30_MIN)
    for i, hora in enumerate(BLOQUES_30_MIN):
        if i + margen_bloques < n:
            cumple = all(
                probs[BLOQUES_30_MIN[k]] >= theta
                for k in range(i, i + 1 + margen_bloques)
            )
            if cumple:
                ofrecidos.append(hora)

    if not ofrecidos:
        return ("Sin oferta", "Sin oferta", [])

    inicio = ofrecidos[0]
    # El fin ofrecido es 30 min después del último bloque ofrecido
    ultimo_idx = BLOQUES_30_MIN.index(ofrecidos[-1])
    fin = BLOQUES_30_MIN[min(ultimo_idx + 1, n - 1)]
    return (inicio, fin, ofrecidos)


def generar_semilla_inicial(
    data_dir: str, theta: float = 0.80
) -> Tuple[List[Estacionamiento], List[Reserva], List[EventoHistorial]]:
    """
    Construye los 50 estacionamientos reales del Hito 1, con reservas de prueba y eventos
    iniciales para demostrar de inmediato las 6 funcionalidades, la rotación de recambio
    y las contingencias en la defensa técnica.
    """
    dataset_path = os.path.join(data_dir, "dataset_historico_hito1.csv")
    stats_por_est, prob_por_bloque = analizar_dataset_hito1(dataset_path)

    # Guardar tabla de probabilidades por bloque y curva grado 4 para consultas y Entrega 3
    prob_csv_path = os.path.join(data_dir, "probabilidades_bloques.csv")
    with open(prob_csv_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Hora", "Promedio_Libres_50", "Curva_Grado_4"] + list(prob_por_bloque.keys()))
        for hora in BLOQUES_30_MIN:
            prom_libres = round(sum(prob_por_bloque[s][hora] for s in prob_por_bloque) , 1)
            curva_val = evaluar_curva_grado_4(hora)
            row = [hora, prom_libres, curva_val] + [prob_por_bloque[s][hora] for s in prob_por_bloque]
            writer.writerow(row)

    estacionamientos: List[Estacionamiento] = []
    for idx in range(50):
        spot_id = f"E{idx + 1:02d}"
        st = stats_por_est[spot_id]
        std_ret = st["std_regreso"]
        es_puntual = std_ret < 1.5
        perfil = "PUNTUAL" if es_puntual else "IRREGULAR"
        margen_min = 30 if es_puntual else 60
        margen_bloques = 1 if es_puntual else 2

        inicio_of, fin_of, bloques_of = calcular_ventana_ofrecida(
            prob_por_bloque[spot_id], margen_bloques, theta=theta
        )

        # Índice de confiabilidad derivado de la regularidad histórica del propietario
        confiabilidad = round(max(55.0, min(99.0, 100.0 - (std_ret * 14.0))), 1)
        piso = (idx // 8) + 1
        num_depto = piso * 100 + ((idx % 8) + 1)

        # Si tiene bloques ofrecidos con theta=0.80, inicia con su semana confirmada
        tiene_oferta = len(bloques_of) > 0
        estado_ini = "LIBRE" if tiene_oferta else "OCUPADO_DUENO"

        est = Estacionamiento(
            id_estacionamiento=spot_id,
            propietario=NOMBRES_PROPIETARIOS[idx],
            departamento=f"Depto {num_depto}",
            horas_libres_dia_hist=st["horas_dia"],
            desviacion_regreso_h=std_ret,
            perfil_regularidad=perfil,
            margen_seguridad_min=margen_min,
            indice_confiabilidad=confiabilidad,
            semana_confirmada=tiene_oferta,
            hora_inicio_ofrecida=inicio_of,
            hora_fin_ofrecida=fin_of,
            estado_actual=estado_ini,
            bloques_bloqueados="",
            veces_asignado=0,
            en_recambio=False,
            ingresos_acumulados=0,
        )
        estacionamientos.append(est)

    # Crear reservas iniciales representativas para que el mapa en vivo (F6) y los CSV tengan datos ricos
    map_est = {e.id_estacionamiento: e for e in estacionamientos}
    reservas: List[Reserva] = []
    eventos: List[EventoHistorial] = []
    fecha_base = "2026-08-28"

    # 1. Reserva FINALIZADA en E18 (el estacionamiento con mayor disponibilidad: 11.1 h/día)
    # Muestra que E18 ya fue elegido hoy -> pasa a en_recambio=True para que roten los demás dueños
    r1 = Reserva(
        id_reserva="RES-1001",
        id_estacionamiento="E18",
        propietario=map_est["E18"].propietario,
        cliente="Pedro Saldivia (Registro Civil)",
        patente="LJKP-42",
        fecha=fecha_base,
        hora_inicio="09:00",
        hora_fin="11:00",
        duracion_reservada_min=120,
        minutos_reales_usados=114,
        minutos_sobreestadia=0,
        estado="FINALIZADA",
        codigo_qr="SIGE-QR-RES1001-E18",
        criterio_asignacion="Mayor disponibilidad histórica (11.1 h/día, θ>=0.80) · Pasa a Cola de Recambio",
        creada_en="2026-08-28 08:45:00",
    )
    r1.calcular_cobro_y_reparto(minutos_efectivos=114, minutos_exceso=0)
    map_est["E18"].veces_asignado = 1
    map_est["E18"].en_recambio = True
    map_est["E18"].ingresos_acumulados += r1.pago_propietario_60
    reservas.append(r1)

    # 2. Reserva EN_CURSO en E05 (segundo con mayor disponibilidad: 10.6 h/día)
    r2 = Reserva(
        id_reserva="RES-1002",
        id_estacionamiento="E05",
        propietario=map_est["E05"].propietario,
        cliente="Dra. Marcela Ojeda",
        patente="PRTW-88",
        fecha=fecha_base,
        hora_inicio="10:00",
        hora_fin="14:00",
        duracion_reservada_min=240,
        minutos_reales_usados=240,
        minutos_sobreestadia=0,
        estado="EN_CURSO",
        codigo_qr="SIGE-QR-RES1002-E05",
        criterio_asignacion="Rotación equitativa (E18 en recambio -> selecciona E05 con 10.6 h/día)",
        creada_en="2026-08-28 09:50:00",
    )
    r2.calcular_cobro_y_reparto(minutos_efectivos=240, minutos_exceso=0)
    map_est["E05"].estado_actual = "ARRENDADO"
    map_est["E05"].veces_asignado = 1
    map_est["E05"].en_recambio = True
    reservas.append(r2)

    # 3. Reserva CONFIRMADA en E02 (lista para hacer Check-in con QR o probar "¡Llegué antes!" del dueño)
    r3 = Reserva(
        id_reserva="RES-1003",
        id_estacionamiento="E02",
        propietario=map_est["E02"].propietario,
        cliente="Jorge Santana (Comercio Centro)",
        patente="GHTR-19",
        fecha=fecha_base,
        hora_inicio="11:30",
        hora_fin="13:30",
        duracion_reservada_min=120,
        minutos_reales_usados=120,
        minutos_sobreestadia=0,
        estado="CONFIRMADA",
        codigo_qr="SIGE-QR-RES1003-E02",
        criterio_asignacion="Rotación equitativa (E18 y E05 en recambio -> selecciona E02 con 10.1 h/día)",
        creada_en="2026-08-28 10:15:00",
    )
    r3.calcular_cobro_y_reparto(minutos_efectivos=120, minutos_exceso=0)
    map_est["E02"].estado_actual = "ARRENDADO"
    map_est["E02"].veces_asignado = 1
    map_est["E02"].en_recambio = True
    reservas.append(r3)

    # 4. Reserva con ALERTA DE SOBREESTADÍA en E16 (para demostrar F7 y recargo x5 de Tabla 3.1)
    r4 = Reserva(
        id_reserva="RES-1004",
        id_estacionamiento="E16",
        propietario=map_est["E16"].propietario,
        cliente="abogado Felipe Méndez",
        patente="KLMN-55",
        fecha=fecha_base,
        hora_inicio="09:30",
        hora_fin="11:30",
        duracion_reservada_min=120,
        minutos_reales_usados=120,
        minutos_sobreestadia=20,
        estado="SOBREESTADIA",
        codigo_qr="SIGE-QR-RES1004-E16",
        criterio_asignacion="Asignación automática por disponibilidad mixta (9.8 h/día)",
        creada_en="2026-08-28 09:20:00",
    )
    r4.calcular_cobro_y_reparto(minutos_efectivos=120, minutos_exceso=20)
    map_est["E16"].estado_actual = "SOBREESTADIA"
    map_est["E16"].veces_asignado = 1
    map_est["E16"].en_recambio = True
    reservas.append(r4)

    # Registrar eventos históricos iniciales para la Entrega 3
    eventos.extend([
        EventoHistorial(
            id_evento="EVT-0001",
            fecha_hora_registro="2026-08-28 08:00:00",
            tipo_evento="CONFIRMACION_SEMANA",
            rol_actor="Propietario",
            id_estacionamiento="E18",
            id_reserva="-",
            propietario=map_est["E18"].propietario,
            cliente="-",
            fecha_operacion=fecha_base,
            hora_inicio=map_est["E18"].hora_inicio_ofrecida,
            hora_fin=map_est["E18"].hora_fin_ofrecida,
            estado_resultante="LIBRE",
            valor_operacion=0,
            detalle="Propietario confirmó disponibilidad semanal sugerida con 1 clic (θ=0.80, margen 30 min).",
        ),
        EventoHistorial(
            id_evento="EVT-0002",
            fecha_hora_registro="2026-08-28 08:45:00",
            tipo_evento="CREACION_RESERVA",
            rol_actor="Cliente",
            id_estacionamiento="E18",
            id_reserva="RES-1001",
            propietario=map_est["E18"].propietario,
            cliente=r1.cliente,
            fecha_operacion=fecha_base,
            hora_inicio=r1.hora_inicio,
            hora_fin=r1.hora_fin,
            estado_resultante="CONFIRMADA",
            valor_operacion=3000,
            detalle="Asignación ciega a E18 (mayor disponibilidad). E18 pasa a estado de Recambio para rotar lotes.",
        ),
        EventoHistorial(
            id_evento="EVT-0003",
            fecha_hora_registro="2026-08-28 10:54:00",
            tipo_evento="CHECK_OUT_QR",
            rol_actor="Cliente/Guardia",
            id_estacionamiento="E18",
            id_reserva="RES-1001",
            propietario=map_est["E18"].propietario,
            cliente=r1.cliente,
            fecha_operacion=fecha_base,
            hora_inicio="09:00",
            hora_fin="10:54",
            estado_resultante="FINALIZADA",
            valor_operacion=r1.monto_total,
            detalle=f"Salida validada con QR (114 min reales Ley 20.967 = ${r1.monto_total}). Reparto 60/30/5/5 aplicado.",
        ),
        EventoHistorial(
            id_evento="EVT-0004",
            fecha_hora_registro="2026-08-28 09:50:00",
            tipo_evento="CREACION_RESERVA",
            rol_actor="Cliente",
            id_estacionamiento="E05",
            id_reserva="RES-1002",
            propietario=map_est["E05"].propietario,
            cliente=r2.cliente,
            fecha_operacion=fecha_base,
            hora_inicio=r2.hora_inicio,
            hora_fin=r2.hora_fin,
            estado_resultante="EN_CURSO",
            valor_operacion=r2.monto_total,
            detalle="Check-in QR realizado en portería. E05 marcado en cola de recambio tras su selección.",
        ),
        EventoHistorial(
            id_evento="EVT-0005",
            fecha_hora_registro="2026-08-28 11:50:00",
            tipo_evento="ALERTA_SOBREESTADIA",
            rol_actor="Sistema/Admin",
            id_estacionamiento="E16",
            id_reserva="RES-1004",
            propietario=map_est["E16"].propietario,
            cliente=r4.cliente,
            fecha_operacion=fecha_base,
            hora_inicio=r4.hora_inicio,
            hora_fin=r4.hora_fin,
            estado_resultante="SOBREESTADIA",
            valor_operacion=r4.monto_total,
            detalle="Exceso de 20 min detectado sobre hora fin (11:30). Se activa tarifa penalizada x5 ($125/min).",
        ),
    ])

    return estacionamientos, reservas, eventos
