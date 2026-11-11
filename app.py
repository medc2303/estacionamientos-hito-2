"""
Aplicación Web en Streamlit — SIGE (Sistema Inteligente de Gestión de Estacionamientos)
Entrega 2 · Hito Evaluativo Integrativo (Basado en la Solemne 1 - Edificio Residencial Puerto Montt)
Autores: Claudio González, Sebastián Aro, Martín Díaz, Matías Soto
Docente: Manuel Reveco
"""

from __future__ import annotations
import os
import pandas as pd
import streamlit as st

from core.engine import (
    MotorSIGE,
    BLOQUES_30_MIN,
    TABLA_5_1_UMBRALES,
    hora_a_minutos,
)

# Configuración de página
st.set_page_config(
    page_title="SIGE · Gestión Eficiente de Estacionamientos (Hito 2)",
    page_icon="🅿️",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def obtener_motor() -> MotorSIGE:
    if "motor_sige" not in st.session_state:
        st.session_state["motor_sige"] = MotorSIGE(DATA_DIR)
    return st.session_state["motor_sige"]


def generar_qr_svg(texto_qr: str, size: int = 170) -> str:
    """Genera un código QR determinista en SVG limpio (sin requerir librerías externas de imagen)."""
    n = 21
    grid = [[0 for _ in range(n)] for _ in range(n)]

    def dibujar_finder(r0: int, c0: int) -> None:
        for r in range(7):
            for c in range(7):
                if r in (0, 6) or c in (0, 6) or (2 <= r <= 4 and 2 <= c <= 4):
                    grid[r0 + r][c0 + c] = 1

    dibujar_finder(0, 0)
    dibujar_finder(0, n - 7)
    dibujar_finder(n - 7, 0)

    semilla = sum((i + 1) * ord(ch) for i, ch in enumerate(texto_qr))
    for r in range(n):
        for c in range(n):
            if (r < 8 and c < 8) or (r < 8 and c >= n - 8) or (r >= n - 8 and c < 8):
                continue
            semilla = (semilla * 1103515245 + 12345) & 0x7FFFFFFF
            grid[r][c] = 1 if (semilla % 11) < 5 else 0

    celda = size / n
    rects = []
    for r in range(n):
        for c in range(n):
            if grid[r][c] == 1:
                x = c * celda
                y = r * celda
                rects.append(
                    f'<rect x="{x:.1f}" y="{y:.1f}" width="{celda + 0.4:.1f}" height="{celda + 0.4:.1f}" fill="#1e293b"/>'
                )
    svg = (
        f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" '
        f'style="background:#ffffff;padding:10px;border-radius:12px;border:2px solid #cbd5e1;">'
        + "".join(rects)
        + "</svg>"
    )
    return svg


# Estilos CSS inspirados en la Maqueta de la Figura 7.1 de la Solemne 1
st.markdown(
    """
    <style>
    .sige-header {
        background: linear-gradient(135deg, #1e293b 0%, #293548 100%);
        color: #ffffff;
        padding: 1.1rem 1.5rem;
        border-radius: 12px;
        margin-bottom: 1rem;
        border-left: 6px solid #4d9b86;
    }
    .sige-header h2 { margin: 0; font-size: 1.45rem; color: #ffffff; }
    .sige-header p { margin: 0.25rem 0 0 0; font-size: 0.9rem; color: #cbd5e1; }
    .maqueta-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 14px;
        padding: 1.2rem;
        box-shadow: 0 2px 6px rgba(15, 23, 42, 0.05);
        margin-bottom: 1rem;
    }
    .maqueta-title {
        background: #232d3b;
        color: #ffffff;
        padding: 0.55rem 0.9rem;
        border-radius: 8px;
        font-weight: 600;
        font-size: 0.95rem;
        text-align: center;
        margin-bottom: 0.9rem;
    }
    .spot-grid {
        display: grid;
        grid-template-columns: repeat(10, 1fr);
        gap: 6px;
        margin: 10px 0;
    }
    .spot-box {
        padding: 7px 4px;
        border-radius: 7px;
        text-align: center;
        font-size: 0.78rem;
        font-weight: 700;
        color: #ffffff;
        line-height: 1.15;
    }
    .spot-libre { background-color: #5ea867; }
    .spot-dueno { background-color: #88929b; }
    .spot-arrendado { background-color: #4180c4; }
    .spot-sobreestadia { background-color: #d64545; }
    .recambio-tag {
        display: inline-block;
        background: rgba(255,255,255,0.24);
        border-radius: 4px;
        padding: 1px 4px;
        font-size: 0.63rem;
        margin-top: 2px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

motor = obtener_motor()
kpis = motor.obtener_resumen_kpis()

# =============================================================================
# BARRA LATERAL: NAVEGACIÓN, ESTADO DEL BOT DE GOOGLE CLOUD Y DATOS DE PRUEBA
# =============================================================================
with st.sidebar:
    st.markdown("### 🅿️ **SIGE · Puerto Montt**")
    st.caption("Hito Evaluativo 2 · Implementación en Python")

    vista = st.radio(
        "Seleccionar Rol / Pantalla:",
        [
            "🏠 1. Mi Espacio · Propietario",
            "🚗 2. Reserva y QR · Cliente",
            "🛡️ 3. Monitor · Administración",
            "📊 4. Datos CSV y Bot Google",
        ],
    )

    st.divider()
    st.markdown("#### 🔄 **Cola de Prioridad y Recambio**")
    confirmados_tot = sum(1 for e in motor.estacionamientos if e.semana_confirmada)
    en_recambio_tot = kpis["en_recambio"]
    prioridad_alta_tot = max(0, confirmados_tot - en_recambio_tot)
    st.caption(
        f"• **Prioridad Principal (sin usar en ciclo):** `{prioridad_alta_tot}` lotes\n"
        f"• **En Cola de Recambio (ya usados):** `{en_recambio_tot}` lotes\n"
        f"• **Umbral activo (θ):** `{motor.theta:.2f}`"
    )

    st.divider()
    st.markdown("#### 🤖 **Estado Persistencia CSV / Bot**")
    if motor.persistencia.bot_google.conectado:
        st.success(f"🟢 {motor.persistencia.bot_google.ultimo_estado}")
    else:
        st.info("💾 CSV Local Activo (`data/*.csv`)\nListo para vincular Bot Google Cloud en pestaña 4.")

    if st.button("🔄 Restaurar Datos Semilla (Hito 1)", use_container_width=True):
        motor.persistencia.inicializar_si_no_existe(forzar_reinicio=True)
        motor.recargar()
        st.toast("Datos semilla del Hito 1 restaurados en CSV.", icon="✅")
        st.rerun()

# Encabezado superior con KPIs rápidos del edificio
st.markdown(
    f"""
    <div class="sige-header">
        <h2>🅿️ SIGE · Gestión Eficiente de Estacionamientos (Edificio Residencial Puerto Montt)</h2>
        <p>50 Estacionamientos (E01–E50) · Regla de oferta θ = {motor.theta:.2f} con margen 30/60 min · Tarifa Ley 20.967: $25/min ($1.500/h) · Reparto: 60% Dueño / 30% Comunidad / 5% Guardia / 5% Operación</p>
    </div>
    """,
    unsafe_allow_html=True,
)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("🟢 Libres Ofrecidos", f"{kpis['libres']} / 50")
c2.metric("🔵 Arrendados / En Uso", f"{kpis['arrendados']}")
c3.metric("🔄 En Pool de Recambio", f"{kpis['en_recambio']} lotes")
c4.metric("🔴 Alertas Sobreestadía", f"{kpis['sobreestadia']}")
c5.metric("💰 Recaudación Total", f"${kpis['ingreso_bruto']:,}")


# =============================================================================
# VISTA 1: PROPIETARIO (OBLIGATORIA: LIBERAR/BLOQUEAR + PROPIA: CONFIRMAR SEMANA MIXTA)
# =============================================================================
if vista.startswith("🏠"):
    st.subheader("🏠 Portal del Propietario — *Mi Espacio · Propietario*")
    st.caption(
        "Implementa **Funcionalidad Obligatoria** (Liberar y bloquear estacionamiento + Botón *'¡Llegué antes!'* con contingencia automática) "
        "y **Funcionalidad Propia (F1)** (Confirmar disponibilidad semanal mixta con 1 clic según umbral θ y margen de seguridad 30/60 min)."
    )

    opciones_est = [
        f"{e.id_estacionamiento} — {e.propietario} ({e.departamento}) · [{e.estado_actual}]"
        for e in motor.estacionamientos
    ]
    seleccion = st.selectbox("Selecciona tu Estacionamiento:", opciones_est, index=1)  # E02 por defecto (tiene reserva para probar contingencia)
    spot_id = seleccion.split(" — ")[0]
    est = motor.obtener_estacionamiento(spot_id)

    col_izq, col_der = st.columns([1.05, 1.15])

    with col_izq:
        st.markdown('<div class="maqueta-title">Mi Espacio · Propietario (Maqueta Hito 1)</div>', unsafe_allow_html=True)

        estado_cola = (
            "🔄 En Estacionamiento de Recambio (ya fue elegido en este ciclo)"
            if est.en_recambio
            else "⭐ Prioridad Principal Activa (listo para ser asignado)"
        )
        st.info(
            f"**Según tu rutina histórica ({est.horas_libres_dia_hist} h libres/día)**, tu estacionamiento "
            f"**{est.id_estacionamiento}** se sugiere disponible de lunes a viernes de "
            f"**{est.hora_inicio_ofrecida} a {est.hora_fin_ofrecida}**.\n\n"
            f"• **Perfil del propietario:** `{est.perfil_regularidad}` (Variación regreso: `{est.desviacion_regreso_h} h` → "
            f"**Margen de seguridad: {est.margen_seguridad_min} min**)\n"
            f"• **Índice de confiabilidad:** `{est.indice_confiabilidad:.1f}%` | **Veces usado:** `{est.veces_asignado}`\n"
            f"• **Estado en rotación:** {estado_cola}\n"
            f"• **Ingresos acumulados (60% Propietario - F3):** **${est.ingresos_acumulados:,}**"
        )

        # Barras visuales L M X J V como en la maqueta de la Figura 7.1
        dias_sem = ["L", "M", "X", "J", "V"]
        color_barra = "#4d9b86" if est.semana_confirmada and est.estado_actual != "BLOQUEADO" else "#94a3b8"
        cols_dias = st.columns(5)
        for i, d in enumerate(dias_sem):
            with cols_dias[i]:
                st.markdown(
                    f"""
                    <div style="text-align:center;font-weight:700;margin-bottom:4px;">{d}</div>
                    <div style="height:95px;background:{color_barra};border-radius:6px;display:flex;
                                align-items:center;justify-content:center;color:white;font-size:0.75rem;padding:4px;text-align:center;">
                        {est.hora_inicio_ofrecida}<br>a<br>{est.hora_fin_ofrecida}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        st.markdown("##### ✨ **Funcionalidad Propia del Propietario (F1): Disponibilidad Mixta**")
        nuevo_perfil = st.selectbox(
            "Ajustar condición de regularidad / margen de seguridad:",
            ["PUNTUAL", "IRREGULAR"],
            index=0 if est.perfil_regularidad == "PUNTUAL" else 1,
            help="Puntual (<1,5h variación): exige 30 min (1 bloque) de margen y permite reservas largas. Irregular (>=1,5h): exige 60 min (2 bloques) y reservas de máx. 2 horas.",
        )
        if st.button("✅ Confirmar semana sugerida con 1 clic (F1)", type="primary", use_container_width=True):
            ok, msg = motor.propietario_confirmar_semana_mixta(est.id_estacionamiento, nuevo_perfil=nuevo_perfil)
            if ok:
                st.success(msg)
            else:
                st.warning(msg)
            st.rerun()

    with col_der:
        st.markdown('<div class="maqueta-title">Funcionalidad Obligatoria: Liberar / Bloquear y Prioridad del Dueño</div>', unsafe_allow_html=True)

        # Mostrar reservas vigentes en este estacionamiento
        res_en_lote = [
            r for r in motor.reservas
            if r.id_estacionamiento == est.id_estacionamiento
            and r.estado in ("CONFIRMADA", "EN_CURSO", "SOBREESTADIA")
        ]
        if res_en_lote:
            for r in res_en_lote:
                st.warning(
                    f"📌 **Reserva vigente en {est.id_estacionamiento}:** `{r.id_reserva}` — Cliente: **{r.cliente}** "
                    f"({r.hora_inicio} a {r.hora_fin}) · Estado: `{r.estado}`.\n"
                    f"*(Si bloqueas este horario o presionas '¡Llegué antes!', el sistema reasignará automáticamente al cliente a un Estacionamiento de Recambio)*."
                )
        else:
            st.caption(f"Actualmente no hay reservas activas ocupando `{est.id_estacionamiento}`.")

        st.markdown("##### 🔓 **Opción A: Liberar estacionamiento**")
        if st.button("🟢 Liberar y habilitar mi estacionamiento ahora", use_container_width=True):
            ok, msg = motor.propietario_liberar_estacionamiento(est.id_estacionamiento, limpiar_bloqueos=True)
            st.success(msg)
            st.rerun()

        st.divider()
        st.markdown("##### 🔒 **Opción B: Bloquear tramo horario específico**")
        b_col1, b_col2 = st.columns(2)
        with b_col1:
            h_ini_bloq = st.selectbox("Hora inicio bloqueo:", BLOQUES_30_MIN, index=10, key="bloq_ini")
        with b_col2:
            h_fin_bloq = st.selectbox("Hora término bloqueo:", BLOQUES_30_MIN, index=16, key="bloq_fin")

        if st.button("🔒 Bloquear rango horario seleccionado", use_container_width=True):
            ok, msg = motor.propietario_bloquear_o_llegue_antes(
                spot_id=est.id_estacionamiento,
                fecha=motor.config.get("fecha_operacion_actual", "2026-08-28"),
                hora_inicio_bloqueo=h_ini_bloq,
                hora_fin_bloqueo=h_fin_bloq,
                es_emergencia_llegue_antes=False,
            )
            if ok:
                st.info(msg)
            else:
                st.error(msg)

        st.divider()
        st.markdown("##### 🚨 **Opción C: Botón de Emergencia «¡Llegué antes!» (F2 · Prioridad Absoluta)**")
        st.caption(
            "Regla RN01 de Solemne 1: El dueño nunca pierde su prioridad. Si vuelve antes, el sistema "
            "pasa la reserva vigente a un **Estacionamiento de Recambio** sin que el cliente pierda su cupo."
        )
        if st.button("🛑 ¡Llegué antes! Necesito mi espacio ahora (F2)", use_container_width=True):
            ok, msg = motor.propietario_bloquear_o_llegue_antes(
                spot_id=est.id_estacionamiento,
                fecha=motor.config.get("fecha_operacion_actual", "2026-08-28"),
                hora_inicio_bloqueo="06:00",
                hora_fin_bloqueo="23:30",
                es_emergencia_llegue_antes=True,
            )
            if ok:
                st.success(msg)
            else:
                st.error(msg)


# =============================================================================
# VISTA 2: CLIENTE (OBLIGATORIA: RESERVAR/CANCELAR + PROPIA: QR PORTERÍA Y LEY 20.967)
# =============================================================================
elif vista.startswith("🚗"):
    st.subheader("🚗 Portal del Cliente y Portería QR — *Reserva y Acceso QR*")
    st.caption(
        "Implementa **Funcionalidad Obligatoria (F4)** (Reservar sin elegir el espacio mediante el Motor Equitativo con Cola de Recambio, "
        "y cancelar/liberar anticipadamente) y **Funcionalidad Propia (F5 + F10)** (Check-in/Check-out con QR y cobro exacto por minuto Ley N° 20.967)."
    )

    col_res, col_qr = st.columns([1.05, 1.15])

    with col_res:
        st.markdown('<div class="maqueta-title">Reserva · Cliente (F4 · Asignación Ciega y Equitativa)</div>', unsafe_allow_html=True)
        st.markdown("##### **¿Cuándo necesitas estacionar?**")

        nom_cliente = st.text_input("Nombre del Cliente:", value="Carolina Mansilla (Visita Centro)")
        pat_cliente = st.text_input("Patente del Vehículo:", value="BCDF-91")
        c_h1, c_h2 = st.columns(2)
        with c_h1:
            h_llegada = st.selectbox("Hora de Llegada:", BLOQUES_30_MIN, index=8)   # 10:00
        with c_h2:
            h_salida = st.selectbox("Hora de Salida:", BLOQUES_30_MIN, index=12)    # 12:00

        dur_estimada = max(0, hora_a_minutos(h_salida) - hora_a_minutos(h_llegada))
        tarifa_estimada = dur_estimada * 25

        st.markdown(
            f"""
            <div style="background:#f8fafc;border:1px solid #cbd5e1;border-radius:10px;padding:12px;text-align:center;margin:10px 0;">
                <div style="font-size:1.1rem;font-weight:700;color:#1e293b;">
                    Tarifa estimada: ${tarifa_estimada:,} ({dur_estimada} min × $25/min)
                </div>
                <div style="font-size:0.82rem;color:#64748b;margin-top:4px;">
                    Ley N° 20.967: Cobro por minuto real de uso sin redondear hacia arriba.<br>
                    <b>El sistema te asigna un espacio automáticamente</b> priorizando a los propietarios con mayor disponibilidad y enviando los lotes ya usados a la <b>Cola de Recambio</b>.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Vista previa de candidatos que evalúa el motor
        candidatos_prev = motor.buscar_candidatos_ordenados(
            fecha=motor.config.get("fecha_operacion_actual", "2026-08-28"),
            hora_inicio=h_llegada,
            hora_fin=h_salida,
        )
        if dur_estimada > 0:
            if candidatos_prev:
                mejor_est, razon_mejor = candidatos_prev[0]
                st.caption(
                    f"🎯 **Disponibilidad verificada:** `{len(candidatos_prev)}` estacionamientos compatibles "
                    f"(con θ={motor.theta:.2f} + margen 30/60 min). Próximo en la cola equitativa: **{mejor_est.id_estacionamiento}** ({razon_mejor})."
                )
            else:
                st.caption("⚠️ Ningún estacionamiento cumple umbral θ + margen en ese rango horario.")

        if st.button("🟠 Reservar Espacio Ahora (F4)", type="primary", use_container_width=True):
            ok, msg, nueva_res = motor.cliente_crear_reserva(
                cliente=nom_cliente,
                patente=pat_cliente,
                fecha=motor.config.get("fecha_operacion_actual", "2026-08-28"),
                hora_inicio=h_llegada,
                hora_fin=h_salida,
            )
            if ok and nueva_res:
                st.session_state["ultima_reserva_id"] = nueva_res.id_reserva
                st.success(msg)
            else:
                st.error(msg)

        st.divider()
        st.markdown("##### 🛑 **Cancelar o Liberar Anticipadamente una Reserva (Obligatoria Cliente)**")
        res_activas_cli = [
            r for r in motor.reservas if r.estado in ("CONFIRMADA", "EN_CURSO")
        ]
        if res_activas_cli:
            op_cli = [
                f"{r.id_reserva} | {r.id_estacionamiento} | {r.cliente} ({r.hora_inicio}-{r.hora_fin}) [{r.estado}]"
                for r in res_activas_cli
            ]
            sel_res_cli = st.selectbox("Selecciona tu reserva vigente:", op_cli)
            id_sel_cli = sel_res_cli.split(" | ")[0]
            obj_res_cli = motor.obtener_reserva(id_sel_cli)

            col_c1, col_c2 = st.columns(2)
            with col_c1:
                if st.button("❌ Cancelar Reserva (Antes de entrar)", use_container_width=True):
                    ok, msg = motor.cliente_cancelar_o_liberar_reserva(id_sel_cli, minutos_usados_si_anticipada=None)
                    if ok:
                        st.success(msg)
                    else:
                        st.warning(msg)
            with col_c2:
                min_ant = st.number_input(
                    "Minutos usados al salir antes:",
                    min_value=5,
                    max_value=max(10, obj_res_cli.duracion_reservada_min),
                    value=max(15, obj_res_cli.duracion_reservada_min // 2),
                    step=5,
                )
                if st.button("⏱️ Liberar Anticipadamente (Cobro real)", use_container_width=True):
                    ok, msg = motor.cliente_cancelar_o_liberar_reserva(
                        id_sel_cli, minutos_usados_si_anticipada=int(min_ant)
                    )
                    if ok:
                        st.success(msg)
                    else:
                        st.warning(msg)
        else:
            st.info("No hay reservas en estado CONFIRMADA o EN_CURSO para cancelar/liberar.")

    with col_qr:
        st.markdown('<div class="maqueta-title">Acceso · Cliente y Portería QR (F5 + F10 · Ley 20.967)</div>', unsafe_allow_html=True)

        todas_res = list(reversed(motor.reservas))
        opciones_qr = [
            f"{r.id_reserva} — {r.codigo_qr} ({r.cliente} · Lote {r.id_estacionamiento} · {r.estado})"
            for r in todas_res
        ]
        idx_def = 0
        if "ultima_reserva_id" in st.session_state:
            for i, r in enumerate(todas_res):
                if r.id_reserva == st.session_state["ultima_reserva_id"]:
                    idx_def = i
                    break

        sel_qr = st.selectbox("Seleccionar Pase QR de Reserva:", opciones_qr, index=idx_def)
        res_qr_id = sel_qr.split(" — ")[0]
        res_qr = motor.obtener_reserva(res_qr_id)

        if res_qr:
            svg_qr = generar_qr_svg(res_qr.codigo_qr, size=165)
            st.markdown(
                f"""
                <div style="background:#ffffff;border:1px solid #cbd5e1;border-radius:12px;padding:16px;text-align:center;">
                    <div style="font-weight:700;font-size:1.05rem;color:#1e293b;margin-bottom:8px;">
                        Reserva {res_qr.id_reserva} · Estado: {res_qr.estado}
                    </div>
                    <div style="display:flex;justify-content:center;margin:8px 0;">{svg_qr}</div>
                    <div style="font-family:monospace;font-weight:700;color:#0f172a;background:#f1f5f9;padding:4px 10px;border-radius:6px;display:inline-block;">
                        {res_qr.codigo_qr}
                    </div>
                    <div style="font-size:0.86rem;color:#475569;margin-top:8px;">
                        Muestra este código en portería · Estacionamiento asignado: <b>{res_qr.id_estacionamiento}</b> ({res_qr.propietario})<br>
                        Horario reservado: <b>{res_qr.hora_inicio} — {res_qr.hora_fin}</b> ({res_qr.duracion_reservada_min} min)
                    </div>
                    <div style="font-size:0.78rem;color:#0284c7;margin-top:6px;">
                        <b>Trazabilidad de Selección:</b> {res_qr.criterio_asignacion}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown("##### 🛂 **Control de Acceso en Portería (Guardia / Cliente — F5 y F10)**")
            q_col1, q_col2 = st.columns(2)
            with q_col1:
                if st.button("📲 1. Escanear QR al Entrar (Check-in)", use_container_width=True):
                    ok, msg = motor.cliente_procesar_qr_porteria(res_qr.codigo_qr, accion="CHECK_IN")
                    if ok:
                        st.success(msg)
                    else:
                        st.warning(msg)

            with q_col2:
                min_reales_out = st.number_input(
                    "Minutos reales de estadía (Check-out):",
                    min_value=1,
                    max_value=600,
                    value=int(res_qr.duracion_reservada_min),
                    step=5,
                    help="Si es menor o igual a lo reservado, cobra $25/min exactos (Ley 20.967). Si supera lo reservado, cobra recargo x5 ($125/min) por el exceso.",
                )
                if st.button("🏁 2. Escanear QR al Salir (Check-out y Cobro)", type="primary", use_container_width=True):
                    ok, msg = motor.cliente_procesar_qr_porteria(
                        res_qr.codigo_qr, accion="CHECK_OUT", minutos_reales=int(min_reales_out)
                    )
                    if ok:
                        st.success(msg)
                    else:
                        st.warning(msg)


# =============================================================================
# VISTA 3: ADMINISTRACIÓN (OBLIGATORIA: ASIGNAR/REASIGNAR + PROPIA: CONTINGENCIAS Y UMBRAL θ)
# =============================================================================
elif vista.startswith("🛡️"):
    st.subheader("🛡️ Monitor de Administración — *Control en Vivo, Reasignación y Regla de Oferta*")
    st.caption(
        "Implementa **Mapa de Ocupación en Vivo (F6)**, **Funcionalidad Obligatoria (F9)** (Asignar y reasignar estacionamientos "
        "verificando disponibilidad y usando el Pool de Recambio) y **Funcionalidad Propia (F7 + F8)** (Gestión de sobreestadía ×5 y calibración del umbral θ)."
    )

    # 1. MAPA DE OCUPACIÓN EN VIVO DE LOS 50 ESTACIONAMIENTOS (MAQUETA FIG. 7.1)
    st.markdown('<div class="maqueta-title">Monitor · Administración — Mapa de Ocupación en Vivo (50 Estacionamientos E01–E50)</div>', unsafe_allow_html=True)

    celdas_html = []
    for e in motor.estacionamientos:
        if e.estado_actual == "LIBRE":
            clase = "spot-libre"
            etiqueta = "Libre"
        elif e.estado_actual == "ARRENDADO":
            clase = "spot-arrendado"
            etiqueta = "Arrendado"
        elif e.estado_actual == "SOBREESTADIA":
            clase = "spot-sobreestadia"
            etiqueta = "Sobreestadía"
        else:
            clase = "spot-dueno"
            etiqueta = "Dueño/Bloq"

        badge_rec = '<div class="recambio-tag">🔄 Recambio</div>' if e.en_recambio else '<div class="recambio-tag">⭐ Prioritario</div>'
        celdas_html.append(
            f'<div class="spot-box {clase}" title="{e.id_estacionamiento} ({e.propietario}) - {e.horas_libres_dia_hist}h/día - Margen {e.margen_seguridad_min}m">'
            f'{e.id_estacionamiento}<br><span style="font-weight:400;font-size:0.68rem;">{etiqueta}</span><br>{badge_rec}'
            f'</div>'
        )

    st.markdown(
        '<div class="spot-grid">' + "".join(celdas_html) + "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div style="display:flex;gap:18px;justify-content:center;font-size:0.85rem;margin-top:6px;margin-bottom:14px;">
            <span>🟢 <b>Libre ofrecido:</b> {kpis['libres']}</span>
            <span>⚪ <b>Dueño en casa / Bloqueado:</b> {kpis['dueno_o_bloq']}</span>
            <span>🔵 <b>Arrendado:</b> {kpis['arrendados']}</span>
            <span>🔴 <b>Sobreestadía (Alerta):</b> {kpis['sobreestadia']}</span>
            <span>🔄 <b>En Cola de Recambio:</b> {kpis['en_recambio']}</span>
            <span>💰 <b>Aporte Comunidad (30%):</b> ${kpis['aporte_comunidad']:,}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_adm1, col_adm2 = st.columns(2)

    with col_adm1:
        st.markdown("#### 🔀 **Funcionalidad Obligatoria Admin (F9): Asignar y Reasignar Estacionamientos**")
        res_reasignables = [
            r for r in motor.reservas if r.estado in ("CONFIRMADA", "EN_CURSO", "SOBREESTADIA")
        ]
        if res_reasignables:
            op_r = [
                f"{r.id_reserva} | Lote actual: {r.id_estacionamiento} | {r.cliente} ({r.hora_inicio}-{r.hora_fin}) [{r.estado}]"
                for r in res_reasignables
            ]
            sel_r_adm = st.selectbox("1. Seleccionar Reserva Activa a Reasignar:", op_r)
            id_res_adm = sel_r_adm.split(" | ")[0]
            res_obj_adm = motor.obtener_reserva(id_res_adm)

            # Mostrar cuáles son compatibles y cuáles están en el Pool de Recambio
            compatibles_adm = motor.buscar_candidatos_ordenados(
                fecha=res_obj_adm.fecha,
                hora_inicio=res_obj_adm.hora_inicio,
                hora_fin=res_obj_adm.hora_fin,
                ignorar_reserva_id=res_obj_adm.id_reserva,
                excluir_estacionamientos=[res_obj_adm.id_estacionamiento],
                preferir_pool_recambio=True,
            )
            ids_comp = {e.id_estacionamiento for e, _ in compatibles_adm}

            op_destinos = []
            for e in motor.estacionamientos:
                if e.id_estacionamiento == res_obj_adm.id_estacionamiento:
                    continue
                tag_comp = "✅ Compatible" if e.id_estacionamiento in ids_comp else "❌ Conflicto/No disponible"
                tag_rec = "🔄 Pool Recambio" if e.en_recambio else "⭐ Prioridad Normal"
                op_destinos.append(
                    f"{e.id_estacionamiento} — {e.propietario} ({tag_rec} · {tag_comp} · Estado: {e.estado_actual})"
                )

            sel_dest = st.selectbox(
                "2. Seleccionar Estacionamiento de Destino (permite probar tanto reasignación válida como rechazo por conflicto):",
                op_destinos,
            )
            nuevo_spot_id = sel_dest.split(" — ")[0]
            motivo_adm = st.text_input(
                "Motivo de la reasignación:",
                value="Contingencia operativa / Reubicación a estacionamiento de recambio",
            )

            if st.button("🔀 Ejecutar Reasignación de Estacionamiento (F9)", type="primary", use_container_width=True):
                ok, msg = motor.admin_reasignar_reserva(id_res_adm, nuevo_spot_id, motivo=motivo_adm)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
        else:
            st.info("No hay reservas activas en este momento para reasignar.")

        st.divider()
        st.markdown("#### 🔄 **Gestión del Pool de Rotación y Recambio**")
        st.caption(
            "Los propietarios cuyos estacionamientos ya fueron elegidos pasan a `en_recambio = True` "
            "(baja prioridad) para que todos los estacionamientos se ocupen equitativamente premiando la disponibilidad."
        )
        if st.button("🔄 Reiniciar Ciclo de Cola de Recambio (Todos a Prioridad Principal)", use_container_width=True):
            ok, msg = motor.admin_reiniciar_ciclo_recambio()
            st.success(msg)
            st.rerun()

    with col_adm2:
        st.markdown("#### 🚨 **Funcionalidad Propia Admin (F7 + F8): Alertas de Exceso (×5) y Motor θ**")

        st.markdown("##### **A. Gestión de Exceso de Tiempo / Sobreestadía (Tarifa ×5 = $125/min)**")
        res_para_alerta = [
            r for r in motor.reservas if r.estado in ("EN_CURSO", "SOBREESTADIA", "CONFIRMADA")
        ]
        if res_para_alerta:
            op_al = [
                f"{r.id_reserva} | {r.id_estacionamiento} | {r.cliente} (Fin: {r.hora_fin} · Exceso actual: {r.minutos_sobreestadia}m) [{r.estado}]"
                for r in res_para_alerta
            ]
            sel_al = st.selectbox("Seleccionar reserva con exceso de tiempo:", op_al)
            id_al = sel_al.split(" | ")[0]
            min_exc = st.slider("Minutos de exceso sobre la hora de salida:", 5, 120, 25, step=5)
            c_al1, c_al2 = st.columns(2)
            with c_al1:
                if st.button("🚨 Declarar Alerta Sobreestadía (×5)", use_container_width=True):
                    ok, msg = motor.admin_declarar_o_resolver_sobreestadia(
                        id_al, minutos_exceso=min_exc, finalizar_ahora=False
                    )
                    st.warning(msg)
            with c_al2:
                if st.button("💳 Liquidar Multa ×5 y Liberar Lote", use_container_width=True):
                    ok, msg = motor.admin_declarar_o_resolver_sobreestadia(
                        id_al, minutos_exceso=min_exc, finalizar_ahora=True
                    )
                    st.success(msg)

        st.divider()
        st.markdown("##### **B. Calibración del Motor de Disponibilidad (Umbral θ · Tabla 5.1 Solemne 1)**")
        opciones_theta = [0.60, 0.70, 0.80, 0.90, 0.95]
        idx_th = opciones_theta.index(motor.theta) if motor.theta in opciones_theta else 2
        nuevo_th = st.select_slider(
            "Seleccionar Umbral θ de probabilidad histórica exigida:",
            options=opciones_theta,
            value=opciones_theta[idx_th],
        )
        info_t51 = TABLA_5_1_UMBRALES.get(f"{nuevo_th:.2f}", TABLA_5_1_UMBRALES["0.80"])
        st.caption(
            f"📊 **Impacto según Tabla 5.1 (Solemne 1):** Con **θ = {nuevo_th:.2f}** → "
            f"Bloques ofrecidos (4 sem): **{info_t51['bloques_ofrecidos']:,}** | "
            f"Ingreso posible: **${info_t51['ingreso_posible']:,}** | "
            f"Riesgo (reserva 2h): **{info_t51['riesgo_2h']}**."
        )
        if st.button("⚙️ Aplicar Nuevo Umbral θ a los 50 Estacionamientos (F8)", use_container_width=True):
            ok, msg = motor.admin_actualizar_umbral_theta(float(nuevo_th))
            st.success(msg)


# =============================================================================
# VISTA 4: DATOS CSV (ENTREGA 3) Y BOT DE GOOGLE CLOUD (SERVICE ACCOUNT + SHEETS)
# =============================================================================
elif vista.startswith("📊"):
    st.subheader("📊 Persistencia en CSV (Preparación Entrega 3) y Bot de Google Cloud")
    st.caption(
        "Cumple con **RT03 (Persistencia)** y **RT04 (Datos estructurados en CSV para el Dashboard de la Entrega 3)**, "
        "además de sincronización en la nube mediante un **Bot de Cuenta de Servicio de Google Cloud (Google Sheets API)**."
    )

    tab_csv, tab_bot, tab_hito1 = st.tabs([
        "📁 1. Tablas CSV Operacionales e Historial",
        "🤖 2. Configurar Bot de Google Cloud (Google Sheets)",
        "📈 3. Dataset Real Hito 1 (720 registros y Curva Grado 4)",
    ])

    with tab_csv:
        st.markdown("#### **1. Registro Histórico de Eventos (`data/historial_eventos.csv`)**")
        st.caption("Registra creación, check-in, check-out, cancelación, liberación anticipada, bloqueos y reasignaciones con fecha y hora.")
        df_evt = pd.read_csv(motor.persistencia.evt_csv)
        st.dataframe(df_evt, use_container_width=True, height=230)
        with open(motor.persistencia.evt_csv, "rb") as f:
            st.download_button(
                "⬇️ Descargar historial_eventos.csv",
                data=f,
                file_name="historial_eventos.csv",
                mime="text/csv",
            )

        st.markdown("#### **2. Registro de Reservas y Reparto 60/30/5/5 (`data/reservas.csv`)**")
        df_res = pd.read_csv(motor.persistencia.res_csv)
        st.dataframe(df_res, use_container_width=True, height=220)
        with open(motor.persistencia.res_csv, "rb") as f:
            st.download_button(
                "⬇️ Descargar reservas.csv",
                data=f,
                file_name="reservas.csv",
                mime="text/csv",
            )

        st.markdown("#### **3. Estado de los 50 Estacionamientos y Cola de Recambio (`data/estacionamientos.csv`)**")
        df_est = pd.read_csv(motor.persistencia.est_csv)
        st.dataframe(df_est, use_container_width=True, height=250)
        with open(motor.persistencia.est_csv, "rb") as f:
            st.download_button(
                "⬇️ Descargar estacionamientos.csv",
                data=f,
                file_name="estacionamientos.csv",
                mime="text/csv",
            )

    with tab_bot:
        st.markdown("#### 🤖 **Gestor de Persistencia en la Nube con Bot de Google Cloud (`Service Account`)**")
        st.write(
            "Para que al hostear la aplicación en **GitHub + Streamlit Community Cloud** los archivos CSV no se pierdan "
            "cuando el contenedor se reinicie, este módulo conecta un **Bot de Cuenta de Servicio de Google (`gspread`)** "
            "que respalda y restaura automáticamente los CSV en una Hoja de Cálculo de Google (**Google Sheets**)."
        )

        bot = motor.persistencia.bot_google
        if bot.conectado:
            st.success(f"✅ **Bot Conectado:** `{bot.bot_email}` | **Hoja vinculada:** `{bot.sheet_url}`")
            b_c1, b_c2, b_c3 = st.columns(3)
            with b_c1:
                if st.button("☁️ Subir CSV Locales -> Google Sheets ahora", type="primary", use_container_width=True):
                    ok, msg = bot.sincronizar_csv_a_sheets(motor.persistencia.ARCHIVOS_OPERACIONALES)
                    if ok:
                        st.success(msg)
                    else:
                        st.warning(msg)
            with b_c2:
                if st.button("📥 Restaurar Google Sheets -> CSV Locales", use_container_width=True):
                    ok, msg = bot.restaurar_sheets_a_csv(motor.persistencia.ARCHIVOS_OPERACIONALES)
                    if ok:
                        motor.recargar()
                        st.success(msg)
                    else:
                        st.warning(msg)
            with b_c3:
                if st.button("🔌 Desvincular Bot (Usar solo CSV local)", use_container_width=True):
                    bot.desconectar_bot()
                    st.rerun()
        else:
            st.info(
                "Actualmente funcionando en **Modo CSV Local (`data/*.csv`)**. "
                "Puedes vincular tu Bot de Google Cloud pegando su JSON de credenciales abajo o mediante `st.secrets` en Streamlit Cloud."
            )

        with st.expander("⚙️ Configurar / Vincular Credenciales del Bot de Google Cloud", expanded=not bot.conectado):
            st.markdown(
                """
                **Pasos rápidos para conectar tu Bot de Google:**
                1. En Google Cloud Console habilita **Google Sheets API** y **Google Drive API**, y crea una **Cuenta de Servicio (Service Account)** descargando su clave en formato `.json`.
                2. Crea un archivo en **Google Sheets** y compártelo (como *Editor*) con el correo `client_email` de tu bot (`...@...iam.gserviceaccount.com`).
                3. Pega el contenido del `.json` y el enlace de tu Google Sheet aquí abajo (o en `Settings -> Secrets` de Streamlit Cloud).
                """
            )
            sheet_url_in = st.text_input(
                "URL o ID de tu Google Sheet:",
                value=bot.sheet_url,
                placeholder="https://docs.google.com/spreadsheets/d/1abc.../edit",
            )
            creds_json_in = st.text_area(
                "Contenido JSON de la Cuenta de Servicio (Service Account):",
                height=160,
                placeholder='{\n  "type": "service_account",\n  "project_id": "...",\n  "private_key": "...",\n  "client_email": "bot-sige@proyecto.iam.gserviceaccount.com"\n}',
            )
            if st.button("🔗 Guardar y Conectar Bot de Google Cloud", type="primary"):
                ok, msg = bot.configurar_bot(creds_json_in, sheet_url_in)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    with tab_hito1:
        st.markdown("#### 📈 **Dataset Original de la Solemne 1 (`data/dataset_historico_hito1.csv` — 720 registros, 15.289 bloques libres)**")
        ruta_hist = os.path.join(DATA_DIR, "dataset_historico_hito1.csv")
        ruta_prob = os.path.join(DATA_DIR, "probabilidades_bloques.csv")
        if os.path.exists(ruta_prob):
            df_prob = pd.read_csv(ruta_prob)
            st.markdown("**Tabla B.1 reproducida: Promedio de libres por bloque (30 min), Curva Polinomial Grado 4 y Probabilidad por Estacionamiento:**")
            st.dataframe(df_prob[["Hora", "Promedio_Libres_50", "Curva_Grado_4", "E18", "E05", "E02", "E16", "E33"]], use_container_width=True, height=240)
        if os.path.exists(ruta_hist):
            df_hist = pd.read_csv(ruta_hist)
            st.markdown("**Matriz completa de los 20 días hábiles (3 al 28 de agosto de 2026 · 50 estacionamientos E01–E50):**")
            st.dataframe(df_hist, use_container_width=True, height=240)
