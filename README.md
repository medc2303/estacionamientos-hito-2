# 🅿️ SIGE — Gestión Eficiente de Estacionamientos (Entrega 2)

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io/deploy?repository=medc2303/estacionamientos-hito-2&branch=main&mainModule=app.py)

Prototipo funcional en **Python + Streamlit** desarrollado para la **Entrega 2 del Hito Evaluativo Integrativo** (*Gestión Eficiente de Estacionamientos en Edificio Residencial de Puerto Montt*).

* **Integrantes:** Claudio González, Sebastián Aro, Martín Díaz, Matías Soto
* **Docente:** Manuel Reveco

---

## 🎯 Funcionalidades Implementadas (6 Principales)

| Rol | Tipo | Funcionalidad | Reglas de Negocio Aplicadas |
| :--- | :--- | :--- | :--- |
| **Propietario** | **Obligatoria** | **Liberar y bloquear estacionamiento (+ Botón *«¡Llegué antes!»* F2)** | Mantiene prioridad absoluta del dueño (`RN01`). Si bloquea un horario con reserva vigente, el sistema la reasigna automáticamente a un **Estacionamiento de Recambio** o compensa al cliente. |
| **Propietario** | **Propia (F1)** | **Confirmar disponibilidad semanal mixta con 1 clic y perfil de regularidad** | Cruza los 720 registros del Hito 1 con el umbral $\theta = 0,80$ y aplica margen de seguridad de **30 min** (puntual $<1,5\text{ h}$) o **60 min** (irregular $\ge 1,5\text{ h}$). |
| **Cliente** | **Obligatoria (F4)** | **Reservar por rango horario (asignación automática) y Cancelar / Liberar anticipadamente** | Asignación ciega con **Rotación Equitativa y Cola de Recambio**: premia a los dueños con mayor disponibilidad y, una vez elegido un lote, baja su prioridad pasándolo a **Recambio** para que todos los estacionamientos se ocupen equitativamente. |
| **Cliente** | **Propia (F5 + F10)** | **Acceso QR en Portería (Check-in / Check-out) y Cobro Ley N° 20.967** | Escaneo de código QR al entrar y salir, cobro exacto por minuto real usado (**\$25/min** sin redondeo), recargo $\times 5$ (**\$125/min**) en sobreestadía y reparto **60% Dueño / 30% Comunidad / 5% Guardia / 5% Operación**. |
| **Administrador** | **Obligatoria (F6 + F9)** | **Mapa de Ocupación en Vivo y Asignar / Reasignar estacionamientos** | Cuadrícula en vivo de los 50 estacionamientos (`E01`–`E50`) y reasignación manual o por contingencia validando cero superposición (`RN02`) y margen de seguridad. |
| **Administrador** | **Propia (F7 + F8)** | **Gestión de Alertas de Sobreestadía ($\times 5$) y Calibración del Motor ($\theta$)** | Declaración/liquidación de excesos de tiempo y ajuste en vivo del umbral $\theta$ ($0,60$ a $0,95$, Tabla 5.1) sobre los 50 estacionamientos. |

---

## 💾 Persistencia Dual: Archivos CSV (`RT03`/`RT04`) + Bot de Google Cloud

1. **Archivos CSV Locales (`data/`):**
   * `data/estacionamientos.csv`: Estado actual de los 50 lotes (`E01`–`E50`), propietario, confiabilidad, margen (30/60 min), contador de usos y estado en la **Cola de Recambio (`en_recambio`)**.
   * `data/reservas.csv`: Reservas confirmadas, en curso, finalizadas, reasignadas y canceladas con su desglose financiero 60/30/5/5.
   * `data/historial_eventos.csv`: Bitácora histórica completa con fecha y hora para construir el Dashboard de KPIs de la **Entrega 3**.
   * `data/dataset_historico_hito1.csv`: Los 720 registros originales del Hito 1 (15.289 bloques libres).
2. **Bot de Google Cloud (`Service Account` + `Google Sheets API`):**
   * En la pestaña **📊 4. Datos CSV y Bot Google** (o mediante `st.secrets` en Streamlit Cloud) puedes vincular el JSON de tu cuenta de servicio de Google Cloud para respaldar y restaurar automáticamente los 4 archivos CSV en una hoja de **Google Sheets**.

---

## 🚀 Ejecución Local y Despliegue en GitHub + Streamlit Cloud

### Ejecución Local
Haz doble clic en **`iniciar.bat`** o ejecuta en terminal:
```bash
pip install -r requirements.txt
streamlit run app.py
```

### Despliegue en Streamlit Community Cloud
1. Sube este repositorio a GitHub con el nombre **`estacionamientos-hito-2`**.
2. Entra a **[share.streamlit.io](https://share.streamlit.io)**, selecciona el repositorio `estacionamientos-hito-2`, rama `main` y archivo principal `app.py`.
3. *(Opcional)* En **App Settings → Secrets**, pega las credenciales de tu Bot de Google siguiendo la plantilla `.streamlit/secrets.toml.example`.
