# app.py - Bloque 1
import streamlit as st
import sqlite3
from datetime import date
import pandas as pd
import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import json
import streamlit.components.v1 as components


# -----------------------
# Configuración página
# -----------------------
st.set_page_config(page_title="Informes Residència", page_icon="🏠", layout="centered")
st.title("🏠 Gestió d'Informes - Residència Reina Sofia")

# Carpeta para almacenar PDFs
PDFS_DIR = "pdfs"
os.makedirs(PDFS_DIR, exist_ok=True)

# app.py - Bloque 2

# -----------------------
# Conexión a la base de datos
# -----------------------
conn = sqlite3.connect("informes.db", check_same_thread=False)
c = conn.cursor()

# Tabla de informes generales
c.execute('''CREATE TABLE IF NOT EXISTS informes (
    fecha TEXT PRIMARY KEY,
    cuidador TEXT,
    entradas_salidas TEXT,
    mantenimiento TEXT,
    temas_genericos TEXT,
    taxis TEXT
)''')

# Tabla de informes individuales
c.execute('''CREATE TABLE IF NOT EXISTS informes_alumnos (
    fecha TEXT,
    alumno TEXT,
    contenido TEXT,
    PRIMARY KEY (fecha, alumno)
)''')

conn.commit()

# -----------------------
# Listas de cuidadores y alumnos
# -----------------------
CUIDADORES = ["", "Israel Pampin", "Marta Oliver", "Eva Milán"]

ALUMNOS = [
    "Adrian Rebollo Bonet","Aina Colomar Carreras","Aina Comas Casasnovas","Aina Real Cerdá",
    "Albert Gomis Amengual","Aleix Bosch Alles","Alma Dalmau Silgado","Ania Cristina Buciu Bologa",
    "Anna Pelletey Marí","Berta Sans Salord","Clara Comas Casasnovas","Cristina Vicente Tercero",
    "Emily Czaja","Iago Parada Llompart","Jaume Coll Vilanova","Jimena Pons Abad",
    "Joan Cortés Rubio","Joan Morlà Mas","Josep Tur Prats","Júlia Caldentey López",
    "Marc Arias Álvarez","Maria Gornés Rodríguez","Miquel Angel Vicens Candentey","Miquel Morlà Mas",
    "Mireia Perelló Alcover","Orion Leon Rennicke","Pablo Velasco Ortiz","Paula Sans Cantallops",
    "Pere Andreu Martínez","Romina Camarillo Alarcón","Santiago Mesa Godoy","Sara Verbeek Alvarez",
    "Soy Tony Theunisse","Tiago del Po Vica","Tomeu Umbert Sureda","Toni Febrer Sintes",
    "Victor Adda Ferrer","Xabier Fenández Cebey","Xavier Capllonch Salas","Matias Acosta Suarez"
]

# -----------------------
# Alias d'esportistes (sense duplicats)
# -----------------------

def generar_alias_base(nombre_completo: str) -> str:
    """
    Genera un alias base tipo @nombreInicialApellido a partir del nombre completo.
    Ejemplo: 'Aina Real Cerdá' -> '@ainaR'
    """
    partes = nombre_completo.split()
    if not partes:
        return ""

    nombre = partes[0].lower()

    if len(partes) > 1:
        inicial_apellido = partes[1][0].lower()
        return f"@{nombre}{inicial_apellido}"
    else:
        return f"@{nombre}"


def generar_alias_resuelto(nombre_completo: str, existentes: set) -> str:
    """
    Genera un alias evitando duplicados.
    - Primero usa @nombre + inicial 1er apellido.
    - Si ya existe y hay 2º apellido, usa @nombre + inicial 1er + inicial 2º apellido.
    - Si aun así existe, añade sufijos numéricos: @nombrex2, @nombrex3, ...
    """
    partes = nombre_completo.split()
    if not partes:
        return ""

    nombre = partes[0].lower()
    alias_base = generar_alias_base(nombre_completo)

    # 1) Alias base
    if alias_base not in existentes:
        return alias_base

    # 2) Dos iniciales de apellidos
    if len(partes) > 2:
        alias_dos_apellidos = f"@{nombre}{partes[1][0].lower()}{partes[2][0].lower()}"
        if alias_dos_apellidos not in existentes:
            return alias_dos_apellidos

    # 3) Sufijos numéricos
    sufijo = 2
    while True:
        candidato = f"{alias_base}{sufijo}"
        if candidato not in existentes:
            return candidato
        sufijo += 1


# Diccionario global de alias por deportista (sin duplicados)
ALIAS_DEPORTISTAS = {}
_alias_usados = set()

for alumno in ALUMNOS:
    alias = generar_alias_resuelto(alumno, _alias_usados)
    ALIAS_DEPORTISTAS[alumno] = alias
    _alias_usados.add(alias)

# -----------------------
# Tabla de usuarios (para contraseñas actualizadas)
# -----------------------
c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
    usuario TEXT PRIMARY KEY,
    password_hash TEXT
)''')
conn.commit()

import hashlib

# -----------------------
# 🔐 LOGIN DE TUTORES
# -----------------------

def obtener_usuarios():
    """Combina usuarios de secrets y los de la base de datos (prioriza los de la BD)."""
    usuarios = {}
    # Cargar primero desde secrets.toml
    try:
        base = {u: hashlib.sha256(p.encode()).hexdigest() for u, p in st.secrets["auth"].items()}
        usuarios.update(base)
    except Exception:
        st.error("⚠️ No s'han trobat credencials a .streamlit/secrets.toml (secció [auth])")

    # Sobrescribir si existen usuarios actualizados en la BD
    c.execute("SELECT usuario, password_hash FROM usuarios")
    for u, p in c.fetchall():
        usuarios[u] = p

    return usuarios

def verificar_login(usuario, password):
    """Comprueba si el usuario existe y la contraseña coincide."""
    usuarios = obtener_usuarios()
    if usuario in usuarios:
        hash_pw = hashlib.sha256(password.encode()).hexdigest()
        return usuarios[usuario] == hash_pw
    return False

def login():
    """Pantalla d'inici de sessió."""
    st.title("🔐 Accés a l'aplicació")
    st.markdown("Introdueix les teves credencials per continuar:")

    usuario = st.text_input("Usuari")
    password = st.text_input("Contrasenya", type="password")

    if st.button("Iniciar sessió", key="boton_login"):
        if verificar_login(usuario, password):
            st.session_state["usuario_autenticado"] = True
            st.session_state["usuario"] = usuario
            st.success(f"Benvingut/da, {usuario.capitalize()} 👋")
            st.rerun()
        else:
            st.error("Usuari o contrasenya incorrectes.")

def logout():
    """Tanca la sessió."""
    st.session_state["usuario_autenticado"] = False
    st.session_state.pop("usuario", None)
    st.rerun()

def cambiar_contraseña():
    """Formulari per canviar la contrasenya de l'usuari actual."""
    st.header("🔑 Canviar contrasenya")

    usuario = st.session_state.get("usuario", None)
    if not usuario:
        st.warning("Has d'iniciar sessió primer.")
        return

    st.info(f"Estàs canviant la contrasenya de **{usuario.capitalize()}**")

    pw_actual = st.text_input("Contrasenya actual", type="password")
    pw_nueva = st.text_input("Nova contrasenya", type="password")
    pw_confirm = st.text_input("Confirmar nova contrasenya", type="password")

    if st.button("Desar nova contrasenya", key="guardar_nueva_contraseña"):
        # Verificar contraseña actual
        if not verificar_login(usuario, pw_actual):
            st.error("❌ La contrasenya actual no és correcta.")
            return

        # Verificar coincidencia
        if pw_nueva != pw_confirm:
            st.warning("⚠️ Les contrasenyes noves no coincideixen.")
            return

        # Guardar hash nuevo en la base de datos
        hash_nuevo = hashlib.sha256(pw_nueva.encode()).hexdigest()
        c.execute(
            "INSERT OR REPLACE INTO usuarios (usuario, password_hash) VALUES (?, ?)",
            (usuario, hash_nuevo)
        )
        conn.commit()

        st.success("✅ Contrasenya actualitzada correctament.")
        st.info("Tornant al menú principal...")

        # Redirigir automáticamente al menú principal
        st.session_state["vista_actual"] = "menu"
        st.rerun()

    st.divider()

    # 🔙 Botón para volver sin cambiar nada
    if st.button("🏠 Tornar al menú", key="volver_menu_cambiar_contraseña"):
        st.session_state["vista_actual"] = "menu"
        st.rerun()



# app.py - Bloque 3

# -----------------------
# Estado de sesión
# -----------------------
if "vista_actual" not in st.session_state:
    st.session_state["vista_actual"] = "menu"

if "form_general" not in st.session_state:
    st.session_state["form_general"] = {
        "fecha": "",
        "cuidador": "",
        "entradas": "",
        "mantenimiento": "",
        "temas": "",
        "taxis": []
    }

if "form_individual" not in st.session_state:
    st.session_state["form_individual"] = {
        "fecha": "",
        "alumno": "",
        "contenido": ""
    }

if "confirm_overwrite" not in st.session_state:
    st.session_state["confirm_overwrite"] = None

if "confirm_overwrite_ind" not in st.session_state:
    st.session_state["confirm_overwrite_ind"] = None

if "taxis_data" not in st.session_state:
    st.session_state["taxis_data"] = []

if "confirmar_salir_general" not in st.session_state:
    st.session_state["confirmar_salir_general"] = False

if "confirmar_salir_individual" not in st.session_state:
    st.session_state["confirmar_salir_individual"] = False


# app.py - Bloque 4 (versión final con formato dd/mm/yyyy en todo)
# -----------------------
# Funciones PDF
# -----------------------
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from datetime import datetime

def generar_pdf_general(cuidador, fecha_iso, entradas, mantenimiento, temas, taxis_list, alumnos_list):
    # Convertir fecha ISO a formato dd/mm/yyyy
    fecha_dt = datetime.strptime(fecha_iso, "%Y-%m-%d")
    fecha_formateada = fecha_dt.strftime("%d/%m/%Y")
    fecha_archivo = fecha_dt.strftime("%d-%m-%Y")

    # Guardar con nombre de archivo con formato dd-mm-yyyy
    fname = os.path.join(PDFS_DIR, f"informe_general_{fecha_archivo}.pdf")
    doc = SimpleDocTemplate(
        fname,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2.5*cm,
        bottomMargin=2*cm
    )
    elements = []

    # --- Estilos ---
    titulo = ParagraphStyle(
        name="Titulo",
        fontName="Helvetica-Bold",
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=20
    )
    subtitulo = ParagraphStyle(
        name="Subtitulo",
        fontName="Helvetica",
        fontSize=12,
        alignment=TA_CENTER,
        spaceAfter=12
    )
    bloque_titulo = ParagraphStyle(
        name="BloqueTitulo",
        fontName="Helvetica-Bold",
        fontSize=12,
        alignment=TA_LEFT,
        spaceAfter=6
    )
    bloque_texto = ParagraphStyle(
        name="BloqueTexto",
        fontName="Helvetica",
        fontSize=10,
        alignment=TA_LEFT,
        leading=14
    )
    tabla_estilo = TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("FONTNAME", (0,0), (-1,-1), "Helvetica"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("ALIGN", (0,0), (-1,-1), "LEFT"),
    ])

    # --- Capçalera ---
    elements.append(Paragraph("Residència Reina Sofia", titulo))
    elements.append(Paragraph(f"<b>Informe del dia {fecha_formateada}</b>", subtitulo))
    elements.append(Spacer(1, 12))

    # --- Cuidador ---
    elements.append(Paragraph(f"<b>Cuidador/a:</b> {cuidador or '—'}", bloque_texto))
    elements.append(Spacer(1, 12))

    # --- Funció per crear blocs amb requadre ---
    def bloque(titol, contingut):
        contingut_html = (contingut or "—").replace("\n", "<br/>")
        data = [
            [Paragraph(f"<b>{titol}</b>", bloque_titulo)],
            [Paragraph(contingut_html, bloque_texto)]
        ]
        tabla = Table(data, colWidths=[16*cm])
        tabla.setStyle(TableStyle([
            ("BOX", (0,0), (-1,-1), 1, colors.black),
            ("INNERPADDING", (0,0), (-1,-1), 6),
            ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
        ]))
        elements.append(tabla)
        elements.append(Spacer(1, 12))

    # --- Blocs principals amb els noms nous ---
    bloque("Informe del dia", entradas)
    bloque("Notes per direcció, manteniment i neteja", mantenimiento)
    bloque("Pícnics pel dia següent", temas)

    # --- Llista d'informes individuals generats ---
    if alumnos_list:
        alumnes_str = "\n".join([f"• {a}" for a in alumnos_list])
        bloque("Informes individuals generats aquest dia", alumnes_str)

    # --- Taula de taxis ---
    if taxis_list:
        elements.append(Paragraph("<b>Taxis</b>", bloque_titulo))
        taxis_data = [["Data", "Hora", "Recollida", "Destí", "Esportistes", "Observacions"]]
        for t in taxis_list:
            fecha_taxi = t.get("Fecha", "")
            # Convertir si està en format YYYY-MM-DD
            if isinstance(fecha_taxi, str) and len(fecha_taxi.split("-")) == 3:
                try:
                    fecha_taxi = datetime.strptime(fecha_taxi, "%Y-%m-%d").strftime("%d/%m/%Y")
                except Exception:
                    pass
            taxis_data.append([
                fecha_taxi,
                t.get("Hora", ""),
                t.get("Recogida", ""),
                t.get("Destino", ""),
                t.get("Deportistas", ""),
                t.get("Observaciones", "")
            ])
        tabla_taxis = Table(taxis_data, colWidths=[2.3*cm, 2.3*cm, 3*cm, 3*cm, 3*cm, 3*cm])
        tabla_taxis.setStyle(tabla_estilo)
        elements.append(tabla_taxis)

    doc.build(elements)
    return fname


def generar_pdf_individual(alumno, contenido, fecha_iso):
    fecha_dt = datetime.strptime(fecha_iso, "%Y-%m-%d")
    fecha_formateada = fecha_dt.strftime("%d/%m/%Y")
    fecha_archivo = fecha_dt.strftime("%d-%m-%Y")

    # Guardar con nombre con formato dd-mm-yyyy
    fname = os.path.join(PDFS_DIR, f"informe_{alumno.replace(' ', '_')}_{fecha_archivo}.pdf")
    doc = SimpleDocTemplate(fname, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2.5*cm, bottomMargin=2*cm)
    elements = []

    # --- Estilos ---
    titulo = ParagraphStyle(name="Titulo", fontName="Helvetica-Bold", fontSize=16, alignment=TA_CENTER, spaceAfter=20)
    subtitulo = ParagraphStyle(name="Subtitulo", fontName="Helvetica", fontSize=12, alignment=TA_CENTER, spaceAfter=12)
    bloque_titulo = ParagraphStyle(name="BloqueTitulo", fontName="Helvetica-Bold", fontSize=12, alignment=TA_LEFT, spaceAfter=6)
    bloque_texto = ParagraphStyle(name="BloqueTexto", fontName="Helvetica", fontSize=10, alignment=TA_LEFT, leading=14)

    # --- Cabecera ---
    elements.append(Paragraph("Residència Reina Sofia", titulo))
    elements.append(Paragraph(f"<b>Informe del dia {fecha_formateada}</b>", subtitulo))
    elements.append(Spacer(1, 18))

    # --- Alumne ---
    elements.append(Paragraph(f"<b>Nom de l'alumne/a:</b> {alumno}", bloque_texto))
    elements.append(Spacer(1, 12))

    # --- Contingut ---
    contenido_html = (contenido or "—").replace("\n", "<br/>")
    data = [
        [Paragraph("<b>Contingut</b>", bloque_titulo)],
        [Paragraph(contenido_html, bloque_texto)]
    ]
    tabla = Table(data, colWidths=[16*cm])
    tabla.setStyle(TableStyle([
        ("BOX", (0,0), (-1,-1), 1, colors.black),
        ("INNERPADDING", (0,0), (-1,-1), 6),
        ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
    ]))
    elements.append(tabla)

    # --- Generar PDF ---
    doc.build(elements)
    return fname


# -----------------------
# Función enviar correo Gmail
# -----------------------
def enviar_correo(asunto, cuerpo, lista_pdfs):
    try:
        EMAIL_FROM = st.secrets["EMAIL_FROM"]
        EMAIL_PASSWORD = st.secrets["EMAIL_PASSWORD"]
        EMAIL_TO = st.secrets["EMAIL_TO"]
    except Exception:
        st.error("Falten secrets a .streamlit/secrets.toml (EMAIL_FROM, EMAIL_PASSWORD, EMAIL_TO)")
        return False

    msg = MIMEMultipart()
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg["Subject"] = asunto
    msg.attach(MIMEText(cuerpo, "plain"))

    for path in lista_pdfs:
        with open(path, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(path))
        part["Content-Disposition"] = f'attachment; filename="{os.path.basename(path)}"'
        msg.attach(part)

    try:
        with smtplib.SMTP("smtp.gmail.com",587) as server:
            server.starttls()
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        st.error(f"❌ Error en enviar el correu: {e}")
        return False

# app.py - Bloque 5
# -----------------------
# Menú principal
# -----------------------
def mostrar_menu():
    vista = st.session_state.get("vista_actual", "menu")

    # Menú principal (solo si estamos en el menú)
    if vista == "menu":
        st.header("📋 Menú principal")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🗓️ Introduir informe general", use_container_width=True):
                st.session_state["vista_actual"] = "informe_general"
                st.rerun()
            if st.button("🔎 Consultar informe general", use_container_width=True):
                st.session_state["vista_actual"] = "consultar_general"
                st.rerun()
        with col2:
            if st.button("👤 Introduir informe individual", use_container_width=True):
                st.session_state["vista_actual"] = "informe_individual"
                st.rerun()
            if st.button("📄 Consultar informes d'alumnes", use_container_width=True):
                st.session_state["vista_actual"] = "consultar_individual"
                st.rerun()

        st.divider()

        # 🔹 Accés directe als històrics
        if st.button("🖨️ Imprimir històrics", use_container_width=True):
            st.session_state["vista_actual"] = "historico"
            st.rerun()

    # Vistas secundarias
    elif vista == "informe_general":
        formulario_informe_general()
    elif vista == "informe_individual":
        formulario_informe_individual()
    elif vista == "consultar_general":
        consultar_informe_general()
    elif vista == "consultar_individual":
        consultar_informe_individual()


# app.py - Bloque 6

# -----------------------
# Funciones de ayuda
# -----------------------
def limpiar_formulario_general():
    st.session_state["form_general"] = {
        "fecha": "",
        "cuidador": "",
        "entradas": "",
        "mantenimiento": "",
        "temas": "",
        "taxis": []
    }
    st.session_state["taxis_data"] = []
    st.session_state["confirm_overwrite"] = None
    st.session_state["vista_actual"] = "menu"

def limpiar_formulario_individual():
    st.session_state["form_individual"] = {
        "fecha": "",
        "alumno": "",
        "contenido": ""
    }
    st.session_state["confirm_overwrite_ind"] = None
    st.session_state["vista_actual"] = "menu"

def comprobar_sobrescribir_general(fecha_iso):
    c.execute("SELECT * FROM informes WHERE fecha=?", (fecha_iso,))
    row = c.fetchone()
    return row is not None

def comprobar_sobrescribir_individual(fecha_iso, alumno):
    c.execute("SELECT * FROM informes_alumnos WHERE fecha=? AND alumno=?", (fecha_iso, alumno))
    row = c.fetchone()
    return row is not None

# app.py – Bloque 7
# -----------------------
# Formulari Informe General
# -----------------------

def formulario_informe_general():
    st.header("🗓️ Introduir informe general")

    cuidadores = CUIDADORES

    # --- Estat inicial ---
    if "informe_general" not in st.session_state:
        st.session_state["informe_general"] = {
            "cuidador": "",
            "entradas": "",
            "mantenimiento": "",
            "temas": "",
            "taxis": []
        }

    if "fecha_cargada" not in st.session_state:
        st.session_state["fecha_cargada"] = None
    if "bloqueado" not in st.session_state:
        st.session_state["bloqueado"] = False
    if "taxis_df" not in st.session_state:
        st.session_state["taxis_df"] = pd.DataFrame(
            columns=["Fecha", "Hora", "Recogida", "Destino", "Deportistas", "Observaciones"]
        )
    if "confirmar_salir_general" not in st.session_state:
        st.session_state["confirmar_salir_general"] = False

    # --- Data de l'informe ---
    fecha_sel = st.date_input("Data de l'informe", value=date.today(), key="fecha_general")
    fecha_iso = fecha_sel.isoformat()
    fecha_mostrar = fecha_sel.strftime("%d/%m/%Y")
    st.markdown(f"**Data seleccionada:** {fecha_mostrar}")

    # --- Carrega des de BD quan canvia la data ---
    if st.session_state["fecha_cargada"] != fecha_iso:
        st.session_state["fecha_cargada"] = fecha_iso

        c.execute(
            "SELECT cuidador, entradas_salidas, mantenimiento, temas_genericos, taxis "
            "FROM informes WHERE fecha=?",
            (fecha_iso,)
        )
        row = c.fetchone()

        if row:
            cuidador, entradas, mantenimiento, temas, taxis_json = row
            st.session_state["informe_general"] = {
                "cuidador": cuidador or "",
                "entradas": entradas or "",
                "mantenimiento": mantenimiento or "",
                "temas": temas or "",
                "taxis": json.loads(taxis_json) if taxis_json else []
            }
            st.session_state["taxis_df"] = pd.DataFrame(
                st.session_state["informe_general"]["taxis"],
                columns=["Fecha", "Hora", "Recogida", "Destino", "Deportistas", "Observaciones"]
            )
            st.session_state["bloqueado"] = True
        else:
            st.session_state["informe_general"] = {
                "cuidador": "",
                "entradas": "",
                "mantenimiento": "",
                "temas": "",
                "taxis": []
            }
            st.session_state["taxis_df"] = pd.DataFrame(
                columns=["Fecha", "Hora", "Recogida", "Destino", "Deportistas", "Observaciones"]
            )
            st.session_state["bloqueado"] = False

        st.session_state["confirmar_salir_general"] = False

    info = st.session_state["informe_general"]
    bloqueado = st.session_state["bloqueado"]

    # --- Àlies d'esportistes (no toca l'estat del formulari) ---
    with st.expander("👀 Consultar àlies d'esportistes (@)", expanded=False):
        st.caption("Fes servir aquests àlies al text: @ainaR, @marcA…")
        df_alias = pd.DataFrame(
            [{"Esportista": n, "Àlies": ALIAS_DEPORTISTAS.get(n, "")} for n in ALUMNOS]
        )
        st.dataframe(df_alias, use_container_width=True, hide_index=True)

    # --- Informació de bloqueig ---
    if bloqueado:
        st.info("🔒 Aquest informe ja està desat i bloquejat per a l'edició.")
        if st.button("✏️ Editar informe desat"):
            st.session_state["bloqueado"] = False
            st.rerun()

    # --- Formulari principal ---
    with st.form("form_informe_general", clear_on_submit=False):
        disabled = bloqueado

        idx = cuidadores.index(info["cuidador"]) if info["cuidador"] in cuidadores else 0
        cuidador_sel = st.selectbox(
            "Cuidador/a",
            cuidadores,
            index=idx,
            disabled=disabled
        )

        entradas_txt = st.text_area(
            "Informe del dia",
            value=info["entradas"],
            height=120,
            disabled=disabled
        )

        mantenimiento_txt = st.text_area(
            "Notes per direcció, manteniment i neteja",
            value=info["mantenimiento"],
            height=120,
            disabled=disabled
        )

        temas_txt = st.text_area(
            "Pícnics pel dia següent",
            value=info["temas"],
            height=120,
            disabled=disabled
        )

        with st.expander("🚕 Detalls dels taxis", expanded=True):
            taxis_df = st.data_editor(
                st.session_state["taxis_df"],
                num_rows="dynamic",
                hide_index=True,
                use_container_width=True,
                disabled=disabled,
                key="taxis_editor",
                column_config={
                    "Fecha": st.column_config.TextColumn("Data (dd/mm/aaaa)"),
                    "Hora": st.column_config.TextColumn("Hora (hh:mm)"),
                    "Recogida": st.column_config.TextColumn("Recollida"),
                    "Destino": st.column_config.TextColumn("Destí"),
                    "Deportistas": st.column_config.TextColumn("Esportistes"),
                    "Observaciones": st.column_config.TextColumn("Observacions"),
                }
            )

            def normalizar_fecha(v):
                if not isinstance(v, str):
                    return v
                v = v.replace("-", "/").replace(".", "/").strip()
                p = v.split("/")
                if len(p) == 3:
                    d, m, a = p
                    if len(a) == 2:
                        a = "20" + a
                    try:
                        return datetime.strptime(f"{d}/{m}/{a}", "%d/%m/%Y").strftime("%d/%m/%Y")
                    except:
                        return v
                return v

            def normalizar_hora(v):
                if not isinstance(v, str):
                    return v
                v = v.strip().replace(".", ":").replace("h", ":").replace("H", ":")
                if v.isdigit():
                    if len(v) == 1:
                        return f"0{v}:00"
                    if len(v) == 2:
                        return f"{v}:00"
                    if len(v) == 3:
                        return f"{v[0]}:{v[1:]}"
                    if len(v) == 4:
                        return f"{v[:2]}:{v[2:]}"
                    return v
                for fmt in ["%H:%M", "%H:%M:%S", "%H:%M:%S.%f"]:
                    try:
                        return datetime.strptime(v, fmt).strftime("%H:%M")
                    except:
                        pass
                return v

            if "Fecha" in taxis_df.columns:
                taxis_df["Fecha"] = taxis_df["Fecha"].apply(normalizar_fecha)
            if "Hora" in taxis_df.columns:
                taxis_df["Hora"] = taxis_df["Hora"].apply(normalizar_hora)

            st.session_state["taxis_df"] = taxis_df

        # Botones de guardar
        col_guardar_1, col_guardar_2 = st.columns(2)
        with col_guardar_1:
            submitted_enviar = st.form_submit_button("💾 Desar i enviar", disabled=disabled)
        with col_guardar_2:
            submitted_sense_enviar = st.form_submit_button("💾 Desar sense enviar", disabled=disabled)

    # --- Desar ---
    if submitted_enviar or submitted_sense_enviar:
        if not cuidador_sel:
            st.warning("⚠️ Has de seleccionar un cuidador abans de desar l'informe.")
            return

        # Actualitzar explícitament l'estat amb el que hi ha al formulari
        info["cuidador"] = cuidador_sel
        info["entradas"] = entradas_txt
        info["mantenimiento"] = mantenimiento_txt
        info["temas"] = temas_txt

        taxis_records = st.session_state["taxis_df"].to_dict("records")
        info["taxis"] = taxis_records
        taxis_json = json.dumps(taxis_records)

        c.execute(
            "INSERT OR REPLACE INTO informes "
            "(fecha, cuidador, entradas_salidas, mantenimiento, temas_genericos, taxis) "
            "VALUES (?,?,?,?,?,?)",
            (fecha_iso, info["cuidador"], info["entradas"], info["mantenimiento"], info["temas"], taxis_json)
        )
        conn.commit()

        # OPCIONAL: debug para verificar exactamente qué hay en BD
        # c.execute(
        #     "SELECT cuidador, entradas_salidas, mantenimiento, temas_genericos "
        #     "FROM informes WHERE fecha=?",
        #     (fecha_iso,)
        # )
        # debug_row = c.fetchone()
        # st.caption(f"[DEBUG] BD després de desar: {debug_row}")

        c.execute("SELECT alumno FROM informes_alumnos WHERE fecha=?", (fecha_iso,))
        alumnos = [r[0] for r in c.fetchall()]

        pdf = generar_pdf_general(
            info["cuidador"], fecha_iso,
            info["entradas"], info["mantenimiento"], info["temas"],
            info["taxis"], alumnos
        )

        if submitted_enviar:
            enviar_correo(
                f"Informe general - {fecha_mostrar}",
                f"Adjunt informe general {fecha_mostrar}",
                [pdf]
            )
            st.success("✅ Informe desat i enviat.")
        else:
            st.success("✅ Informe desat (sense enviar correu).")

        st.session_state["bloqueado"] = True
        st.session_state["confirmar_salir_general"] = False
        st.rerun()

    # --- Tornar al menú amb protecció de canvis ---
    if st.session_state.get("confirmar_salir_general", False):
        st.warning("⚠ Hi ha canvis sense desar. Segur que vols tornar al menú?")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Sí, tornar al menú", key="salir_sin_guardar_general"):
                st.session_state["confirmar_salir_general"] = False
                st.session_state["fecha_cargada"] = None
                st.session_state["vista_actual"] = "menu"
                st.rerun()
        with col2:
            if st.button("Cancel·lar", key="cancelar_salida_general"):
                st.session_state["confirmar_salir_general"] = False
                st.rerun()
    else:
        if st.button("🏠 Tornar al menú", key="volver_inicio_general"):
            if not st.session_state["bloqueado"]:
                st.session_state["confirmar_salir_general"] = True
                st.rerun()
            else:
                st.session_state["fecha_cargada"] = None
                st.session_state["vista_actual"] = "menu"
                st.rerun()


        
# app.py – Bloque 8
# -----------------------
# Formulari Informe Individual
# -----------------------

def formulario_informe_individual():
    st.header("👤 Introduir informe individual")

    # Control d'edició
    if "forzar_edicion_individual" not in st.session_state:
        st.session_state["forzar_edicion_individual"] = False
    if "alumno_actual_informe" not in st.session_state:
        st.session_state["alumno_actual_informe"] = ""

    # Selecció de data
    fecha_sel = st.date_input("Data de l'informe", value=date.today(), key="fecha_individual")
    fecha_iso = fecha_sel.isoformat()

    # Data en format dd/mm/aaaa
    fecha_mostrar = fecha_sel.strftime("%d/%m/%Y")
    st.markdown(f"**Data seleccionada:** {fecha_mostrar}")

    # Llista d'alumnes amb opció en blanc
    alumno_lista = [""] + ALUMNOS
    alumno = st.selectbox("Alumne", alumno_lista, index=0)

    # Si canviem d'alumne, sortim del mode edició forçada
    if alumno != st.session_state["alumno_actual_informe"]:
        st.session_state["alumno_actual_informe"] = alumno
        st.session_state["forzar_edicion_individual"] = False

    # ----------------------------------------------------
    # Comprovar si ja existeix informe i carregar contingut
    # ----------------------------------------------------
    contenido_inicial = ""
    tiene_informe = False

    if alumno:
        c.execute(
            "SELECT contenido FROM informes_alumnos WHERE fecha=? AND alumno=?",
            (fecha_iso, alumno)
        )
        row = c.fetchone()
        if row:
            tiene_informe = True
            contenido_inicial = row[0] or ""

    bloqueado = tiene_informe and not st.session_state["forzar_edicion_individual"]

    # Missatge si l'informe existeix
    if tiene_informe and bloqueado:
        st.info("🔒 Aquest informe ja existeix i està bloquejat per a l'edició.")
        if st.button("✏️ Editar informe existent"):
            st.session_state["forzar_edicion_individual"] = True
            st.rerun()

    # Camp de contingut (valor actual del widget)
    contenido = st.text_area(
        "Contingut de l'informe",
        value=contenido_inicial,
        height=150,
        disabled=bloqueado
    )

    # -----------------------------------------
    # Funció interna per desar i tornar al menú
    # -----------------------------------------
    def guardar_i_tornar(enviar=True):
        # Validació: alumne obligatori
        if not alumno:
            st.warning("⚠️ Has de seleccionar un alumne abans de desar l'informe.")
            return

        # Guardam exactament el que hi ha al widget ara mateix
        c.execute(
            "INSERT OR REPLACE INTO informes_alumnos (fecha, alumno, contenido) VALUES (?,?,?)",
            (fecha_iso, alumno, contenido)
        )
        conn.commit()

        # OPCIONAL: debug per comprovar què queda a la BD
        # c.execute(
        #     "SELECT contenido FROM informes_alumnos WHERE fecha=? AND alumno=?",
        #     (fecha_iso, alumno)
        # )
        # debug_row = c.fetchone()
        # st.caption(f"[DEBUG] BD després de desar individual: {debug_row}")

        data_text = fecha_sel.strftime("%d/%m/%Y")
        pdf = generar_pdf_individual(alumno, contenido, fecha_iso)

        if enviar:
            enviar_correo(
                f"Informe individual - {alumno} - {data_text}",
                f"Adjunt informe individual de {alumno} ({data_text})",
                [pdf]
            )
            st.success(f"✅ Informe individual desat i enviat: {pdf}")
        else:
            st.success(f"✅ Informe individual desat (sense enviar correu): {pdf}")

        st.session_state["forzar_edicion_individual"] = False
        st.session_state["confirmar_salir_individual"] = False
        st.session_state["vista_actual"] = "menu"
        st.rerun()

    # ================================
    # BOTONS PRINCIPALS DE DESAR
    # ================================
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("💾 Desar i enviar informe", disabled=bloqueado):
            guardar_i_tornar(enviar=True)
    with col_b2:
        if st.button("💾 Desar sense enviar", disabled=bloqueado):
            guardar_i_tornar(enviar=False)

    # ================================
    # PROTECCIÓ SORTIDA SENSE DESAR
    # ================================
    # Avaluam dades directament dels widgets
    tiene_datos = (
        (alumno is not None and alumno != "") or
        (contenido is not None and contenido.strip() != "")
    )

    if st.session_state["confirmar_salir_individual"]:
        st.warning("⚠ Hi ha canvis sense desar. Vols desar l'informe abans de sortir?")

        col1, col2, col3 = st.columns(3)

        # Desar i sortir (comportament igual que abans: guarda i envia)
        with col1:
            if st.button("💾 Desar i tornar al menú", key="confirm_guardar_sortir_individual"):
                guardar_i_tornar(enviar=True)

        # Sortir sense desar
        with col2:
            if st.button("Sortir sense desar", key="sortir_sense_desar_individual"):
                st.session_state["confirmar_salir_individual"] = False
                st.session_state["forzar_edicion_individual"] = False
                st.session_state["vista_actual"] = "menu"
                st.rerun()

        # Cancel·lar (quedar-se a la pantalla i no sortir)
        with col3:
            if st.button("Cancel·lar", key="cancelar_sortida_individual"):
                st.session_state["confirmar_salir_individual"] = False
                st.rerun()

    else:
        # Botó normal de tornar a l'inici
        if st.button("🏠 Tornar a l'inici", key="volver_inicio_individual"):
            # Només demanam confirmació si hi ha dades i l'informe no està bloquejat
            if tiene_datos and not bloqueado:
                st.session_state["confirmar_salir_individual"] = True
                st.rerun()
            else:
                st.session_state["vista_actual"] = "menu"
                st.rerun()


# app.py - Bloque 9
# -----------------------
# Consultes i Històrics
# -----------------------

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from datetime import datetime
import re


# =====================================================
#   DETECCIÓ I EXTRACCIÓ DE MENCIONS
# =====================================================

def extraer_menciones_de(alumno, texto):
    """
    Retorna una llista de línies on apareix es deportista.
    Mira línia per línia i retorna la línia completa si detecta:
    - l'àlies definit
    - o un @nom
    """
    if not texto:
        return []

    alias = ALIAS_DEPORTISTAS.get(alumno, "")
    alias_lower = alias.lower() if alias else ""
    nombre_pila = alumno.split()[0].lower()

    trozos = []

    for linea in texto.splitlines():
        linea_str = linea or ""
        linea_lower = linea_str.lower()

        te_alias = alias_lower and alias_lower in linea_lower
        te_nom = f"@{nombre_pila}" in linea_lower

        if te_alias or te_nom:
            trozos.append(linea_str.strip())

    return trozos


def hay_mencion_de(alumno, texto):
    return len(extraer_menciones_de(alumno, texto)) > 0


# =====================================================
#   CONSULTAR INFORME INDIVIDUAL I MENCIONS
# =====================================================

def consultar_informe_individual():
    st.header("📄 Consultar informació d'un esportista")

    alumno = st.selectbox("Seleccionar esportista", ALUMNOS)

    tipo = st.radio(
        "Tipus de consulta",
        ["Informes individuals", "Mencions als informes generals"],
        horizontal=True
    )

    if not alumno:
        st.info("Seleccionau un esportista per consultar la informació.")
        return

    # -------------------------------------------------
    # 1) INFORMES INDIVIDUALS
    # -------------------------------------------------
    if tipo == "Informes individuals":
        c.execute("""
            SELECT fecha, contenido 
            FROM informes_alumnos 
            WHERE alumno=? 
            ORDER BY fecha DESC
        """, (alumno,))
        registros = c.fetchall()

        if not registros:
            st.info("No hi ha informes individuals per aquest esportista.")
        else:
            for fecha, contenido in registros:
                fecha_mostrar = datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m/%Y")

                st.markdown(
                    f"""
                    <div style="border:1px solid #cccccc; border-radius:6px; padding:12px; margin-bottom:12px;">
                        <strong>📅 {fecha_mostrar}</strong><br><br>
                        <pre style="white-space:pre-wrap; margin:0;">{contenido or "—"}</pre>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

    # -------------------------------------------------
    # 2) MENCIONS EN INFORMES GENERALS
    # -------------------------------------------------
    else:
        c.execute("""
            SELECT fecha, cuidador, entradas_salidas, mantenimiento, temas_genericos
            FROM informes
            ORDER BY fecha DESC
        """)
        registros = c.fetchall()

        menciones = []

        for fecha, cuidador, entradas, mantenimiento, temas in registros:
            campos = {}

            frags_e = extraer_menciones_de(alumno, entradas)
            if frags_e:
                campos["Informe del dia"] = "\n".join(frags_e)

            frags_m = extraer_menciones_de(alumno, mantenimiento)
            if frags_m:
                campos["Notes per direcció, manteniment i neteja"] = "\n".join(frags_m)

            frags_t = extraer_menciones_de(alumno, temas)
            if frags_t:
                campos["Pícnics pel dia següent"] = "\n".join(frags_t)

            if campos:
                menciones.append((fecha, cuidador, campos))

        if not menciones:
            st.info("No hi ha mencions d'aquest esportista als informes generals.")
        else:
            for fecha, cuidador, campos in menciones:
                fecha_mostrar = datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m/%Y")

                st.markdown(f"### 📅 {fecha_mostrar} — 🧑‍💼 {cuidador or '—'}")

                for titulo, contenido in campos.items():
                    st.markdown(
                        f"""
                        <div style="border:1px solid #bbbbbb; border-radius:6px; padding:10px; margin-bottom:8px;">
                            <strong>{titulo}</strong><br>
                            <pre style="white-space:pre-wrap; margin:0;">{contenido or "—"}</pre>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                st.divider()

    if st.button("🏠 Tornar al menú", key="volver_menu_individual_consulta"):
        st.session_state["vista_actual"] = "menu"
        st.rerun()


# =====================================================
#   CONSULTAR INFORME GENERAL
# =====================================================

def consultar_informe_general():
    st.header("🔎 Consultar informe general")

    fecha_sel = st.date_input("Selecciona la data de l'informe", value=date.today(), key="fecha_consulta_general")
    fecha_iso = fecha_sel.isoformat()
    fecha_mostrar = fecha_sel.strftime("%d/%m/%Y")

    st.markdown(f"**Data seleccionada:** {fecha_mostrar}")

    c.execute("""
        SELECT cuidador, entradas_salidas, mantenimiento, temas_genericos, taxis 
        FROM informes 
        WHERE fecha=?
    """, (fecha_iso,))
    row = c.fetchone()

    if not row:
        st.info(f"No hi ha informe general guardat per a {fecha_mostrar}.")

        if st.button("🏠 Tornar al menú", key="volver_menu_general_consulta_sense_informe"):
            st.session_state["vista_actual"] = "menu"
            st.rerun()

        return

    cuidador, entradas, mantenimiento, temas, taxis_json = row

    st.markdown(
        f"""
        <div style="border:1px solid #cccccc; border-radius:6px; padding:10px; margin-bottom:10px;">
            <strong>Cuidador/a</strong><br>
            {cuidador or "—"}
        </div>
        """,
        unsafe_allow_html=True
    )

    # Informe del dia
    st.markdown(
        f"""
        <div style="border:1px solid #cccccc; border-radius:6px; padding:10px; margin-bottom:10px;">
            <strong>Informe del dia</strong><br>
            <pre style="white-space:pre-wrap; margin:0;">{entradas or "—"}</pre>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Notes per direcció, manteniment i neteja
    st.markdown(
        f"""
        <div style="border:1px solid #cccccc; border-radius:6px; padding:10px; margin-bottom:10px;">
            <strong>Notes per direcció, manteniment i neteja</strong><br>
            <pre style="white-space:pre-wrap; margin:0;">{mantenimiento or "—"}</pre>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Pícnics pel dia següent
    st.markdown(
        f"""
        <div style="border:1px solid #cccccc; border-radius:6px; padding:10px; margin-bottom:10px;">
            <strong>Pícnics pel dia següent</strong><br>
            <pre style="white-space:pre-wrap; margin:0;">{temas or "—"}</pre>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Taxis
    taxis_list = json.loads(taxis_json) if taxis_json else []
    if taxis_list:
        st.markdown(
            """
            <div style="border:1px solid #cccccc; border-radius:6px; padding:10px; margin-bottom:10px;">
                <strong>Taxis</strong>
            </div>
            """,
            unsafe_allow_html=True
        )
        st.table(pd.DataFrame(taxis_list))

    if st.button("🏠 Tornar al menú", key="volver_menu_general_consulta"):
        st.session_state["vista_actual"] = "menu"
        st.rerun()


# =====================================================
#   HISTÒRIC INDIVIDUAL (AMB MENCIONS)
# =====================================================

def generar_pdf_historico_individual(alumno, desde, hasta):
    fname = os.path.join(
        PDFS_DIR,
        f"historico_individual_{alumno.replace(' ','_')}_{desde.strftime('%d-%m-%Y')}_a_{hasta.strftime('%d-%m-%Y')}.pdf"
    )
    doc = SimpleDocTemplate(
        fname,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )
    elements = []

    estilo_titulo = ParagraphStyle(name="Titulo", fontName="Helvetica-Bold",
                                   fontSize=16, alignment=TA_CENTER, spaceAfter=6)
    estilo_sub = ParagraphStyle(name="Sub", fontName="Helvetica",
                                fontSize=12, alignment=TA_CENTER, spaceAfter=10)
    estilo_fecha = ParagraphStyle(name="Fecha", fontName="Helvetica-Bold",
                                  fontSize=13, spaceAfter=6)
    estilo_titulo_bloque = ParagraphStyle(name="TituloBloque", fontName="Helvetica-Bold",
                                          fontSize=12, spaceAfter=4)
    estilo_texto = ParagraphStyle(name="Texto", fontName="Helvetica",
                                  fontSize=10, leading=14)

    # Informes individuals
    c.execute("""
        SELECT fecha, contenido 
        FROM informes_alumnos 
        WHERE alumno=? 
          AND fecha BETWEEN ? AND ? 
        ORDER BY fecha ASC
    """, (alumno, desde.strftime("%Y-%m-%d"), hasta.strftime("%Y-%m-%d")))
    registros_ind = c.fetchall()

    # Mencions generals
    c.execute("""
        SELECT fecha, cuidador, entradas_salidas, mantenimiento, temas_genericos
        FROM informes
        WHERE fecha BETWEEN ? AND ?
        ORDER BY fecha ASC
    """, (desde.strftime("%Y-%m-%d"), hasta.strftime("%Y-%m-%d")))
    registros_gen = c.fetchall()

    menciones = []

    for fecha, cuidador, entradas, mantenimiento, temas in registros_gen:
        campos = {}

        frags_e = extraer_menciones_de(alumno, entradas)
        if frags_e:
            campos["Informe del dia"] = frags_e

        frags_m = extraer_menciones_de(alumno, mantenimiento)
        if frags_m:
            campos["Notes per direcció, manteniment i neteja"] = frags_m

        frags_t = extraer_menciones_de(alumno, temas)
        if frags_t:
            campos["Pícnics pel dia següent"] = frags_t

        if campos:
            menciones.append((fecha, cuidador, campos))

    if not registros_ind and not menciones:
        return None

    # Capçalera general
    elements.append(Paragraph("Residència Reina Sofia", estilo_titulo))
    elements.append(Paragraph(f"Històric individual - {alumno}", estilo_sub))
    elements.append(Spacer(1, 8))

    # A) Informes individuals
    if registros_ind:
        elements.append(Paragraph("A) Informes individuals", estilo_titulo_bloque))
        elements.append(Spacer(1, 6))

        for fecha, contenido in registros_ind:
            fecha_mostrar = datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m/%Y")
            elements.append(Paragraph(f"Informe del dia {fecha_mostrar}", estilo_fecha))
            elements.append(Paragraph((contenido or "—").replace("\n", "<br/>"), estilo_texto))
            elements.append(Spacer(1, 8))
            elements.append(Paragraph("<hr/>", estilo_texto))
            elements.append(Spacer(1, 4))

    # B) Mencions generals
    if menciones:
        elements.append(Spacer(1, 10))
        elements.append(Paragraph("B) Mencions als informes generals", estilo_titulo_bloque))
        elements.append(Spacer(1, 6))

        for fecha, cuidador, campos in menciones:
            fecha_mostrar = datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m/%Y")
            elements.append(Paragraph(f"Informe general del dia {fecha_mostrar}", estilo_fecha))
            elements.append(Paragraph(f"<b>Cuidador/a:</b> {cuidador or '—'}", estilo_texto))
            elements.append(Spacer(1, 4))

            for camp, fragments in campos.items():
                elements.append(Paragraph(f"<b>{camp}:</b>", estilo_titulo_bloque))
                for frag in fragments:
                    elements.append(Paragraph(frag.replace("\n", "<br/>"), estilo_texto))
                    elements.append(Spacer(1, 2))

            elements.append(Spacer(1, 8))
            elements.append(Paragraph("<hr/>", estilo_texto))
            elements.append(Spacer(1, 4))

    doc.build(elements)
    return fname


# =====================================================
#   HISTÒRIC GENERAL
# =====================================================

def generar_pdf_historico_general(desde, hasta):
    fname = os.path.join(
        PDFS_DIR,
        f"historico_general_{desde.strftime('%d-%m-%Y')}_a_{hasta.strftime('%d-%m-%Y')}.pdf"
    )
    doc = SimpleDocTemplate(
        fname,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )
    elements = []

    estilo_fecha = ParagraphStyle(name="Fecha", fontName="Helvetica-Bold", fontSize=13, spaceAfter=6)
    estilo_titulo = ParagraphStyle(name="Titulo", fontName="Helvetica-Bold", fontSize=12, spaceAfter=4)
    estilo_texto = ParagraphStyle(name="Texto", fontName="Helvetica", fontSize=10, leading=14)

    c.execute("""
        SELECT fecha, cuidador, entradas_salidas, mantenimiento, temas_genericos, taxis
        FROM informes
        WHERE fecha BETWEEN ? AND ?
        ORDER BY fecha ASC
    """, (desde.strftime("%Y-%m-%d"), hasta.strftime("%Y-%m-%d")))
    registros = c.fetchall()

    if not registros:
        return None

    elements.append(Paragraph(
        "Residència Reina Sofia",
        ParagraphStyle(name="TituloCab", alignment=TA_CENTER, fontName="Helvetica-Bold", fontSize=16)
    ))
    elements.append(Paragraph(
        "Històric d'informes generals",
        ParagraphStyle(name="SubCab", alignment=TA_CENTER, fontName="Helvetica", fontSize=12)
    ))
    elements.append(Spacer(1, 12))

    for fecha, cuidador, entradas, mantenimiento, temas, taxis_json in registros:
        fecha_mostrar = datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m/%Y")

        elements.append(Paragraph(f"Informe del dia {fecha_mostrar}", estilo_fecha))
        elements.append(Paragraph(f"<b>Cuidador/a:</b> {cuidador or '—'}", estilo_texto))
        elements.append(Spacer(1, 4))

        elements.append(Paragraph("<b>Informe del dia:</b>", estilo_titulo))
        elements.append(Paragraph((entradas or '—').replace("\n", "<br/>"), estilo_texto))

        elements.append(Paragraph("<b>Notes per direcció, manteniment i neteja:</b>", estilo_titulo))
        elements.append(Paragraph((mantenimiento or '—').replace("\n", "<br/>"), estilo_texto))

        elements.append(Paragraph("<b>Pícnics pel dia següent:</b>", estilo_titulo))
        elements.append(Paragraph((temas or '—').replace("\n", "<br/>"), estilo_texto))

        taxis_list = json.loads(taxis_json) if taxis_json else []
        if taxis_list:
            data = [["Data", "Hora", "Recollida", "Destí", "Esportistes", "Observacions"]]

            for t in taxis_list:
                fecha_raw = t.get("Fecha", "")
                try:
                    fecha_raw = datetime.strptime(fecha_raw, "%Y-%m-%d").strftime("%d/%m/%Y")
                except:
                    pass

                data.append([
                    fecha_raw,
                    t.get("Hora", ""),
                    t.get("Recogida", ""),
                    t.get("Destino", ""),
                    t.get("Deportistas", ""),
                    t.get("Observaciones", "")
                ])

            table = Table(data, colWidths=[2.3*cm, 2.3*cm, 3*cm, 3*cm, 3*cm, 3*cm])
            table.setStyle(TableStyle([("GRID", (0,0), (-1,-1), 0.5, colors.black)]))
            elements.append(table)

        elements.append(Spacer(1, 12))
        elements.append(Paragraph("<hr/>", estilo_texto))

    doc.build(elements)
    return fname


# =====================================================
#   HISTÒRIC TAXIS (PDF + DataFrame)
# =====================================================

def _recopilar_taxis_en_rang(desde, hasta):
    """
    Retorna una llista de files amb tots els taxis en el rang de dates.
    Cada fila és [data_informe, data_servei, hora, recollida, destí, esportistes, observacions]
    """
    c.execute("""
        SELECT fecha, taxis
        FROM informes
        WHERE fecha BETWEEN ? AND ?
        ORDER BY fecha ASC
    """, (desde.strftime("%Y-%m-%d"), hasta.strftime("%Y-%m-%d")))
    registros = c.fetchall()

    filas = []

    for fecha_informe, taxis_json in registros:
        taxis_list = json.loads(taxis_json) if taxis_json else []
        if not taxis_list:
            continue

        # Data de l'informe (YYYY-MM-DD -> dd/mm/aaaa)
        try:
            fecha_inf_dt = datetime.strptime(fecha_informe, "%Y-%m-%d")
            fecha_inf_str = fecha_inf_dt.strftime("%d/%m/%Y")
        except Exception:
            fecha_inf_str = fecha_informe

        for t in taxis_list:
            data_servei = t.get("Fecha", "") or ""
            hora = t.get("Hora", "") or ""
            recollida = t.get("Recogida", "") or ""
            desti = t.get("Destino", "") or ""
            esportistes = t.get("Deportistas", "") or ""
            observacions = t.get("Observaciones", "") or ""

            filas.append([
                fecha_inf_str,
                data_servei,
                hora,
                recollida,
                desti,
                esportistes,
                observacions
            ])

    return filas


def generar_pdf_historico_taxis(desde, hasta):
    filas = _recopilar_taxis_en_rang(desde, hasta)
    if not filas:
        return None

    fname = os.path.join(
        PDFS_DIR,
        f"historico_taxis_{desde.strftime('%d-%m-%Y')}_a_{hasta.strftime('%d-%m-%Y')}.pdf"
    )

    doc = SimpleDocTemplate(
        fname,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )
    elements = []

    estilo_titulo = ParagraphStyle(
        name="TituloTaxis",
        fontName="Helvetica-Bold",
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=8
    )
    estilo_sub = ParagraphStyle(
        name="SubTaxis",
        fontName="Helvetica",
        fontSize=12,
        alignment=TA_CENTER,
        spaceAfter=12
    )

    elements.append(Paragraph("Residència Reina Sofia", estilo_titulo))
    elements.append(Paragraph(
        f"Històric de serveis de taxi ({desde.strftime('%d/%m/%Y')} - {hasta.strftime('%d/%m/%Y')})",
        estilo_sub
    ))
    elements.append(Spacer(1, 8))

    data = [["Data informe", "Data servei", "Hora", "Recollida", "Destí", "Esportistes", "Observacions"]]
    data.extend(filas)

    table = Table(data, colWidths=[2.5*cm, 2.5*cm, 2*cm, 3*cm, 3*cm, 3*cm, 3*cm])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))

    elements.append(table)
    doc.build(elements)
    return fname


def obtener_historico_taxis_df(desde, hasta):
    filas = _recopilar_taxis_en_rang(desde, hasta)
    if not filas:
        return None

    columnas = [
        "Data informe",
        "Data servei",
        "Hora",
        "Recollida",
        "Destí",
        "Esportistes",
        "Observacions"
    ]
    df = pd.DataFrame(filas, columns=columnas)
    return df


# app.py - Bloque 10
# -----------------------
# Lógica principal
# -----------------------
import io

def main():
    # --- Autenticación de usuario ---
    if "usuario_autenticado" not in st.session_state or not st.session_state["usuario_autenticado"]:
        login()
        return

    # --- Barra lateral ---
    st.sidebar.markdown(f"👤 Usuari: **{st.session_state.get('usuario','').capitalize()}**")
    if st.sidebar.button("🔑 Canviar contrasenya"):
        st.session_state["vista_actual"] = "cambiar_contraseña"
        st.rerun()
    if st.sidebar.button("🚪 Tancar sessió"):
        logout()
        return

    vista = st.session_state.get("vista_actual", "menu")

    if vista == "menu":
        mostrar_menu()

    elif vista == "informe_general":
        formulario_informe_general()

    elif vista == "informe_individual":
        formulario_informe_individual()

    elif vista == "consultar_general":
        consultar_informe_general()

    elif vista == "consultar_individual":
        consultar_informe_individual()

    elif vista == "cambiar_contraseña":
        cambiar_contraseña()

    elif vista == "historico":
        st.header("🖨️ Imprimir històric d'informes")
        tipo = st.radio(
            "Seleccionar tipus d'històric",
            ["Històric individual", "Històric general", "Històric taxis"]
        )
        desde = st.date_input("Des de")
        hasta = st.date_input("Fins a")

        # ============================================================
        # HISTÓRICO INDIVIDUAL
        # ============================================================
        if tipo == "Històric individual":
            alumno = st.selectbox("Seleccionar esportista", ALUMNOS)
            if st.button("📄 Generar històric individual"):
                pdf = generar_pdf_historico_individual(alumno, desde, hasta)
                if pdf:
                    st.success(
                        f"✅ Històric generat correctament "
                        f"({desde.strftime('%d/%m/%Y')} - {hasta.strftime('%d/%m/%Y')})"
                    )
                    with open(pdf, "rb") as f:
                        st.download_button(
                            label="📥 Descarregar PDF",
                            data=f,
                            file_name=os.path.basename(pdf),
                            mime="application/pdf"
                        )
                else:
                    st.info("No hi ha informes en el rang seleccionat.")

        # ============================================================
        # HISTÓRICO GENERAL
        # ============================================================
        elif tipo == "Històric general":
            if st.button("📄 Generar històric general"):
                pdf = generar_pdf_historico_general(desde, hasta)
                if pdf:
                    st.success(
                        f"✅ Històric generat correctament "
                        f"({desde.strftime('%d/%m/%Y')} - {hasta.strftime('%d/%m/%Y')})"
                    )
                    with open(pdf, "rb") as f:
                        st.download_button(
                            label="📥 Descarregar PDF",
                            data=f,
                            file_name=os.path.basename(pdf),
                            mime="application/pdf"
                        )
                else:
                    st.info("No hi ha informes generals en aquest rang.")

        # ============================================================
        # HISTÓRICO TAXIS - PDF + EXCEL
        # ============================================================
        elif tipo == "Històric taxis":
            if st.button("🚕 Generar històric de taxis"):

                # PDF
                pdf = generar_pdf_historico_taxis(desde, hasta)

                # Excel (DataFrame)
                df_taxis = obtener_historico_taxis_df(desde, hasta)

                if not pdf and df_taxis is None:
                    st.info("No hi ha serveis de taxi en aquest rang.")
                else:
                    st.success(
                        f"✅ Històric generat correctament "
                        f"({desde.strftime('%d/%m/%Y')} - {hasta.strftime('%d/%m/%Y')})"
                    )

                    # ---- Botón PDF ----
                    if pdf:
                        with open(pdf, "rb") as f:
                            st.download_button(
                                label="📥 Descarregar PDF",
                                data=f,
                                file_name=os.path.basename(pdf),
                                mime="application/pdf"
                            )

                    # ---- Botón Excel ----
                    if df_taxis is not None:
                        buffer = io.BytesIO()
                        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                            df_taxis.to_excel(
                                writer,
                                index=False,
                                sheet_name="Taxis"
                            )
                        buffer.seek(0)

                        nombre_excel = (
                            f"historico_taxis_"
                            f"{desde.strftime('%d-%m-%Y')}_a_{hasta.strftime('%d-%m-%Y')}.xlsx"
                        )

                        st.download_button(
                            label="📊 Descarregar Excel",
                            data=buffer.getvalue(),
                            file_name=nombre_excel,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )

        # Botón volver al menú
        if st.button("🏠 Tornar al menú"):
            st.session_state["vista_actual"] = "menu"
            st.rerun()


if __name__ == "__main__":
    main()
