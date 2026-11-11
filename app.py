from __future__ import annotations
import os
import pandas as pd
import streamlit as st

from core.engine import (
    MotorSIGE,
    BLOQUES_30_MIN,
    hora_a_minutos,
)

st.set_page_config(
    page_title="SIGE - Hito 2",
    layout="wide",
)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def obtener_motor() -> MotorSIGE:
    if "motor_sige" not in st.session_state:
        st.session_state["motor_sige"] = MotorSIGE(DATA_DIR)
    return st.session_state["motor_sige"]


def generar_qr_svg(texto_qr: str, size: int = 150) -> str:
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
                    f'<rect x="{x:.1f}" y="{y:.1f}" width="{celda + 0.4:.1f}" height="{celda + 0.4:.1f}" fill="#000000"/>'
                )
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" '
        f'style="background:#ffffff;padding:8px;border:1px solid #000000;">'
        + "".join(rects)
        + "</svg>"
    )


motor = obtener_motor()
kpis = motor.obtener_resumen_kpis()

st.title("Sistema de Gestion de Estacionamientos (Hito 2)")

tab_prop, tab_cli, tab_adm, tab_datos = st.tabs([
    "Propietario",
    "Cliente",
    "Administrador",
    "Datos CSV y Bot Google",
])

# =============================================================================
# PESTANA 1: PROPIETARIO
# =============================================================================
with tab_prop:
    opciones_est = [
        f"{e.id_estacionamiento} - {e.propietario} ({e.departamento}) [{e.estado_actual}]"
        for e in motor.estacionamientos
    ]
    seleccion_prop = st.selectbox("Estacionamiento", opciones_est, index=1, key="sel_est_prop")
    spot_id_prop = seleccion_prop.split(" - ")[0]
    est = motor.obtener_estacionamiento(spot_id_prop)

    p_col1, p_col2, p_col3, p_col4, p_col5 = st.columns(5)
    p_col1.metric("Estado", est.estado_actual)
    p_col2.metric("Horario Ofrecido", f"{est.hora_inicio_ofrecida} - {est.hora_fin_ofrecida}")
    p_col3.metric("Perfil / Margen", f"{est.perfil_regularidad} ({est.margen_seguridad_min}m)")
    p_col4.metric("Cola Rotacion", "En Recambio" if est.en_recambio else "Prioridad Principal")
    p_col5.metric("Ingresos Acumulados", f"${est.ingresos_acumulados:,}")

    sub_prop1, sub_prop2, sub_prop3 = st.tabs([
        "Liberar o Bloquear",
        "Emergencia Llegue Antes",
        "Confirmar Semana y Perfil",
    ])

    with sub_prop1:
        if st.button("Liberar estacionamiento", key="btn_liberar_prop"):
            ok, msg = motor.propietario_liberar_estacionamiento(est.id_estacionamiento, limpiar_bloqueos=True)
            if ok:
                st.success(msg)
            else:
                st.error(msg)

        st.divider()

        b_col1, b_col2 = st.columns(2)
        with b_col1:
            h_ini_bloq = st.selectbox("Hora inicio bloqueo", BLOQUES_30_MIN, index=10, key="bloq_ini")
        with b_col2:
            h_fin_bloq = st.selectbox("Hora termino bloqueo", BLOQUES_30_MIN, index=16, key="bloq_fin")

        if st.button("Bloquear rango horario", key="btn_bloq_prop"):
            ok, msg = motor.propietario_bloquear_o_llegue_antes(
                spot_id=est.id_estacionamiento,
                fecha=motor.config.get("fecha_operacion_actual", "2026-08-28"),
                hora_inicio_bloqueo=h_ini_bloq,
                hora_fin_bloqueo=h_fin_bloq,
                es_emergencia_llegue_antes=False,
            )
            if ok:
                st.success(msg)
            else:
                st.error(msg)

    with sub_prop2:
        res_en_lote = [
            r for r in motor.reservas
            if r.id_estacionamiento == est.id_estacionamiento
            and r.estado in ("CONFIRMADA", "EN_CURSO", "SOBREESTADIA")
        ]
        if res_en_lote:
            st.dataframe(pd.DataFrame([r.to_dict() for r in res_en_lote]), use_container_width=True)
        else:
            st.write("Sin reservas activas en este estacionamiento.")

        if st.button("Llegue antes (Reclamar mi estacionamiento ahora)", key="btn_llegue_antes"):
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

    with sub_prop3:
        nuevo_perfil = st.selectbox(
            "Perfil de regularidad",
            ["PUNTUAL", "IRREGULAR"],
            index=0 if est.perfil_regularidad == "PUNTUAL" else 1,
            key="sel_perfil_prop",
        )
        if st.button("Confirmar disponibilidad semanal", key="btn_conf_sem"):
            ok, msg = motor.propietario_confirmar_semana_mixta(est.id_estacionamiento, nuevo_perfil=nuevo_perfil)
            if ok:
                st.success(msg)
            else:
                st.warning(msg)

