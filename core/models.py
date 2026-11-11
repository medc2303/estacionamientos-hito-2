"""
Modelos de dominio en Programación Orientada a Objetos (POO) para SIGE (Hito 2).
Traduce las entidades y reglas definidas en la Solemne 1 (Primer Hito Evaluativo):
- Estacionamiento / Propietario (con índice de confiabilidad, margen 30/60 min y cola de recambio)
- Reserva (con asignación ciega, código QR, cobro por minuto Ley 20.967 y reparto 60/30/5/5)
- EventoHistorial (trazabilidad completa en CSV para KPIs de la Entrega 3)
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any


TARIFA_MINUTO_BASE = 25          # $25 por minuto ($1.500 / hora, $750 / bloque de 30 min) - Ley 20.967
MULTIPLICADOR_SOBREESTADIA = 5   # Penalización x5 ($125/min) por exceso de tiempo (Tabla 3.1 Solemne 1)
COMPENSACION_CONTINGENCIA = 1500 # Compensación al cliente ($1.500 = 1h gratis) si dueño vuelve y no hay recambio

# Reparto de ingresos (Sección III.4 Solemne 1)
PCT_PROPIETARIO = 0.60
PCT_ADMINISTRACION = 0.30
PCT_GUARDIA = 0.05
PCT_OPERACION = 0.05


@dataclass
class Estacionamiento:
    """Representa uno de los 50 estacionamientos (E01 a E50) y los datos de su propietario."""
    id_estacionamiento: str
    propietario: str
    departamento: str
    horas_libres_dia_hist: float
    desviacion_regreso_h: float
    perfil_regularidad: str          # "PUNTUAL" (< 1.5h var) o "IRREGULAR" (>= 1.5h var)
    margen_seguridad_min: int        # 30 min (1 bloque) si es puntual, 60 min (2 bloques) si es irregular
    indice_confiabilidad: float      # 0.0 a 100.0
    semana_confirmada: bool          # F1: Disponibilidad mixta confirmada con 1 clic
    hora_inicio_ofrecida: str        # Ej. "08:30"
    hora_fin_ofrecida: str           # Ej. "17:30"
    estado_actual: str               # "LIBRE", "OCUPADO_DUENO", "ARRENDADO", "SOBREESTADIA", "BLOQUEADO"
    bloques_bloqueados: str = ""     # Bloques específicos bloqueados por el dueño (separados por coma)
    veces_asignado: int = 0          # Cantidad de veces que ya fue seleccionado
    en_recambio: bool = False        # True si ya fue elegido en el ciclo actual (baja prioridad / pasa a recambio)
    ingresos_acumulados: int = 0     # 60% acumulado por el propietario ($)

    @property
    def bloques_margen(self) -> int:
        """Cantidad de bloques de 30 minutos requeridos como margen de seguridad."""
        return 1 if self.margen_seguridad_min <= 30 else 2

    @property
    def max_duracion_reserva_min(self) -> int:
        """Dueños puntuales permiten reservas largas (hasta 8h); irregulares solo reservas cortas (máx 2h)."""
        return 480 if self.perfil_regularidad == "PUNTUAL" else 120

    @property
    def lista_bloques_bloqueados(self) -> List[str]:
        if not self.bloques_bloqueados:
            return []
        return [b.strip() for b in self.bloques_bloqueados.split(",") if b.strip()]

    def puntaje_prioridad_asignacion(self) -> float:
        """
        Calcula el puntaje de selección del estacionamiento:
        - Premia a los propietarios con mayor disponibilidad histórica (horas_libres_dia_hist)
          y mayor índice de confiabilidad.
        - Si el lote ya fue elegido (en_recambio=True), baja su prioridad para que todos los
          estacionamientos roten equitativamente y quede como estacionamiento de recambio.
        """
        base = self.horas_libres_dia_hist * (self.indice_confiabilidad / 100.0)
        factor_uso = 1.0 / (1.0 + self.veces_asignado * 0.5)
        penalizacion_recambio = 0.15 if self.en_recambio else 1.0
        return round(base * factor_uso * penalizacion_recambio, 4)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Reserva:
    """Representa una reserva de estacionamiento realizada por un cliente."""
    id_reserva: str
    id_estacionamiento: str
    propietario: str
    cliente: str
    patente: str
    fecha: str                       # YYYY-MM-DD
    hora_inicio: str                 # HH:MM
    hora_fin: str                    # HH:MM
    duracion_reservada_min: int
    minutos_reales_usados: int
    minutos_sobreestadia: int
    estado: str                      # "CONFIRMADA", "EN_CURSO", "FINALIZADA", "REASIGNADA", "CANCELADA", "SOBREESTADIA"
    codigo_qr: str
    tarifa_minuto: int = TARIFA_MINUTO_BASE
    monto_base: int = 0
    multa_sobreestadia: int = 0
    compensacion_cliente: int = 0
    monto_total: int = 0
    pago_propietario_60: int = 0
    aporte_admin_30: int = 0
    bono_guardia_5: int = 0
    ingreso_operacion_5: int = 0
    estacionamiento_original: str = ""
    criterio_asignacion: str = ""
    creada_en: str = ""

    def calcular_cobro_y_reparto(self, minutos_efectivos: int, minutos_exceso: int = 0) -> None:
        """
        Aplica la Ley N° 20.967: cobro por minuto realmente usado sin redondear hacia arriba ($25/min),
        recargo x5 ($125/min) en caso de sobreestadía, y reparto 60% / 30% / 5% / 5%.
        """
        self.minutos_reales_usados = max(0, int(minutos_efectivos))
        self.minutos_sobreestadia = max(0, int(minutos_exceso))
        self.monto_base = self.minutos_reales_usados * self.tarifa_minuto
        self.multa_sobreestadia = self.minutos_sobreestadia * (self.tarifa_minuto * MULTIPLICADOR_SOBREESTADIA)
        self.monto_total = self.monto_base + self.multa_sobreestadia

        self.pago_propietario_60 = int(round(self.monto_total * PCT_PROPIETARIO))
        self.aporte_admin_30 = int(round(self.monto_total * PCT_ADMINISTRACION))
        self.bono_guardia_5 = int(round(self.monto_total * PCT_GUARDIA))
        self.ingreso_operacion_5 = self.monto_total - (
            self.pago_propietario_60 + self.aporte_admin_30 + self.bono_guardia_5
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EventoHistorial:
    """Registro histórico estructurado para auditoría y futuro Dashboard de KPIs (Entrega 3)."""
    id_evento: str
    fecha_hora_registro: str
    tipo_evento: str
    rol_actor: str
    id_estacionamiento: str
    id_reserva: str
    propietario: str
    cliente: str
    fecha_operacion: str
    hora_inicio: str
    hora_fin: str
    estado_resultante: str
    valor_operacion: int
    detalle: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
