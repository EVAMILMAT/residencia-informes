import streamlit as st
import sqlite3
from datetime import date

# --- Conexión a la base de datos ---
conn = sqlite3.connect("informes.db")
c = conn.cursor()
c.execute('''
    CREATE TABLE IF NOT EXISTS informes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT,
        item1 TEXT,
        item2 TEXT,
        comentarios TEXT
    )
''')
conn.commit()

# --- Interfaz ---
st.title("Informe Diario")

# Formulario
with st.form("formulario_informe"):
    fecha = st.date_input("Fecha", date.today())
    item1 = st.text_input("Ítem 1")
    item2 = st.text_input("Ítem 2")
    comentarios = st.text_area("Comentarios")
    submit = st.form_submit_button("Guardar informe")
    
    if submit:
        c.execute(
            "INSERT INTO informes (fecha, item1, item2, comentarios) VALUES (?,?,?,?)",
            (str(fecha), item1, item2, comentarios)
        )
        conn.commit()
        st.success("Informe guardado correctamente ✅")

# Consulta de informes
st.subheader("Consultar informes")
fecha_busqueda = st.date_input("Seleccionar fecha", date.today(), key="consulta_fecha")
if st.button("Buscar informe"):
    c.execute("SELECT * FROM informes WHERE fecha=?", (str(fecha_busqueda),))
    resultados = c.fetchall()
    if resultados:
        for r in resultados:
            st.write(f"ID: {r[0]}, Fecha: {r[1]}, Ítem 1: {r[2]}, Ítem 2: {r[3]}, Comentarios: {r[4]}")
    else:
        st.warning("No hay informes para esa fecha.")