# =============================================================================
# PESTANA 2: CLIENTE
# =============================================================================
with tab_cli:
    sub_cli1, sub_cli2, sub_cli3 = st.tabs([
        "Reservar Estacionamiento",
        "Cancelar o Liberar Reserva",
        "Acceso QR Porteria",
    ])

    with sub_cli1:
        nom_cliente = st.text_input("Nombre del cliente", value="Carolina Mansilla")
        pat_cliente = st.text_input("Patente", value="BCDF-91")
        c_h1, c_h2 = st.columns(2)
        with c_h1:
            h_llegada = st.selectbox("Hora de llegada", BLOQUES_30_MIN, index=8, key="cli_llegada")
        with c_h2:
            h_salida = st.selectbox("Hora de salida", BLOQUES_30_MIN, index=12, key="cli_salida")

        dur_estimada = max(0, hora_a_minutos(h_salida) - hora_a_minutos(h_llegada))
        tarifa_estimada = dur_estimada * 25
        st.write(f"Duracion: {dur_estimada} min | Tarifa estimada: ${tarifa_estimada:,} ($25/min)")

        if st.button("Reservar", key="btn_reservar_cli"):
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

    with sub_cli2:
        res_activas_cli = [
            r for r in motor.reservas if r.estado in ("CONFIRMADA", "EN_CURSO")
        ]
        if res_activas_cli:
            op_cli = [
                f"{r.id_reserva} | {r.id_estacionamiento} | {r.cliente} ({r.hora_inicio}-{r.hora_fin}) [{r.estado}]"
                for r in res_activas_cli
            ]
            sel_res_cli = st.selectbox("Reserva activa", op_cli, key="sel_res_cancel")
            id_sel_cli = sel_res_cli.split(" | ")[0]
            obj_res_cli = motor.obtener_reserva(id_sel_cli)

            col_c1, col_c2 = st.columns(2)
            with col_c1:
                if st.button("Cancelar reserva", key="btn_cancel_cli"):
                    ok, msg = motor.cliente_cancelar_o_liberar_reserva(
                        id_sel_cli, minutos_usados_si_anticipada=None
                    )
                    if ok:
                        st.success(msg)
                    else:
                        st.warning(msg)
            with col_c2:
                min_ant = st.number_input(
                    "Minutos utilizados",
                    min_value=5,
                    max_value=max(10, obj_res_cli.duracion_reservada_min),
                    value=max(15, obj_res_cli.duracion_reservada_min // 2),
                    step=5,
                    key="num_min_ant",
                )
                if st.button("Liberar anticipadamente", key="btn_lib_ant_cli"):
                    ok, msg = motor.cliente_cancelar_o_liberar_reserva(
                        id_sel_cli, minutos_usados_si_anticipada=int(min_ant)
                    )
                    if ok:
                        st.success(msg)
                    else:
                        st.warning(msg)
        else:
            st.write("No hay reservas activas.")

    with sub_cli3:
        todas_res = list(reversed(motor.reservas))
        opciones_qr = [
            f"{r.id_reserva} - {r.codigo_qr} ({r.cliente} | {r.id_estacionamiento} | {r.estado})"
            for r in todas_res
        ]
        idx_def = 0
        if "ultima_reserva_id" in st.session_state:
            for i, r in enumerate(todas_res):
                if r.id_reserva == st.session_state["ultima_reserva_id"]:
                    idx_def = i
                    break

        sel_qr = st.selectbox("Reserva / Codigo QR", opciones_qr, index=idx_def, key="sel_qr_cli")
        res_qr_id = sel_qr.split(" - ")[0]
        res_qr = motor.obtener_reserva(res_qr_id)

        if res_qr:
            q_info_col, q_act_col = st.columns([1, 2])
            with q_info_col:
                st.markdown(generar_qr_svg(res_qr.codigo_qr, size=140), unsafe_allow_html=True)
                st.write(f"Codigo: `{res_qr.codigo_qr}`")
                st.write(f"Estacionamiento: `{res_qr.id_estacionamiento}`")
                st.write(f"Horario: `{res_qr.hora_inicio} - {res_qr.hora_fin}`")
                st.write(f"Estado: `{res_qr.estado}`")

            with q_act_col:
                if st.button("Check-in (Entrada)", key="btn_checkin"):
                    ok, msg = motor.cliente_procesar_qr_porteria(res_qr.codigo_qr, accion="CHECK_IN")
                    if ok:
                        st.success(msg)
                    else:
                        st.warning(msg)

                st.divider()

                min_reales_out = st.number_input(
                    "Minutos reales de estadia",
                    min_value=1,
                    max_value=600,
                    value=int(res_qr.duracion_reservada_min),
                    step=5,
                    key="num_min_out",
                )
                if st.button("Check-out (Salida y Cobro)", key="btn_checkout"):
                    ok, msg = motor.cliente_procesar_qr_porteria(
                        res_qr.codigo_qr, accion="CHECK_OUT", minutos_reales=int(min_reales_out)
                    )
                    if ok:
                        st.success(msg)
                    else:
                        st.warning(msg)

# =============================================================================
# PESTANA 3: ADMINISTRADOR
# =============================================================================
with tab_adm:
    sub_adm1, sub_adm2, sub_adm3, sub_adm4 = st.tabs([
        "Mapa de Ocupacion",
        "Asignar y Reasignar",
        "Sobreestadia",
        "Umbral Theta y Recambio",
    ])

    with sub_adm1:
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Libres", f"{kpis['libres']} / 50")
        m2.metric("Arrendados", f"{kpis['arrendados']}")
        m3.metric("En Recambio", f"{kpis['en_recambio']}")
        m4.metric("Sobreestadia", f"{kpis['sobreestadia']}")
        m5.metric("Recaudacion Total", f"${kpis['ingreso_bruto']:,}")

        celdas = []
        for e in motor.estacionamientos:
            rec_txt = "RECAMBIO" if e.en_recambio else "NORMAL"
            celdas.append(
                f'<div style="border:1px solid #888;padding:4px;font-size:11px;text-align:center;">'
                f'<b>{e.id_estacionamiento}</b><br>{e.estado_actual}<br>{rec_txt}</div>'
            )
        st.markdown(
            '<div style="display:grid;grid-template-columns:repeat(10,1fr);gap:4px;margin:10px 0;">'
            + "".join(celdas)
            + "</div>",
            unsafe_allow_html=True,
        )

        df_ocupacion = pd.DataFrame([e.to_dict() for e in motor.estacionamientos])
        st.dataframe(df_ocupacion, use_container_width=True, height=350)

    with sub_adm2:
        res_reasignables = [
            r for r in motor.reservas if r.estado in ("CONFIRMADA", "EN_CURSO", "SOBREESTADIA")
        ]
        if res_reasignables:
            op_r = [
                f"{r.id_reserva} | Lote: {r.id_estacionamiento} | {r.cliente} ({r.hora_inicio}-{r.hora_fin}) [{r.estado}]"
                for r in res_reasignables
            ]
            sel_r_adm = st.selectbox("Reserva a reasignar", op_r, key="sel_res_adm")
            id_res_adm = sel_r_adm.split(" | ")[0]
            res_obj_adm = motor.obtener_reserva(id_res_adm)

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
                tag_comp = "Compatible" if e.id_estacionamiento in ids_comp else "Conflicto/No disponible"
                tag_rec = "Recambio" if e.en_recambio else "Prioridad Principal"
                op_destinos.append(
                    f"{e.id_estacionamiento} - {e.propietario} [{tag_rec} | {tag_comp} | {e.estado_actual}]"
                )

            sel_dest = st.selectbox("Estacionamiento destino", op_destinos, key="sel_dest_adm")
            nuevo_spot_id = sel_dest.split(" - ")[0]
            motivo_adm = st.text_input("Motivo", value="Reubicacion operativa", key="txt_motivo_adm")

            if st.button("Reasignar estacionamiento", key="btn_reasignar_adm"):
                ok, msg = motor.admin_reasignar_reserva(id_res_adm, nuevo_spot_id, motivo=motivo_adm)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
        else:
            st.write("No hay reservas activas para reasignar.")

    with sub_adm3:
        res_para_alerta = [
            r for r in motor.reservas if r.estado in ("EN_CURSO", "SOBREESTADIA", "CONFIRMADA")
        ]
        if res_para_alerta:
            op_al = [
                f"{r.id_reserva} | {r.id_estacionamiento} | {r.cliente} (Fin: {r.hora_fin} | Exceso: {r.minutos_sobreestadia}m) [{r.estado}]"
                for r in res_para_alerta
            ]
            sel_al = st.selectbox("Reserva", op_al, key="sel_alerta_adm")
            id_al = sel_al.split(" | ")[0]
            min_exc = st.number_input("Minutos de exceso", min_value=5, max_value=240, value=25, step=5, key="num_exc_adm")

            c_al1, c_al2 = st.columns(2)
            with c_al1:
                if st.button("Declarar sobreestadia", key="btn_decl_sobre"):
                    ok, msg = motor.admin_declarar_o_resolver_sobreestadia(
                        id_al, minutos_exceso=int(min_exc), finalizar_ahora=False
                    )
                    if ok:
                        st.warning(msg)
                    else:
                        st.error(msg)
            with c_al2:
                if st.button("Liquidar sobreestadia y liberar", key="btn_liq_sobre"):
                    ok, msg = motor.admin_declarar_o_resolver_sobreestadia(
                        id_al, minutos_exceso=int(min_exc), finalizar_ahora=True
                    )
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)
        else:
            st.write("No hay reservas disponibles.")

    with sub_adm4:
        opciones_theta = [0.60, 0.70, 0.80, 0.90, 0.95]
        idx_th = opciones_theta.index(motor.theta) if motor.theta in opciones_theta else 2
        nuevo_th = st.select_slider(
            "Umbral theta",
            options=opciones_theta,
            value=opciones_theta[idx_th],
            key="slider_theta_adm",
        )
        if st.button("Aplicar umbral theta", key="btn_theta_adm"):
            ok, msg = motor.admin_actualizar_umbral_theta(float(nuevo_th))
            if ok:
                st.success(msg)
            else:
                st.error(msg)

        st.divider()

        if st.button("Reiniciar ciclo de recambio", key="btn_reset_recambio"):
            ok, msg = motor.admin_reiniciar_ciclo_recambio()
            if ok:
                st.success(msg)
            else:
                st.error(msg)

# =============================================================================
# PESTANA 4: DATOS CSV Y BOT GOOGLE
# =============================================================================
with tab_datos:
    sub_dat1, sub_dat2, sub_dat3, sub_dat4 = st.tabs([
        "Historial Eventos CSV",
        "Reservas CSV",
        "Estacionamientos CSV",
        "Bot Google y Semilla",
    ])

    with sub_dat1:
        df_evt = pd.read_csv(motor.persistencia.evt_csv)
        st.dataframe(df_evt, use_container_width=True, height=380)
        with open(motor.persistencia.evt_csv, "rb") as f:
            st.download_button("Descargar historial_eventos.csv", data=f, file_name="historial_eventos.csv", mime="text/csv")

    with sub_dat2:
        df_res = pd.read_csv(motor.persistencia.res_csv)
        st.dataframe(df_res, use_container_width=True, height=380)
        with open(motor.persistencia.res_csv, "rb") as f:
            st.download_button("Descargar reservas.csv", data=f, file_name="reservas.csv", mime="text/csv")

    with sub_dat3:
        df_est = pd.read_csv(motor.persistencia.est_csv)
        st.dataframe(df_est, use_container_width=True, height=380)
        with open(motor.persistencia.est_csv, "rb") as f:
            st.download_button("Descargar estacionamientos.csv", data=f, file_name="estacionamientos.csv", mime="text/csv")

    with sub_dat4:
        bot = motor.persistencia.bot_google
        st.write(f"Estado Bot: {bot.ultimo_estado}")

        b_c1, b_c2, b_c3, b_c4 = st.columns(4)
        with b_c1:
            if st.button("Sincronizar CSV a Google Sheets", key="btn_sync_up"):
                ok, msg = bot.sincronizar_csv_a_sheets(motor.persistencia.ARCHIVOS_OPERACIONALES)
                if ok:
                    st.success(msg)
                else:
                    st.warning(msg)
        with b_c2:
            if st.button("Restaurar desde Google Sheets", key="btn_sync_down"):
                ok, msg = bot.restaurar_sheets_a_csv(motor.persistencia.ARCHIVOS_OPERACIONALES)
                if ok:
                    motor.recargar()
                    st.success(msg)
                else:
                    st.warning(msg)
        with b_c3:
            if st.button("Desvincular Bot", key="btn_unlink_bot"):
                bot.desconectar_bot()
                st.rerun()
        with b_c4:
            if st.button("Restaurar Datos Semilla Hito 1", key="btn_seed_reset"):
                motor.persistencia.inicializar_si_no_existe(forzar_reinicio=True)
                motor.recargar()
                st.success("Datos semilla restaurados.")
                st.rerun()

        st.divider()

        sheet_url_in = st.text_input(
            "URL o ID de Google Sheet (dejar en AUTO para deteccion automatica)",
            value=bot.sheet_url if bot.sheet_url else "AUTO",
            key="in_sheet_url",
        )
        creds_json_in = st.text_area(
            "JSON Cuenta de Servicio Google Cloud",
            height=120,
            key="in_creds_json",
        )
        if st.button("Conectar Cuenta de Servicio JSON", key="btn_conn_json"):
            ok, msg = bot.configurar_bot(creds_json_in, sheet_url_in)
            if ok:
                bot.sincronizar_csv_a_sheets(motor.persistencia.ARCHIVOS_OPERACIONALES)
                st.success(msg)
            else:
                st.error(msg)
