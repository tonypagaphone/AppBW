import streamlit as st
from operacion_bwc import consultar_linea, cancelar_linea, guardar_df, cargar_base_operativa, buscar_linea, calcular_fecha_facturacion, generar_archivo_revision, procesar_facturacion, actualizar_activaciones, procesar_recargas_dia, convertir_a_excel
import pandas as pd
import pytz
from datetime import datetime, timedelta, date


st.set_page_config(page_title="Sistema BWC", layout="centered")

st.title("📊 Sistema de Operaciones BWC")

# === SECCIÓN: CONSULTA Y REGISTRO RÁPIDO ===
st.header("🔎 Consulta")

identificador = st.text_input("Ingresa MSISDN o ICCID").strip()
st.markdown("Las fechas mostradas están en formato **AAAA-MM-DD**.  \nPara buscar ICC, ponle un ' al inicio.")
if st.button("🔍 Consultar línea"):
    if identificador:
        resultado = consultar_linea(identificador)
        if resultado:
            for hoja, df in resultado.items():
                if hoja == "Renewals":
                    st.write("📦 **Última recarga**")
                    fecha = pd.to_datetime(df['fecharenovacionservicio'].values[0], errors='coerce')
                    if pd.notnull(fecha):
                        dias = (pd.Timestamp.now().normalize() - fecha).days
                        if dias < 30:
                            st.success(f"Recarga vigente (hace {dias} días). Se puede recargar ilimitado.")
                        else:
                            st.warning("No tiene recarga vigente.")
                elif hoja == "Next Renewals":
                    st.write("🔜 **Siguiente recarga programada**")
                elif hoja == "Activations":
                    st.write("🚀 **Activación**")
                elif hoja == "Billing":
                    st.write("💰 **Última factura**")
                else:
                    st.write(f"📄 **{hoja}**")

                st.dataframe(df, use_container_width=True)
        else:
            st.info("No se encontró la línea.")

st.markdown("---")

# === SECCIÓN: CONSULTA Y REGISTRO RÁPIDO ===
st.header("🗑️ Registros de Baja y Reactivacion")
col1, col2 = st.columns(2)
with col1:
    st.markdown("### 🗑️ Registrar baja")
    identificador_cancelar = st.text_input("Ingresa MSISDN o ICCID para cancelar (ICC con un '):", key="cancelar_input")

    if st.button("Confirmar cancelación"):
        if identificador_cancelar:
            resultado = cancelar_linea(identificador_cancelar.strip())
            if resultado["status"] == "ok":
                st.success(resultado["mensaje"])
            else:
                st.error(resultado["mensaje"])
        else:
            st.warning("Por favor, ingresa un identificador.")

with col2:
    st.markdown("### 🔄 Registrar reactivación")

    with st.form("reactivar_form"):
        msisdn_iccid = st.text_input("MSISDN o ICCID")
        codigo_input = st.text_input("Código distribuidora")
        fecha_reactivacion_input = st.date_input("Fecha de reactivación")

        submitted = st.form_submit_button("Buscar y continuar")

        if submitted:
            # Paso 0: cargar base
            data = cargar_base_operativa()
            np_df = data["no_procede_base"]
            cancelaciones_df = data["cancelations"]
            renewals_df = data["renewals"]
            asociados_df = data["associates_df"]
            day_df = data["billing_days"]
            reactivaciones_df = data["reactivaciones_df"]
            spreadsheet = data["spreadsheet"]
            zona_mx = pytz.timezone("America/Mexico_City")
            hoy = pd.to_datetime(datetime.now(zona_mx).date())

            fecha_reactivacion = pd.to_datetime(fecha_reactivacion_input)

            # Paso 1: buscar línea
            registro = buscar_linea(np_df, msisdn_iccid)
            if registro.empty:
                registro = buscar_linea(cancelaciones_df, msisdn_iccid)
            
            if not registro.empty:
                msisdn = registro['msisdn'].values[0]
                iccid = registro['iccid'].values[0]
                nombre = registro['nombre'].values[0]
                registro = registro.iloc[[-1]].copy()
                st.write("🔎 Línea encontrada:", registro[['nombre', 'msisdn', 'iccid', 'codigoDistribuidora']])
                codigo_encontrado = str(registro['codigoDistribuidora'].values[0])

                if codigo_input != codigo_encontrado:
                    confirmar_cambio = st.radio(
                        f"⚠️ El código ingresado ({codigo_input}) no coincide con el encontrado ({codigo_encontrado}). ¿Es cambio de DS?",
                        options=["Sí", "No"],
                        index=0
                    )
                    if confirmar_cambio == "No":
                        st.error("❌ Registro cancelado por discrepancia.")
                        st.stop()
                    else:
                        codigo_distribuidora = codigo_input
                else:
                    codigo_distribuidora = codigo_encontrado
            else:
                st.warning("🔍 Línea nueva. Ingresa los datos manualmente.")
                nombre = st.text_input("Nombre del cliente")
                msisdn = st.text_input("MSISDN")
                iccid = st.text_input("ICCID")
                if not (nombre and msisdn and iccid):
                    st.stop()
                codigo_distribuidora = codigo_input
            
            if codigo_distribuidora not in asociados_df['codigoDistribuidora'].astype(str).values:
                id_asociado = st.text_input("Código nuevo detectado. Ingresa ID del asociado:")
                if not id_asociado:
                    st.stop()

                asociados_df = pd.concat([asociados_df, pd.DataFrame([{
                    'codigoDistribuidora': codigo_distribuidora,
                    'idAsociado': id_asociado
                }])], ignore_index=True)
            else:
                id_asociado = asociados_df[
                    asociados_df['codigoDistribuidora'].astype(str) == codigo_distribuidora
                ]['idAsociado'].values[0]

            if codigo_distribuidora not in day_df['codigoDistribuidora'].astype(str).values:
                dia_fact = st.text_input("Día de facturación (LUNES a VIERNES)").upper()
                if dia_fact not in ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES"]:
                    st.warning("⚠️ Escribe un día válido (LUNES a VIERNES).")
                    st.stop()
                day_df = pd.concat([day_df, pd.DataFrame([{
                    'codigoDistribuidora': codigo_distribuidora,
                    'diaFacturacion': dia_fact
                }])], ignore_index=True)
            else:
                dia_fact = day_df[
                    day_df['codigoDistribuidora'].astype(str) == codigo_distribuidora
                ]['diaFacturacion'].values[0]
            
            reactivaciones_previas = reactivaciones_df[
                reactivaciones_df['msisdn'].astype(str) == msisdn
            ]
            if not reactivaciones_previas.empty:
                ultima_fecha = pd.to_datetime(reactivaciones_previas['fechaRenovacionServicio'].max())
                dias_diferencia = (hoy - ultima_fecha).days
                if dias_diferencia < 28:
                    st.error(f"❌ Esta línea fue reactivada hace {dias_diferencia} días (última vez: {ultima_fecha.date()}). Registro cancelado.")
                    st.stop()
            

            fecha_facturacion = calcular_fecha_facturacion(hoy, dia_fact)

            nueva_fila = pd.DataFrame([{
                'nombre': nombre,
                'msisdn': msisdn,
                'iccid': iccid,
                'fechaActivacion': registro['fechaActivacion'].values[0] if not registro.empty and 'fechaActivacion' in registro.columns else fecha_reactivacion,
                'fechaRenovacionServicio': fecha_reactivacion,
                'fechaFacturacion': fecha_facturacion,
                'codigoDistribuidora': codigo_distribuidora
            }])

            renewals_df = pd.concat([renewals_df, nueva_fila], ignore_index=True)
            reactivaciones_df = pd.concat([reactivaciones_df, nueva_fila], ignore_index=True)

            guardar_df("Renewals", renewals_df, spreadsheet)
            guardar_df("Reactivaciones", reactivaciones_df, spreadsheet)
            guardar_df("Cancelations", cancelaciones_df, spreadsheet)
            guardar_df("Day", day_df, spreadsheet)
            guardar_df("Associates", asociados_df, spreadsheet)

            st.success("✅ Reactivación registrada correctamente.")

