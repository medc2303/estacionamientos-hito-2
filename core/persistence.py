"""
Gestor de Persistencia Híbrida (CSV Local + Bot de Google Cloud / Google Sheets API).
Cumple con:
- RT03 (Persistencia): Conserva estados y recupera datos tras cerrar y volver a ejecutar.
- RT04 (Datos para el Dashboard Entrega 3): Mantiene archivos CSV estructurados en data/.
- Hosting en GitHub + Streamlit Cloud: Integra un Bot de Cuenta de Servicio de Google Cloud
  (gspread + google-auth) que respalda y restaura automáticamente las tablas CSV en un
  Google Sheet compartido con el correo del bot.
"""

from __future__ import annotations
import csv
import json
import os
from typing import Dict, List, Optional, Tuple, Any
from core.models import Estacionamiento, Reserva, EventoHistorial
from core.seed_data import generar_semilla_inicial


class GoogleSheetsBotManager:
    """
    Administra la sincronización bidireccional entre los archivos CSV locales
    y una Hoja de Cálculo de Google (Google Sheets) mediante un Bot Service Account.
    """

    def __init__(self, data_dir: str) -> None:
        self.data_dir = data_dir
        self.config_bot_path = os.path.join(data_dir, "google_bot_config.json")
        self.ultimo_estado: str = "Modo CSV Local Activo"
        self.bot_email: str = ""
        self.sheet_url: str = ""
        self.conectado: bool = False
        self._creds_dict: Optional[Dict[str, Any]] = None
        self._cargar_configuracion_guardada()

    def _cargar_configuracion_guardada(self) -> None:
        """Intenta cargar credenciales desde st.secrets o desde archivo de configuración local."""
        # 1. Intentar desde archivo local si el usuario lo configuró en la interfaz
        if os.path.exists(self.config_bot_path):
            try:
                with open(self.config_bot_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self._creds_dict = saved.get("service_account")
                self.sheet_url = saved.get("sheet_url", "")
                if self._creds_dict and self.sheet_url:
                    self.bot_email = self._creds_dict.get("client_email", "")
                    self.conectado = True
                    self.ultimo_estado = f"Bot Google vinculado ({self.bot_email})"
                    return
            except Exception:
                pass

        # 2. Intentar desde st.secrets (cuando corre en Streamlit Community Cloud)
        try:
            import streamlit as st
            if "gcp_service_account" in st.secrets:
                self._creds_dict = dict(st.secrets["gcp_service_account"])
                self.sheet_url = st.secrets.get("spreadsheet_url", "")
                self.bot_email = self._creds_dict.get("client_email", "")
                if self._creds_dict and self.sheet_url:
                    self.conectado = True
                    self.ultimo_estado = f"Bot Google Cloud activo desde st.secrets ({self.bot_email})"
        except Exception:
            pass

    def configurar_bot(self, creds_json_str: str, sheet_url: str) -> Tuple[bool, str]:
        """Guarda y valida las credenciales JSON del Bot de Google Cloud y el URL del Google Sheet."""
        try:
            creds_data = json.loads(creds_json_str)
            if "client_email" not in creds_data or "private_key" not in creds_data:
                return False, "El JSON no corresponde a una Cuenta de Servicio de Google Cloud válida."

            self._creds_dict = creds_data
            self.sheet_url = sheet_url.strip()
            self.bot_email = creds_data["client_email"]

            with open(self.config_bot_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"service_account": creds_data, "sheet_url": self.sheet_url},
                    f,
                    indent=2,
                    ensure_ascii=False,
                )

            self.conectado = True
            self.ultimo_estado = f"Bot configurado: {self.bot_email}"
            return True, f"Bot de Google ({self.bot_email}) vinculado correctamente."
        except Exception as e:
            return False, f"Error al leer credenciales JSON del Bot: {e}"

    def desconectar_bot(self) -> None:
        self.conectado = False
        self._creds_dict = None
        self.sheet_url = ""
        self.bot_email = ""
        self.ultimo_estado = "Modo CSV Local Activo"
        if os.path.exists(self.config_bot_path):
            try:
                os.remove(self.config_bot_path)
            except OSError:
                pass

    def _abrir_spreadsheet(self):
        """Abre la conexión con Google Sheets usando gspread y google-auth."""
        if not self.conectado or not self._creds_dict or not self.sheet_url:
            return None
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(self._creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        if self.sheet_url.startswith("http"):
            return client.open_by_url(self.sheet_url)
        return client.open_by_key(self.sheet_url)

    def sincronizar_csv_a_sheets(self, nombres_archivos: List[str]) -> Tuple[bool, str]:
        """Sube el contenido actual de los archivos CSV locales a pestañas del Google Sheet."""
        if not self.conectado:
            return False, "El Bot de Google no está vinculado; los datos se guardaron en los CSV locales."
        try:
            sh = self._abrir_spreadsheet()
            if sh is None:
                return False, "No fue posible abrir el Google Sheet."

            existentes = {ws.title: ws for ws in sh.worksheets()}
            for nombre_csv in nombres_archivos:
                ruta_csv = os.path.join(self.data_dir, nombre_csv)
                if not os.path.exists(ruta_csv):
                    continue
                titulo_hoja = nombre_csv.replace(".csv", "")
                with open(ruta_csv, mode="r", encoding="utf-8") as f:
                    filas = list(csv.reader(f))
                if not filas:
                    continue

                if titulo_hoja in existentes:
                    ws = existentes[titulo_hoja]
                    ws.clear()
                else:
                    ws = sh.add_worksheet(
                        title=titulo_hoja,
                        rows=max(100, len(filas) + 20),
                        cols=max(25, len(filas[0]) + 2),
                    )
                ws.update(filas)

            self.ultimo_estado = "CSV sincronizados con Google Sheets exitosamente"
            return True, "Todos los archivos CSV fueron respaldados en Google Sheets por el Bot."
        except Exception as e:
            self.ultimo_estado = f"Respaldo local CSV OK (Aviso Bot: {e})"
            return False, f"Guardado en CSV local exitoso. Aviso al sincronizar Google Sheets: {e}"

    def restaurar_sheets_a_csv(self, nombres_archivos: List[str]) -> Tuple[bool, str]:
        """Descarga las pestañas del Google Sheet hacia los archivos CSV locales."""
        if not self.conectado:
            return False, "El Bot de Google no está configurado."
        try:
            sh = self._abrir_spreadsheet()
            if sh is None:
                return False, "No fue posible conectar con el Google Sheet."

            existentes = {ws.title: ws for ws in sh.worksheets()}
            restaurados = 0
            for nombre_csv in nombres_archivos:
                titulo_hoja = nombre_csv.replace(".csv", "")
                if titulo_hoja in existentes:
                    filas = existentes[titulo_hoja].get_all_values()
                    if len(filas) > 1:
                        ruta_csv = os.path.join(self.data_dir, nombre_csv)
                        with open(ruta_csv, mode="w", newline="", encoding="utf-8") as f:
                            writer = csv.writer(f)
                            writer.writerows(filas)
                        restaurados += 1
            if restaurados > 0:
                self.ultimo_estado = f"{restaurados} tablas CSV restauradas desde Google Sheets"
                return True, f"Se restauraron {restaurados} archivos CSV desde Google Sheets."
            return False, "El Google Sheet aún no contiene tablas válidas para restaurar."
        except Exception as e:
            return False, f"Error al descargar desde Google Sheets: {e}"


class GestorPersistenciaCSV:
    """
    Gestiona la lectura y escritura de los archivos CSV requeridos por RT03 y RT04:
    - estacionamientos.csv
    - reservas.csv
    - historial_eventos.csv
    - config_sistema.csv
    Y coordina la sincronización opcional con el Bot de Google Cloud.
    """

    ARCHIVOS_OPERACIONALES = [
        "estacionamientos.csv",
        "reservas.csv",
        "historial_eventos.csv",
        "config_sistema.csv",
    ]

    def __init__(self, data_dir: str) -> None:
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.est_csv = os.path.join(self.data_dir, "estacionamientos.csv")
        self.res_csv = os.path.join(self.data_dir, "reservas.csv")
        self.evt_csv = os.path.join(self.data_dir, "historial_eventos.csv")
        self.cfg_csv = os.path.join(self.data_dir, "config_sistema.csv")
        self.bot_google = GoogleSheetsBotManager(self.data_dir)

    def inicializar_si_no_existe(self, forzar_reinicio: bool = False) -> None:
        """
        Si no existen los CSV operacionales (o si se solicita reiniciar a los datos semilla del Hito 1),
        intenta primero restaurar desde el Bot de Google Sheets (si no es reinicio forzado) y,
        en su defecto, genera los CSV semilla a partir de dataset_historico_hito1.csv.
        """
        existen_locales = (
            os.path.exists(self.est_csv)
            and os.path.exists(self.res_csv)
            and os.path.exists(self.evt_csv)
        )
        if existen_locales and not forzar_reinicio:
            return

        if not forzar_reinicio and self.bot_google.conectado:
            ok, _ = self.bot_google.restaurar_sheets_a_csv(self.ARCHIVOS_OPERACIONALES)
            if ok and os.path.exists(self.est_csv):
                return

        estacionamientos, reservas, eventos = generar_semilla_inicial(self.data_dir, theta=0.80)
        config = {"theta": "0.80", "fecha_operacion_actual": "2026-08-28"}
        self.guardar_todo(estacionamientos, reservas, eventos, config)

    def guardar_todo(
        self,
        estacionamientos: List[Estacionamiento],
        reservas: List[Reserva],
        eventos: List[EventoHistorial],
        config: Dict[str, str],
        sincronizar_nube: bool = True,
    ) -> None:
        """Escribe todas las entidades en sus respectivos archivos CSV y sincroniza con el Bot si está activo."""
        # 1. Guardar estacionamientos.csv
        if estacionamientos:
            campos_est = list(estacionamientos[0].to_dict().keys())
            with open(self.est_csv, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=campos_est)
                writer.writeheader()
                for e in estacionamientos:
                    writer.writerow(e.to_dict())

        # 2. Guardar reservas.csv
        campos_res = [
            "id_reserva", "id_estacionamiento", "propietario", "cliente", "patente",
            "fecha", "hora_inicio", "hora_fin", "duracion_reservada_min",
            "minutos_reales_usados", "minutos_sobreestadia", "estado", "codigo_qr",
            "tarifa_minuto", "monto_base", "multa_sobreestadia", "compensacion_cliente",
            "monto_total", "pago_propietario_60", "aporte_admin_30", "bono_guardia_5",
            "ingreso_operacion_5", "estacionamiento_original", "criterio_asignacion", "creada_en"
        ]
        with open(self.res_csv, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=campos_res)
            writer.writeheader()
            for r in reservas:
                writer.writerow(r.to_dict())

        # 3. Guardar historial_eventos.csv
        campos_evt = [
            "id_evento", "fecha_hora_registro", "tipo_evento", "rol_actor",
            "id_estacionamiento", "id_reserva", "propietario", "cliente",
            "fecha_operacion", "hora_inicio", "hora_fin", "estado_resultante",
            "valor_operacion", "detalle"
        ]
        with open(self.evt_csv, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=campos_evt)
            writer.writeheader()
            for ev in eventos:
                writer.writerow(ev.to_dict())

        # 4. Guardar config_sistema.csv
        with open(self.cfg_csv, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["clave", "valor"])
            for k, v in config.items():
                writer.writerow([k, str(v)])

        # 5. Si el Bot de Google Cloud está conectado, respaldar en Google Sheets
        if sincronizar_nube and self.bot_google.conectado:
            self.bot_google.sincronizar_csv_a_sheets(self.ARCHIVOS_OPERACIONALES)

    def cargar_todo(
        self,
    ) -> Tuple[List[Estacionamiento], List[Reserva], List[EventoHistorial], Dict[str, str]]:
        """Recupera el estado completo del sistema desde los archivos CSV."""
        self.inicializar_si_no_existe(forzar_reinicio=False)

        estacionamientos: List[Estacionamiento] = []
        with open(self.est_csv, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                estacionamientos.append(
                    Estacionamiento(
                        id_estacionamiento=row["id_estacionamiento"],
                        propietario=row["propietario"],
                        departamento=row["departamento"],
                        horas_libres_dia_hist=float(row["horas_libres_dia_hist"]),
                        desviacion_regreso_h=float(row["desviacion_regreso_h"]),
                        perfil_regularidad=row["perfil_regularidad"],
                        margen_seguridad_min=int(float(row["margen_seguridad_min"])),
                        indice_confiabilidad=float(row["indice_confiabilidad"]),
                        semana_confirmada=str(row["semana_confirmada"]).lower() in ("true", "1", "si", "sí"),
                        hora_inicio_ofrecida=row["hora_inicio_ofrecida"],
                        hora_fin_ofrecida=row["hora_fin_ofrecida"],
                        estado_actual=row["estado_actual"],
                        bloques_bloqueados=row.get("bloques_bloqueados", ""),
                        veces_asignado=int(float(row.get("veces_asignado", 0))),
                        en_recambio=str(row.get("en_recambio", "False")).lower() in ("true", "1", "si", "sí"),
                        ingresos_acumulados=int(float(row.get("ingresos_acumulados", 0))),
                    )
                )

        reservas: List[Reserva] = []
        if os.path.exists(self.res_csv):
            with open(self.res_csv, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    reservas.append(
                        Reserva(
                            id_reserva=row["id_reserva"],
                            id_estacionamiento=row["id_estacionamiento"],
                            propietario=row["propietario"],
                            cliente=row["cliente"],
                            patente=row.get("patente", "S/P"),
                            fecha=row["fecha"],
                            hora_inicio=row["hora_inicio"],
                            hora_fin=row["hora_fin"],
                            duracion_reservada_min=int(float(row["duracion_reservada_min"])),
                            minutos_reales_usados=int(float(row["minutos_reales_usados"])),
                            minutos_sobreestadia=int(float(row.get("minutos_sobreestadia", 0))),
                            estado=row["estado"],
                            codigo_qr=row["codigo_qr"],
                            tarifa_minuto=int(float(row.get("tarifa_minuto", 25))),
                            monto_base=int(float(row.get("monto_base", 0))),
                            multa_sobreestadia=int(float(row.get("multa_sobreestadia", 0))),
                            compensacion_cliente=int(float(row.get("compensacion_cliente", 0))),
                            monto_total=int(float(row.get("monto_total", 0))),
                            pago_propietario_60=int(float(row.get("pago_propietario_60", 0))),
                            aporte_admin_30=int(float(row.get("aporte_admin_30", 0))),
                            bono_guardia_5=int(float(row.get("bono_guardia_5", 0))),
                            ingreso_operacion_5=int(float(row.get("ingreso_operacion_5", 0))),
                            estacionamiento_original=row.get("estacionamiento_original", ""),
                            criterio_asignacion=row.get("criterio_asignacion", ""),
                            creada_en=row.get("creada_en", ""),
                        )
                    )

        eventos: List[EventoHistorial] = []
        if os.path.exists(self.evt_csv):
            with open(self.evt_csv, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    eventos.append(
                        EventoHistorial(
                            id_evento=row["id_evento"],
                            fecha_hora_registro=row["fecha_hora_registro"],
                            tipo_evento=row["tipo_evento"],
                            rol_actor=row["rol_actor"],
                            id_estacionamiento=row["id_estacionamiento"],
                            id_reserva=row["id_reserva"],
                            propietario=row["propietario"],
                            cliente=row["cliente"],
                            fecha_operacion=row["fecha_operacion"],
                            hora_inicio=row["hora_inicio"],
                            hora_fin=row["hora_fin"],
                            estado_resultante=row["estado_resultante"],
                            valor_operacion=int(float(row.get("valor_operacion", 0))),
                            detalle=row["detalle"],
                        )
                    )

        config: Dict[str, str] = {"theta": "0.80", "fecha_operacion_actual": "2026-08-28"}
        if os.path.exists(self.cfg_csv):
            with open(self.cfg_csv, mode="r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader, None)
                for r in reader:
                    if len(r) >= 2:
                        config[r[0]] = r[1]

        return estacionamientos, reservas, eventos, config