st.markdown("---")

# === SECCIÓN: CREACIÓN DE ARCHIVOS ===
st.header("📁 Crear archivos")

st.subheader("📅 Generar archivo de revisión")
fecha_input = st.date_input(
    "Selecciona el primer día del ciclo de renovación (usualmente lunes)",
    value=st.session_state.get("fecha_revision", None)
)

if st.button("📥 Generar archivo de revisión"):
    if fecha_input:
        st.session_state.fecha_revision = fecha_input
        with st.spinner("Generando archivo..."):
            archivo = generar_archivo_revision(pd.to_datetime(fecha_input))
        st.success("✅ Archivo generado correctamente.")
        st.download_button(
            label="📄 Descargar archivo Excel",
            data=archivo,
            file_name="archivo_revision.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.warning("⚠️ Selecciona una fecha válida.")


st.subheader("🔁 Procesar archivo de facturación")

revision_file = st.file_uploader("📥 Cargar archivo de revisión (Excel)", type=["xlsx"])
actualizacion_csv = st.file_uploader("🔄 Cargar archivo de actualización (CSV)", type=["csv"])

if revision_file and actualizacion_csv:
    if st.button("✅ Procesar facturación"):
        with st.spinner("Procesando..."):
            billing_df = procesar_facturacion(revision_file, actualizacion_csv)
            st.success("¡Facturación procesada exitosamente!")
            st.download_button(
                label="⬇️ Descargar facturación (Excel)",
                data=billing_df.to_csv(index=False).encode("utf-8"),
                file_name="facturacion_generada.csv",
                mime="text/csv"
            )

st.markdown("---")

# === SECCIÓN: ACTUALIZACIONES Y REPORTES ===
st.header("🔄 Actualizaciones")

st.subheader("📲 Actualizar activaciones")

ventas_file = st.file_uploader("📥 Cargar archivo de ventas (Excel)", type=["xlsx"])

if ventas_file:
    if st.button("🔄 Actualizar activaciones"):
        with st.spinner("Actualizando activaciones y hojas asociadas..."):
            actualizar_activaciones(ventas_file)
            st.success("¡Activaciones actualizadas exitosamente!")

st.subheader("📆 Procesar recargas del día")

fecha_dia = st.date_input("Selecciona el día de recarga")

if st.button("⚡ Procesar recargas"):
    with st.spinner("Procesando..."):
        nombre_archivo, df_salida = procesar_recargas_dia(fecha_dia)
        st.success("¡Recargas procesadas exitosamente!")
        st.download_button(
            label="⬇️ Descargar archivo de recargas",
            data=convertir_a_excel(df_salida),  # Asegúrate de tener esta función
            file_name=nombre_archivo,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )