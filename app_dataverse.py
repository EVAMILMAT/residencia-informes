# =========================================================
# app_dataverse.py - BLOQUE 1
# =========================================================
import streamlit as st
from datetime import date, datetime
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
import hashlib
import requests

# -----------------------
# Configuración página
# -----------------------
st.set_page_config(page_title="Informes Residència", page_icon="🏠", layout="centered")
st.title("🏠 Gestió d'Informes - Residència Reina Sofia")

# Carpeta para almacenar PDFs
PDFS_DIR = "pdfs"
os.makedirs(PDFS_DIR, exist_ok=True)

# -----------------------
# Listas de cuidadores (se cargan desde Dataverse)
# -----------------------
# CUIDADORES: lista de nombres visibles en el select del informe general
# MAPA_USUARIO_A_CUIDADOR: mapea el "login" (usuari que entra) al nom de cuidador
CUIDADORES: list[str] = []
MAPA_USUARIO_A_CUIDADOR: dict[str, str] = {}

# -----------------------
# Alias de esportistes (des de Dataverse)
# -----------------------

def generar_alias(nombre_completo: str) -> str:
    """
    Genera un alias tipo @nombreInicialApellido a partir del nombre completo.
    Se usa solo como respaldo si en Dataverse no hay alias.
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

# Variables globales (se rellenan desde Dataverse)
ALUMNOS: list[str] = []
ALIAS_DEPORTISTAS: dict[str, str] = {}

# =========================================================
# app_dataverse.py - BLOQUE 2 (CLIENTE DATAVERSE) — CORREGIDO
# =========================================================

# -----------------------
# Configuración Dataverse
# -----------------------
DV_CFG = st.secrets["dataverse"]

TENANT_ID = DV_CFG["tenant_id"]
CLIENT_ID = DV_CFG["client_id"]
CLIENT_SECRET = DV_CFG["client_secret"]

RESOURCE = DV_CFG["resource"]
API_BASE = DV_CFG["api_base"]

ENTITY_INFORMES = DV_CFG["informes_entity_set"]          # p.ej. "cr143_informegenerals"
ENTITY_TAXIS = DV_CFG["taxis_entity_set"]                # p.ej. "cr143_taxis"
ENTITY_INDIV = DV_CFG["informes_ind_entity_set"]         # p.ej. "cr143_informeindividualses"
ENTITY_USUARIOS = DV_CFG["usuarios_entity_set"]          # p.ej. "cr143_usuarisaplicacios"
ENTITY_ALUMNOS = DV_CFG["alumnos_entity_set"]            # p.ej. "cr143_esportistas"

# Camp d'usuari per fer login i camp de nom visible
USU_LOGIN_FIELD = "cr143_nomusuariregistre"
USU_NAME_FIELD  = "cr143_nomusuari"

# Camps d'esportistes
ALUMNOS_NAME_FIELD  = "cr143_nomcomplet"
ALUMNOS_ALIAS_FIELD = "cr143_alias"  # nom lògic confirmat

# (Opcional però recomanat per evitar NameError si algun import falta a bloc 1)
import pandas as pd


class DataverseClient:
    def __init__(self):
        self._token: str | None = None

    # ----------------------------------------------
    # Autenticación OAuth2 client_credentials
    # ----------------------------------------------
    def _get_token(self) -> str:
        if self._token:
            return self._token

        url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
        data = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scope": f"{RESOURCE}/.default",
            "grant_type": "client_credentials",
        }

        resp = requests.post(url, data=data)
        if resp.status_code != 200:
            raise RuntimeError(f"Error obtenint token OAuth: {resp.status_code} - {resp.text}")

        self._token = resp.json()["access_token"]
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
        }

    # ----------------------------------------------
    # Helpers HTTP
    # ----------------------------------------------
    def get(self, endpoint: str, params: dict | None = None):
        r = requests.get(f"{API_BASE}/{endpoint}", headers=self._headers(), params=params)
        if r.status_code not in (200, 204):
            raise RuntimeError(f"GET {endpoint} → {r.status_code}: {r.text}")
        if not r.text:
            return None
        return r.json()

    def post(self, endpoint: str, payload: dict):
        r = requests.post(f"{API_BASE}/{endpoint}", headers=self._headers(), data=json.dumps(payload))
        if r.status_code not in (200, 201, 204):
            raise RuntimeError(f"POST {endpoint} → {r.status_code}: {r.text}")
        return r

    def patch(self, endpoint: str, payload: dict):
        r = requests.patch(f"{API_BASE}/{endpoint}", headers=self._headers(), data=json.dumps(payload))
        if r.status_code not in (200, 204):
            raise RuntimeError(f"PATCH {endpoint} → {r.status_code}: {r.text}")
        return r

    def delete(self, endpoint: str):
        r = requests.delete(f"{API_BASE}/{endpoint}", headers=self._headers())
        if r.status_code not in (200, 204):
            raise RuntimeError(f"DELETE {endpoint} → {r.status_code}: {r.text}")
        return r

    # =========================================================
    # 🔶 USUARIOS
    # =========================================================
    def _get_usuario_registro(self, usuario_login: str) -> dict | None:
        usuario_esc = usuario_login.replace("'", "''")
        filtro = f"{USU_LOGIN_FIELD} eq '{usuario_esc}'"
        endpoint = f"{ENTITY_USUARIOS}?$filter={filtro}"
        data = self.get(endpoint)
        if not data or not data.get("value"):
            return None
        return data["value"][0]

    def get_usuario_hash(self, usuario_login: str) -> str | None:
        rec = self._get_usuario_registro(usuario_login)
        if not rec:
            return None
        return rec.get("cr143_passwordhash")

    def set_usuario_hash(self, usuario_login: str, password_hash: str):
        usuario_esc = usuario_login.replace("'", "''")
        filtro = f"{USU_LOGIN_FIELD} eq '{usuario_esc}'"
        endpoint = f"{ENTITY_USUARIOS}?$filter={filtro}"
        data = self.get(endpoint)

        payload = {
            USU_LOGIN_FIELD: usuario_login,
            "cr143_passwordhash": password_hash,
        }

        if data and data.get("value"):
            rec_id = data["value"][0]["cr143_usuarisaplicacioid"]
            self.patch(f"{ENTITY_USUARIOS}({rec_id})", payload)
        else:
            self.post(ENTITY_USUARIOS, payload)

    def get_usuario_nombre_visible(self, usuario_login: str) -> str | None:
        rec = self._get_usuario_registro(usuario_login)
        if not rec:
            return None
        return (rec.get(USU_NAME_FIELD) or "").strip()

    # =========================================================
    # 🔶 INFORME GENERAL
    # =========================================================
    def get_informe_general(self, fecha_iso: str) -> dict | None:
        fecha_esc = fecha_iso.replace("'", "''")
        filtro = f"cr143_codigofecha eq '{fecha_esc}'"
        endpoint = f"{ENTITY_INFORMES}?$filter={filtro}"
        data = self.get(endpoint)
        if not data or not data.get("value"):
            return None

        rec = data["value"][0]
        return {
            "id": rec.get("cr143_informegeneralid"),
            "cuidador": rec.get("cr143_cuidador") or "",
            "entradas": rec.get("cr143_informedeldia") or "",
            "mantenimiento": rec.get("cr143_notesdireccio") or "",
            "temas": rec.get("cr143_picnics") or "",
        }

    def upsert_informe_general(self, fecha_iso: str, cuidador: str, entradas: str, mantenimiento: str, temas: str) -> str | None:
        existente = self.get_informe_general(fecha_iso)
        fecha_date = datetime.strptime(fecha_iso, "%Y-%m-%d").date().isoformat()

        payload = {
            "cr143_fechainforme": fecha_date,
            "cr143_codigofecha": fecha_iso,
            "cr143_cuidador": cuidador or "",
            "cr143_informedeldia": entradas or "",
            "cr143_notesdireccio": mantenimiento or "",
            "cr143_picnics": temas or "",
        }

        if existente and existente.get("id"):
            rec_id = existente["id"]
            self.patch(f"{ENTITY_INFORMES}({rec_id})", payload)
            return rec_id

        r = self.post(ENTITY_INFORMES, payload)
        location = r.headers.get("OData-EntityId") or r.headers.get("Location")
        if location and "(" in location and ")" in location:
            return location.split("(")[1].split(")")[0]
        return None

    # =========================================================
    # 🔶 TAXIS
    # =========================================================
    def get_taxis_by_informe(self, informe_id: str) -> list[dict]:
        if not informe_id:
            return []

        filtro = f"_cr143_informegeneral_value eq {informe_id}"
        endpoint = f"{ENTITY_TAXIS}?$filter={filtro}"
        data = self.get(endpoint)
        rows = data.get("value", []) if data else []

        taxis: list[dict] = []
        for rec in rows:
            fecha_txt = dv_date(rec.get("cr143_fecha"))


            taxis.append({
                "Fecha": fecha_txt,
                "Hora": rec.get("cr143_hora") or "",
                "Recogida": rec.get("cr143_recollida") or "",
                "Destino": rec.get("cr143_desti") or "",
                "Deportistas": rec.get("cr143_esportistes") or "",
                "Observaciones": rec.get("cr143_observacions") or "",
            })
        return taxis

    def replace_taxis_for_informe(self, informe_id: str, fecha_iso: str, taxis_list: list[dict]):
        """
        Borra todos los taxis asociados a ese informe y crea los nuevos.
        Sanea valores para evitar arrays en Dataverse.
        """
        if not informe_id:
            return

        def _to_text(v) -> str:
            if v is None:
                return ""
            try:
                if isinstance(v, float) and pd.isna(v):
                    return ""
            except Exception:
                pass
            if isinstance(v, (list, tuple, set)):
                return "\n".join([str(x) for x in v if x is not None])
            return str(v)

        filtro = f"_cr143_informegeneral_value eq {informe_id}"
        endpoint = f"{ENTITY_TAXIS}?$filter={filtro}"
        data = self.get(endpoint)
        rows = data.get("value", []) if data else []

        for rec in rows:
            taxi_id = rec["cr143_taxiid"]
            self.delete(f"{ENTITY_TAXIS}({taxi_id})")

        for t in taxis_list:
            fecha_txt = _to_text(t.get("Fecha") or fecha_iso).strip()

            fecha_iso_real = None
            for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
                try:
                    fecha_iso_real = datetime.strptime(fecha_txt, fmt).date().isoformat()
                    break
                except Exception:
                    pass
            if not fecha_iso_real:
                fecha_iso_real = datetime.strptime(fecha_iso, "%Y-%m-%d").date().isoformat()

            payload = {
                "cr143_fecha": fecha_iso_real,
                "cr143_hora": _to_text(t.get("Hora", "")).strip(),
                "cr143_recollida": _to_text(t.get("Recogida", "")).strip(),
                "cr143_desti": _to_text(t.get("Destino", "")).strip(),
                "cr143_esportistes": _to_text(t.get("Deportistas", "")).strip(),
                "cr143_observacions": _to_text(t.get("Observaciones", "")).strip(),
                "cr143_Informegeneral@odata.bind": f"/{ENTITY_INFORMES}({informe_id})",
            }
            self.post(ENTITY_TAXIS, payload)

    # =========================================================
    # 🔶 INFORMES INDIVIDUALS
    # =========================================================
    def get_informe_individual(self, fecha_iso: str, alumno: str) -> dict | None:
        fecha_esc = fecha_iso.replace("'", "''")
        alumno_esc = alumno.replace("'", "''")
        filtro = f"cr143_codigofecha eq '{fecha_esc}' and cr143_alumne eq '{alumno_esc}'"
        endpoint = f"{ENTITY_INDIV}?$filter={filtro}"
        data = self.get(endpoint)
        if not data or not data.get("value"):
            return None

        rec = data["value"][0]
        return {
            "id": rec.get("cr143_informeindividualsid"),
            "contenido": rec.get("cr143_congingut") or "",
        }

    def upsert_informe_individual(self, fecha_iso: str, alumno: str, alias: str, contenido: str) -> str | None:
        existente = self.get_informe_individual(fecha_iso, alumno)
        fecha_date = datetime.strptime(fecha_iso, "%Y-%m-%d").date().isoformat()

        payload = {
            "cr143_fechainforme": fecha_date,
            "cr143_codigofecha": fecha_iso,
            "cr143_alumne": alumno,
            "cr143_alias": alias or "",
            "cr143_congingut": contenido or "",
        }

        if existente and existente.get("id"):
            rec_id = existente["id"]
            self.patch(f"{ENTITY_INDIV}({rec_id})", payload)
            return rec_id

        r = self.post(ENTITY_INDIV, payload)
        location = r.headers.get("OData-EntityId") or r.headers.get("Location")
        if location and "(" in location and ")" in location:
            return location.split("(")[1].split(")")[0]
        return None

    def get_informes_individuales_por_alumno(self, alumno: str) -> list[tuple[str, str]]:
        alumno_esc = alumno.replace("'", "''")
        filtro = f"cr143_alumne eq '{alumno_esc}'"
        endpoint = f"{ENTITY_INDIV}?$filter={filtro}&$orderby=cr143_fechainforme desc"
        data = self.get(endpoint)
        rows = data.get("value", []) if data else []

        res: list[tuple[str, str]] = []
        for rec in rows:
           fecha_iso_out = dv_date(rec.get("cr143_fechainforme"))
            res.append((fecha_iso_out, rec.get("cr143_congingut") or ""))
        return res

    # =========================================================
    # 🔶 ALUMNOS (Esportistes)
    # =========================================================
    def get_alumnos(self) -> list[dict]:
        data = self.get(ENTITY_ALUMNOS)
        if not data or "value" not in data:
            return []

        rows = data["value"] or []
        res: list[dict] = []

        for rec in rows:
            nombre = (rec.get(ALUMNOS_NAME_FIELD) or "").strip()
            if not nombre:
                continue

            alias = ""
            if ALUMNOS_ALIAS_FIELD:
                alias = (rec.get(ALUMNOS_ALIAS_FIELD) or "").strip()

            res.append({"nombre": nombre, "alias": alias})

        return res

    # =========================================================
    # 🔶 HELPERS EXTRA
    # =========================================================
    def get_alumnos_con_informe_en_fecha(self, fecha_iso: str) -> list[str]:
        fecha_esc = fecha_iso.replace("'", "''")
        filtro = f"cr143_codigofecha eq '{fecha_esc}'"
        endpoint = f"{ENTITY_INDIV}?$filter={filtro}&$select=cr143_alumne"
        data = self.get(endpoint)

        alumnes: list[str] = []
        rows = data.get("value", []) if data else []
        for rec in rows:
            nom = (rec.get("cr143_alumne") or "").strip()
            if nom and nom not in alumnes:
                alumnes.append(nom)
        return alumnes

    def get_informes_generales_rango(self, desde_iso: str, hasta_iso: str) -> list[dict]:
        desde_esc = desde_iso.replace("'", "''")
        hasta_esc = hasta_iso.replace("'", "''")

        filtro = f"cr143_codigofecha ge '{desde_esc}' and cr143_codigofecha le '{hasta_esc}'"
        select = ",".join([
            "cr143_informegeneralid",
            "cr143_codigofecha",
            "cr143_cuidador",
            "cr143_informedeldia",
            "cr143_notesdireccio",
            "cr143_picnics",
        ])

        endpoint = (
            f"{ENTITY_INFORMES}"
            f"?$filter={filtro}"
            f"&$orderby=cr143_codigofecha asc"
            f"&$select={select}"
        )

        data = self.get(endpoint)
        rows = data.get("value", []) if data else []

        res: list[dict] = []
        for rec in rows:
            fecha_raw = (rec.get("cr143_codigofecha") or "").strip()
            fecha_iso_out = dv_date(rec.get("cr143_codigofecha"))


            res.append({
                "id": rec.get("cr143_informegeneralid"),
                "fecha": fecha_iso_out,
                "cuidador": rec.get("cr143_cuidador") or "",
                "entradas": rec.get("cr143_informedeldia") or "",
                "mantenimiento": rec.get("cr143_notesdireccio") or "",
                "temas": rec.get("cr143_picnics") or "",
            })
        return res

    def get_informes_generales_todos(self) -> list[dict]:
        select = ",".join([
            "cr143_informegeneralid",
            "cr143_codigofecha",
            "cr143_cuidador",
            "cr143_informedeldia",
            "cr143_notesdireccio",
            "cr143_picnics",
        ])
        endpoint = (
            f"{ENTITY_INFORMES}"
            f"?$orderby=cr143_codigofecha desc"
            f"&$select={select}"
        )

        data = self.get(endpoint)
        rows = data.get("value", []) if data else []

        res: list[dict] = []
        for rec in rows:
            fecha_raw = (rec.get("cr143_codigofecha") or "").strip()
            fecha_iso_out = dv_date(rec.get("cr143_codigofecha")) if fecha_raw else ""
            res.append({
                "id": rec.get("cr143_informegeneralid"),
                "fecha": fecha_iso_out,
                "cuidador": rec.get("cr143_cuidador") or "",
                "entradas": rec.get("cr143_informedeldia") or "",
                "mantenimiento": rec.get("cr143_notesdireccio") or "",
                "temas": rec.get("cr143_picnics") or "",
            })
        return res


# Instancia global del cliente Dataverse
DV = DataverseClient()

# =========================================================
# Càrrega d'esportistes (ALUMNOS + ALIAS_DEPORTISTAS)
# =========================================================

def cargar_alumnos_desde_dataverse():
    """
    Omple les globals:
      - ALUMNOS: llista de noms (ordenada)
      - ALIAS_DEPORTISTAS: dict {nom -> alias}
    """
    global ALUMNOS, ALIAS_DEPORTISTAS

    try:
        rows = DV.get_alumnos()  # [{nombre:..., alias:...}, ...]
    except Exception as e:
        st.error(f"Error carregant esportistes des de Dataverse: {e}")
        ALUMNOS = []
        ALIAS_DEPORTISTAS = {}
        return

    alumnos = []
    alias_map = {}

    for r in rows or []:
        nombre = (r.get("nombre") or "").strip()
        if not nombre:
            continue

        alias = (r.get("alias") or "").strip()
        alumnos.append(nombre)
        alias_map[nombre] = alias if alias else generar_alias(nombre)

    ALUMNOS = sorted(set(alumnos), key=lambda x: x.lower())
    ALIAS_DEPORTISTAS = alias_map

def dv_get_alumnos():
    return DV.get_alumnos()

def dv_date(value: str) -> str:
    """
    Convierte cualquier fecha de Dataverse a formato dd/mm/yyyy.
    Acepta:
      - 2025-12-15
      - 2025-12-15T00:00:00
      - 2025-12-15T00:00:00Z
    """
    if not value:
        return ""

    v = value.strip()

    # Dataverse suele devolver ...Z
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(v).date().strftime("%d/%m/%Y")
    except Exception:
        try:
            return datetime.strptime(v[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception:
            return ""







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

        # Estilos del contenido de celdas
        estilo_taxi = ParagraphStyle(
            name="TaxiCell",
            parent=bloque_texto,
            fontSize=9,
            leading=11,
            wordWrap='CJK'  # permite saltos automáticos según ancho de celda
        )

        estilo_header = ParagraphStyle(
            name="TaxiHeader",
            parent=bloque_titulo,
            fontSize=9,
            leading=11
        )

        # Cabecera
        taxis_data = [[
            Paragraph("<b>Data</b>", estilo_header),
            Paragraph("<b>Hora</b>", estilo_header),
            Paragraph("<b>Recollida</b>", estilo_header),
            Paragraph("<b>Destí</b>", estilo_header),
            Paragraph("<b>Esportistes</b>", estilo_header),
            Paragraph("<b>Observacions</b>", estilo_header),
        ]]

        # Filas
        for t in taxis_list:

            fecha_taxi = t.get("Fecha", "")
            if isinstance(fecha_taxi, str) and len(fecha_taxi.split("-")) == 3:
                try:
                    fecha_taxi = datetime.strptime(fecha_taxi, "%Y-%m-%d").strftime("%d/%m/%Y")
                except:
                    pass

            taxis_data.append([
                Paragraph(str(fecha_taxi), estilo_taxi),
                Paragraph(str(t.get("Hora", "") or ""), estilo_taxi),
                Paragraph(str(t.get("Recogida", "") or ""), estilo_taxi),
                Paragraph(str(t.get("Destino", "") or ""), estilo_taxi),
                Paragraph(str(t.get("Deportistas", "") or "").replace("\n", "<br/>"), estilo_taxi),
                Paragraph(str(t.get("Observaciones", "") or "").replace("\n", "<br/>"), estilo_taxi)
            ])

        tabla_taxis = Table(
            taxis_data,
            colWidths=[2.3*cm, 2.3*cm, 3*cm, 3*cm, 3*cm, 3*cm]
        )

        tabla_taxis.setStyle(TableStyle([
            ("GRID", (0,0), (-1,-1), 0.5, colors.black),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("ALIGN", (0,0), (-1,-1), "LEFT"),
            ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
            ("WORDWRAP", (0,0), (-1,-1), 1)
        ]))

        elements.append(tabla_taxis)

    # --- Generar PDF i tornar el nom de fitxer ---
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


# app_dataverse.py – Bloque 6
# -----------------------
# Funcions d'ajuda (adaptades a Dataverse)
# -----------------------

def limpiar_formulario_general():
    """
    Reinicia tot l'estat relacionat amb l'informe general i torna al menú.
    Pensat per si en un futur vols cridar-ho explícitament des d'algun botó.
    """
    # Estat antic (per compatibilitat, encara que ja no s'utilitza directament)
    st.session_state["form_general"] = {
        "fecha": "",
        "cuidador": "",
        "entradas": "",
        "mantenimiento": "",
        "temas": "",
        "taxis": []
    }

    # Estat nou usat al formulari d'informe general (Bloc 7)
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
    st.session_state["fecha_cargada"] = None
    st.session_state["bloqueado"] = False
    st.session_state["confirmar_salir_general"] = False
    st.session_state["informe_general_id"] = None

    # Tornar al menú
    st.session_state["vista_actual"] = "menu"


def limpiar_formulario_individual():
    """
    Reinicia tot l'estat relacionat amb l'informe individual i torna al menú.
    Pensat per si en un futur vols cridar-ho explícitament des d'algun botó.
    """
    # Estat antic (per compatibilitat, encara que ja no s'utilitza directament)
    st.session_state["form_individual"] = {
        "fecha": "",
        "alumno": "",
        "contenido": ""
    }

    # Estat nou usat al formulari d'informe individual (Bloc 8)
    st.session_state["forzar_edicion_individual"] = False
    st.session_state["alumno_actual_informe"] = ""
    st.session_state["confirmar_salir_individual"] = False

    # Tornar al menú
    st.session_state["vista_actual"] = "menu"


# -------------------------------------------------------
# Funcions de comprovació de sobrescriptura (Dataverse)
# No s'utilitzen directament als blocs nous, però
# queden disponibles per si les vols fer servir.
# -------------------------------------------------------

def comprobar_sobrescribir_general(fecha_iso: str) -> bool:
    """
    Indica si ja existeix un informe general per a aquesta data a Dataverse.
    Equivalent lògic a l'antic SELECT ... FROM informes WHERE fecha=?
    """
    try:
        informe = DV.get_informe_general(fecha_iso)
    except Exception as e:
        st.error(f"Error comprovant informe general a Dataverse: {e}")
        return False

    return informe is not None


def comprobar_sobrescribir_individual(fecha_iso: str, alumno: str) -> bool:
    """
    Indica si ja existeix un informe individual (data, alumne) a Dataverse.
    Equivalent lògic a l'antic SELECT ... FROM informes_alumnos WHERE ...
    """
    if not alumno:
        return False

    try:
        informe = DV.get_informe_individual(fecha_iso, alumno)
    except Exception as e:
        st.error(f"Error comprovant informe individual a Dataverse: {e}")
        return False

    return informe is not None

# app_dataverse.py – Bloque 7
# -----------------------
# Formulari Informe General (Dataverse)
# -----------------------

def obtener_cuidador_para_usuario_session() -> str:
    """
    A partir de l'usuari amb el qual s'ha fet login (st.session_state['usuario']),
    obté el nom de cuidador/a (Nom usuari) que s'ha de guardar a l'informe.

    - El login és el camp USU_LOGIN_FIELD (cr143_nomusuariregistre)
    - El nom visible ve de USU_NAME_FIELD (cr143_nomusuari)
    """
    usuario_login = st.session_state.get("usuario", "")
    if not usuario_login:
        return ""

    try:
        nombre_visible = DV.get_usuario_nombre_visible(usuario_login)
        # Si per qualsevol motiu no hi ha nom visible, fem servir el login com a últim recurs
        return nombre_visible or usuario_login
    except Exception as e:
        st.error(f"No s'ha pogut determinar el cuidador a partir de l'usuari: {e}")
        return usuario_login


def formulario_informe_general():
    st.header("🗓️ Introduir informe general")

    # Asseguram que els alumnes i àlies estiguin carregats
    if not ALUMNOS:
        cargar_alumnos_desde_dataverse()

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
    if "informe_general_id" not in st.session_state:
        st.session_state["informe_general_id"] = None

    # --- Data de l'informe ---
    fecha_sel = st.date_input("Data de l'informe", value=date.today(), key="fecha_general")
    fecha_iso = fecha_sel.isoformat()
    fecha_mostrar = fecha_sel.strftime("%d/%m/%Y")
    st.markdown(f"**Data seleccionada:** {fecha_mostrar}")

    # --- Carrega des de Dataverse quan canvia la data ---
    if st.session_state["fecha_cargada"] != fecha_iso:
        st.session_state["fecha_cargada"] = fecha_iso

        try:
            informe = DV.get_informe_general(fecha_iso)
        except Exception as e:
            st.error(f"Error llegint l'informe general des de Dataverse: {e}")
            informe = None

        if informe:
            # Hi ha informe a Dataverse → omplim i bloquejam
            st.session_state["informe_general"] = {
                "cuidador": informe.get("cuidador", "") or "",
                "entradas": informe.get("entradas", "") or "",
                "mantenimiento": informe.get("mantenimiento", "") or "",
                "temas": informe.get("temas", "") or "",
                "taxis": []
            }
            informe_id = informe.get("id")
            st.session_state["informe_general_id"] = informe_id

            # Carregam taxis associats a l'informe
            taxis = []
            if informe_id:
                try:
                    taxis = DV.get_taxis_by_informe(informe_id)
                except Exception as e:
                    st.error(f"Error llegint taxis des de Dataverse: {e}")
                    taxis = []

            st.session_state["informe_general"]["taxis"] = taxis
            st.session_state["taxis_df"] = pd.DataFrame(
                taxis,
                columns=["Fecha", "Hora", "Recogida", "Destino", "Deportistas", "Observaciones"]
            )
            st.session_state["bloqueado"] = True
        else:
            # No hi ha informe per aquest dia → formulari en blanc
            cuidador_sessio = obtener_cuidador_para_usuario_session()

            st.session_state["informe_general"] = {
                "cuidador": cuidador_sessio,
                "entradas": "",
                "mantenimiento": "",
                "temas": "",
                "taxis": []
            }
            st.session_state["taxis_df"] = pd.DataFrame(
                columns=["Fecha", "Hora", "Recogida", "Destino", "Deportistas", "Observaciones"]
            )
            st.session_state["bloqueado"] = False
            st.session_state["informe_general_id"] = None

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

        # Cuidador/a: només mostrar, no permetre canviar des del formulari
        cuidador_txt = st.text_input(
            "Cuidador/a",
            value=info.get("cuidador", ""),
            disabled=True
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
                    except Exception:
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
                    except Exception:
                        pass
                return v

            if "Fecha" in taxis_df.columns:
                taxis_df["Fecha"] = taxis_df["Fecha"].apply(normalizar_fecha)
            if "Hora" in taxis_df.columns:
                taxis_df["Hora"] = taxis_df["Hora"].apply(normalizar_hora)

            st.session_state["taxis_df"] = taxis_df

        # --- Informes individuals del dia (al final del formulari, abans de guardar) ---
        with st.expander("📑 Informes individuals d'aquest dia", expanded=False):
            try:
                alumnos_ind_dia = DV.get_alumnos_con_informe_en_fecha(fecha_iso)
            except Exception as e:
                st.error(f"Error llegint informes individuals del dia des de Dataverse: {e}")
                alumnos_ind_dia = []

            if alumnos_ind_dia:
                st.caption("Esportistes que tenen informe individual per aquesta data:")
                for a in alumnos_ind_dia:
                    st.markdown(f"- {a}")
            else:
                st.caption("Per ara no hi ha informes individuals registrats per aquesta data.")

        # Botones de guardar
        col_guardar_1, col_guardar_2 = st.columns(2)
        with col_guardar_1:
            submitted_enviar = st.form_submit_button("💾 Desar i enviar", disabled=disabled)
        with col_guardar_2:
            submitted_sense_enviar = st.form_submit_button("💾 Desar sense enviar", disabled=disabled)

    # --- Desar a Dataverse ---
    if submitted_enviar or submitted_sense_enviar:
        # Actualitzar informació a partir del formulari
        info["cuidador"] = cuidador_txt
        info["entradas"] = entradas_txt
        info["mantenimiento"] = mantenimiento_txt
        info["temas"] = temas_txt

        if not info["cuidador"]:
            st.warning(
                "⚠️ No s'ha pogut determinar el cuidador per aquesta sessió. "
                "Revisa la configuració de la taula d'usuaris a Dataverse."
            )
            return

        taxis_records = st.session_state["taxis_df"].to_dict("records")
        info["taxis"] = taxis_records

        try:
            # 1) Upsert informe general
            informe_id = DV.upsert_informe_general(
                fecha_iso,
                info["cuidador"],
                info["entradas"],
                info["mantenimiento"],
                info["temas"],
            )
            st.session_state["informe_general_id"] = informe_id

            # 2) Reemplaçar taxis associats
            DV.replace_taxis_for_informe(informe_id, fecha_iso, taxis_records)

            # 3) Llista d'alumnes amb informe individual aquell dia (per al PDF)
            alumnos = DV.get_alumnos_con_informe_en_fecha(fecha_iso)

        except Exception as e:
            st.error(f"Error desant l'informe general a Dataverse: {e}")
            return

        # Generar PDF
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
            st.success("✅ Informe desat a Dataverse i enviat per correu.")
        else:
            st.success("✅ Informe desat a Dataverse (sense enviar correu).")

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

        
# app_dataverse.py – Bloque 8
# -----------------------
# Formulari Informe Individual (Dataverse)
# -----------------------

def formulario_informe_individual():
    st.header("👤 Introduir informe individual")

    # Asseguram l'accés a les globals
    global ALUMNOS, ALIAS_DEPORTISTAS

    # Carregar sempre els alumnes des de Dataverse (per si l'estat s'ha perdut)
    try:
        cargar_alumnos_desde_dataverse()
    except Exception as e:
        st.error(f"No s'han pogut carregar els esportistes des de Dataverse: {e}")
        ALUMNOS = []

    # Control d'edició
    if "forzar_edicion_individual" not in st.session_state:
        st.session_state["forzar_edicion_individual"] = False
    if "alumno_actual_informe" not in st.session_state:
        st.session_state["alumno_actual_informe"] = ""
    if "confirmar_salir_individual" not in st.session_state:
        st.session_state["confirmar_salir_individual"] = False

    # -----------------------
    # Selecció de data
    # -----------------------
    fecha_sel = st.date_input("Data de l'informe", value=date.today(), key="fecha_individual")
    fecha_iso = fecha_sel.isoformat()

    # Data en format dd/mm/aaaa
    fecha_mostrar = fecha_sel.strftime("%d/%m/%Y")
    st.markdown(f"**Data seleccionada:** {fecha_mostrar}")

    # -----------------------
    # Llista d'alumnes amb opció en blanc
    # -----------------------
    if not ALUMNOS:
        st.warning("No s'han trobat esportistes a Dataverse.")
        if st.button("🏠 Tornar al menú", key="volver_menu_sense_alumnes"):
            st.session_state["vista_actual"] = "menu"
            st.rerun()
        return

    alumno_lista = [""] + ALUMNOS
    alumno = st.selectbox("Alumne", alumno_lista, index=0)

    # Si no s'ha seleccionat alumne
    if not alumno:
        st.info("Seleccionau un alumne per continuar.")
        if st.button("🏠 Tornar al menú", key="volver_menu_cap_alumne"):
            st.session_state["vista_actual"] = "menu"
            st.rerun()
        return

    # Si canviem d'alumne, sortim del mode edició forçada
    if alumno != st.session_state["alumno_actual_informe"]:
        st.session_state["alumno_actual_informe"] = alumno
        st.session_state["forzar_edicion_individual"] = False

    # ----------------------------------------------------
    # Comprovar si ja existeix informe (Dataverse) i carregar contingut
    # ----------------------------------------------------
    contenido_inicial = ""
    tiene_informe = False

    try:
        rec = DV.get_informe_individual(fecha_iso, alumno)
    except Exception as e:
        st.error(f"Error llegint informe individual des de Dataverse: {e}")
        rec = None

    if rec:
        tiene_informe = True
        contenido_inicial = rec.get("contenido", "") or ""

    bloqueado = tiene_informe and not st.session_state["forzar_edicion_individual"]

    # Missatge si l'informe existeix i està bloquejat
    if tiene_informe and bloqueado:
        st.info("🔒 Aquest informe ja existeix i està bloquejat per a l'edició.")
        if st.button("✏️ Editar informe existent"):
            st.session_state["forzar_edicion_individual"] = True
            st.rerun()

    # -----------------------
    # Camp de contingut
    # -----------------------
    contenido = st.text_area(
        "Contingut de l'informe",
        value=contenido_inicial,
        height=150,
        disabled=bloqueado
    )

    # -----------------------------------------
    # Funció interna per desar / eliminar i tornar al menú
    # -----------------------------------------
    def guardar_i_tornar(enviar=True):
        # Validació: alumne obligatori (per seguretat extra)
        if not alumno:
            st.warning("⚠️ Has de seleccionar un alumne abans de desar l'informe.")
            return

        alias = ALIAS_DEPORTISTAS.get(alumno) or generar_alias(alumno)
        contenido_norm = (contenido or "").strip()

        # 🔥 Si el contingut està buit → eliminar informe si existeix
        if contenido_norm == "":
            try:
                rec_exist = DV.get_informe_individual(fecha_iso, alumno)
            except Exception as e:
                st.error(f"Error comprovant l'informe individual a Dataverse: {e}")
                return

            if rec_exist and rec_exist.get("id"):
                try:
                    DV.delete(f"{ENTITY_INDIV}({rec_exist['id']})")
                except Exception as e:
                    st.error(f"Error eliminant l'informe individual a Dataverse: {e}")
                    return

            st.success(f"🗑️ Informe individual eliminat per al dia {fecha_mostrar}.")
            st.session_state["forzar_edicion_individual"] = False
            st.session_state["confirmar_salir_individual"] = False
            st.session_state["vista_actual"] = "menu"
            st.rerun()
            return

        # ✅ Si hi ha contingut → crear/actualitzar normalment
        try:
            DV.upsert_informe_individual(
                fecha_iso=fecha_iso,
                alumno=alumno,
                alias=alias,
                contenido=contenido_norm,
            )
        except Exception as e:
            st.error(f"Error desant l'informe individual a Dataverse: {e}")
            return

        data_text = fecha_sel.strftime("%d/%m/%Y")
        pdf = generar_pdf_individual(alumno, contenido_norm, fecha_iso)

        if enviar:
            enviar_correo(
                f"Informe individual - {alumno} - {data_text}",
                f"Adjunt informe individual de {alumno} ({data_text})",
                [pdf]
            )
            st.success(f"✅ Informe individual desat a Dataverse i enviat: {pdf}")
        else:
            st.success(f"✅ Informe individual desat a Dataverse (sense enviar correu): {pdf}")

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
    tiene_datos = (
        (alumno is not None and alumno != "") or
        (contenido is not None and contenido.strip() != "")
    )

    if st.session_state.get("confirmar_salir_individual", False):
        st.warning("⚠ Hi ha canvis sense desar. Vols desar l'informe abans de sortir?")

        col1, col2, col3 = st.columns(3)

        # Desar i sortir
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

        # Cancel·lar
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

# app_dataverse.py - Bloque 9
# -----------------------
# Consultes i Històrics (Dataverse)
# -----------------------

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from datetime import datetime
import re
import os
import json
import pandas as pd


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
#   CONSULTAR INFORME INDIVIDUAL I MENCIONS (Dataverse)
# =====================================================

def consultar_informe_individual():
    st.header("📄 Consultar informació d'un esportista")

    # Assegurar que la llista d'alumnes està carregada
    if not ALUMNOS:
        cargar_alumnos_desde_dataverse()

    # Selector d'esportista amb opció en blanc
    alumno_lista = [""] + ALUMNOS
    alumno = st.selectbox("Seleccionar esportista", alumno_lista, index=0)

    tipo = st.radio(
        "Tipus de consulta",
        ["Informes individuals", "Mencions als informes generals"],
        horizontal=True
    )

    if not alumno:
        st.info("Seleccionau un esportista per consultar la informació.")
        return

    # -------------------------------------------------
    # 1) INFORMES INDIVIDUALS (Dataverse)
    # -------------------------------------------------
    if tipo == "Informes individuals":

        try:
            # Llista de (fecha_iso, contenido) ordenada desc des de Dataverse
            registros = DV.get_informes_individuales_por_alumno(alumno)
        except Exception as e:
            st.error(f"Error llegint informes individuals de Dataverse: {e}")
            registros = []

        if not registros:
            st.info("No hi ha informes individuals per aquest esportista.")
        else:
            for fecha_iso, contenido in registros:
                if fecha_iso:
                    fecha_mostrar = datetime.strptime(fecha_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
                else:
                    fecha_mostrar = "—"

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
    # 2) MENCIONS EN INFORMES GENERALS (Dataverse)
    # -------------------------------------------------
    else:
        try:
            informes = DV.get_informes_generales_todos()
        except Exception as e:
            st.error(f"Error llegint informes generals de Dataverse: {e}")
            informes = []

        menciones = []

        for rec in informes:
            fecha = rec.get("fecha") or ""
            cuidador = rec.get("cuidador") or ""
            entradas = rec.get("entradas") or ""
            mantenimiento = rec.get("mantenimiento") or ""
            temas = rec.get("temas") or ""

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
            for fecha_iso, cuidador, campos in menciones:
                if fecha_iso:
                    fecha_mostrar = datetime.strptime(fecha_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
                else:
                    fecha_mostrar = "—"

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
#   CONSULTAR INFORME GENERAL (Dataverse)
# =====================================================

def consultar_informe_general():
    st.header("🔎 Consultar informe general")

    fecha_sel = st.date_input(
        "Selecciona la data de l'informe",
        value=date.today(),
        key="fecha_consulta_general"
    )
    fecha_iso = fecha_sel.isoformat()
    fecha_mostrar = fecha_sel.strftime("%d/%m/%Y")

    st.markdown(f"**Data seleccionada:** {fecha_mostrar}")

    try:
        informe = DV.get_informe_general(fecha_iso)
    except Exception as e:
        st.error(f"Error llegint informe general des de Dataverse: {e}")
        informe = None

    if not informe:
        st.info(f"No hi ha informe general guardat a Dataverse per a {fecha_mostrar}.")

        if st.button("🏠 Tornar al menú", key="volver_menu_general_consulta_sense_informe"):
            st.session_state["vista_actual"] = "menu"
            st.rerun()

        return

    cuidador = informe.get("cuidador") or ""
    entradas = informe.get("entradas") or ""
    mantenimiento = informe.get("mantenimiento") or ""
    temas = informe.get("temas") or ""
    informe_id = informe.get("id")

    try:
        taxis_list = DV.get_taxis_by_informe(informe_id) if informe_id else []
    except Exception as e:
        st.error(f"Error llegint taxis de Dataverse: {e}")
        taxis_list = []

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
#   HISTÒRIC INDIVIDUAL (AMB MENCIONS) – Dataverse
# =====================================================

def generar_pdf_historico_individual(alumno, desde, hasta):
    desde_iso = desde.strftime("%Y-%m-%d")
    hasta_iso = hasta.strftime("%Y-%m-%d")

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

    # Informes individuals (Dataverse)
    try:
        todos_ind = DV.get_informes_individuales_por_alumno(alumno)
    except Exception as e:
        st.error(f"Error llegint informes individuals de Dataverse: {e}")
        todos_ind = []

    registros_ind = []
    for fecha_iso_val, contenido in todos_ind:
        if not fecha_iso_val:
            continue
        if desde_iso <= fecha_iso_val <= hasta_iso:
            registros_ind.append((fecha_iso_val, contenido))

    # Mencions generals (Dataverse)
    try:
        informes_gen = DV.get_informes_generales_rango(desde_iso, hasta_iso)
    except Exception as e:
        st.error(f"Error llegint informes generals de Dataverse: {e}")
        informes_gen = []

    menciones = []

    for rec in informes_gen:
        fecha = rec.get("fecha") or ""
        cuidador = rec.get("cuidador") or ""
        entradas = rec.get("entradas") or ""
        mantenimiento = rec.get("mantenimiento") or ""
        temas = rec.get("temas") or ""

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

        for fecha_iso_val, contenido in registros_ind:
            fecha_mostrar = datetime.strptime(fecha_iso_val, "%Y-%m-%d").strftime("%d/%m/%Y")
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

        for fecha_iso_val, cuidador, campos in menciones:
            fecha_mostrar = datetime.strptime(fecha_iso_val, "%Y-%m-%d").strftime("%d/%m/%Y")
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
#   HISTÒRIC GENERAL – Dataverse
# =====================================================

def generar_pdf_historico_general(desde, hasta):
    desde_iso = desde.strftime("%Y-%m-%d")
    hasta_iso = hasta.strftime("%Y-%m-%d")

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

    try:
        registros = DV.get_informes_generales_rango(desde_iso, hasta_iso)
    except Exception as e:
        st.error(f"Error llegint informes generals de Dataverse: {e}")
        registros = []

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

    for rec in registros:
        fecha_iso_val = rec.get("fecha") or ""
        cuidador = rec.get("cuidador") or ""
        entradas = rec.get("entradas") or ""
        mantenimiento = rec.get("mantenimiento") or ""
        temas = rec.get("temas") or ""
        informe_id = rec.get("id")

        try:
            taxis_list = DV.get_taxis_by_informe(informe_id) if informe_id else []
        except Exception as e:
            st.error(f"Error llegint taxis de Dataverse: {e}")
            taxis_list = []

        fecha_mostrar = (
            datetime.strptime(fecha_iso_val, "%Y-%m-%d").strftime("%d/%m/%Y")
            if fecha_iso_val else "—"
        )

        elements.append(Paragraph(f"Informe del dia {fecha_mostrar}", estilo_fecha))
        elements.append(Paragraph(f"<b>Cuidador/a:</b> {cuidador or '—'}", estilo_texto))
        elements.append(Spacer(1, 4))

        elements.append(Paragraph("<b>Informe del dia:</b>", estilo_titulo))
        elements.append(Paragraph((entradas or '—').replace("\n", "<br/>"), estilo_texto))

        elements.append(Paragraph("<b>Notes per direcció, manteniment i neteja:</b>", estilo_titulo))
        elements.append(Paragraph((mantenimiento or '—').replace("\n", "<br/>"), estilo_texto))

        elements.append(Paragraph("<b>Pícnics pel dia següent:</b>", estilo_titulo))
        elements.append(Paragraph((temas or '—').replace("\n", "<br/>"), estilo_texto))

        # Taxis associats a aquest informe, amb data servei en dd/mm/yyyy
        if taxis_list:
            data = [["Data servei", "Hora", "Recollida", "Destí", "Esportistes", "Observacions"]]

            for t in taxis_list:
                fecha_raw = t.get("Fecha", "")
                try:
                    fecha_servicio_mostrar = datetime.strptime(fecha_raw, "%Y-%m-%d").strftime("%d/%m/%Y")
                except Exception:
                    fecha_servicio_mostrar = fecha_raw

                data.append([
                    fecha_servicio_mostrar,
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
#   HISTÒRIC TAXIS (PDF + DataFrame) – Dataverse
# =====================================================

def _recopilar_taxis_en_rang(desde, hasta):
    """
    Retorna una llista de files amb tots els taxis en el rang de dates (Dataverse).
    Cada fila és [data_informe, data_servei, hora, recollida, destí, esportistes, observacions]
    """
    desde_iso = desde.strftime("%Y-%m-%d")
    hasta_iso = hasta.strftime("%Y-%m-%d")

    try:
        informes = DV.get_informes_generales_rango(desde_iso, hasta_iso)
    except Exception as e:
        st.error(f"Error llegint informes generals per a taxis de Dataverse: {e}")
        informes = []

    filas = []

    for rec in informes:
        fecha_informe_iso = rec.get("fecha") or ""
        informe_id = rec.get("id")

        try:
            taxis_list = DV.get_taxis_by_informe(informe_id) if informe_id else []
        except Exception as e:
            st.error(f"Error llegint taxis de Dataverse: {e}")
            taxis_list = []

        try:
            fecha_inf_dt = datetime.strptime(fecha_informe_iso, "%Y-%m-%d")
            fecha_inf_str = fecha_inf_dt.strftime("%d/%m/%Y")
        except Exception:
            fecha_inf_str = fecha_informe_iso

        for t in taxis_list:
            # Data servei en dd/mm/yyyy
            fecha_raw = t.get("Fecha", "") or ""
            try:
                fecha_servicio_str = datetime.strptime(fecha_raw, "%Y-%m-%d").strftime("%d/%m/%Y")
            except Exception:
                fecha_servicio_str = fecha_raw

            hora = t.get("Hora", "") or ""
            recollida = t.get("Recogida", "") or ""
            desti = t.get("Destino", "") or ""
            esportistes = t.get("Deportistas", "") or ""
            observacions = t.get("Observaciones", "") or ""

            filas.append([
                fecha_inf_str,
                fecha_servicio_str,
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

# =========================================================
# AUTH: login / logout / cambiar contraseña (Dataverse)
# =========================================================

def _hash_password(pw: str) -> str:
    return hashlib.sha256((pw or "").encode("utf-8")).hexdigest()

def login():
    st.header("🔐 Accés a l'aplicació")

    if "usuario_autenticado" not in st.session_state:
        st.session_state["usuario_autenticado"] = False
    if "usuario" not in st.session_state:
        st.session_state["usuario"] = ""

    usuario = st.text_input("Usuari", key="login_usuario").strip().lower()
    password = st.text_input("Contrasenya", type="password", key="login_password")

    if st.button("Entrar", use_container_width=True):
        if not usuario or not password:
            st.warning("Introdueix usuari i contrasenya.")
            return

        pw_hash_introducido = _hash_password(password)

        # 1) Intentar validar con Dataverse (si ya hay hash)
        try:
            hash_guardado = DV.get_usuario_hash(usuario)
        except Exception as e:
            st.error(f"Error llegint usuari a Dataverse: {e}")
            return

        if hash_guardado:
            if pw_hash_introducido != hash_guardado:
                st.error("Contrasenya incorrecta.")
                return

            st.session_state["usuario_autenticado"] = True
            st.session_state["usuario"] = usuario
            st.session_state["vista_actual"] = "menu"
            st.rerun()

        # 2) Si no hay hash en Dataverse: fallback a secrets.toml [auth]
        auth = st.secrets.get("auth", {})
        pw_secret = (auth.get(usuario) or "").strip()

        if not pw_secret:
            st.error("Usuari no existent o sense contrasenya configurada.")
            return

        if password != pw_secret:
            st.error("Contrasenya incorrecta.")
            return

        # 3) Login OK por secrets → guardar hash en Dataverse para futuras sesiones
        try:
            DV.set_usuario_hash(usuario, pw_hash_introducido)
        except Exception as e:
            st.warning(f"⚠️ Login correcte, però no s'ha pogut guardar el hash a Dataverse: {e}")

        st.session_state["usuario_autenticado"] = True
        st.session_state["usuario"] = usuario
        st.session_state["vista_actual"] = "menu"
        st.rerun()


def logout():
    # Mantén lo mínimo; no borres secrets ni nada
    st.session_state["usuario_autenticado"] = False
    st.session_state["usuario"] = ""
    st.session_state["vista_actual"] = "menu"
    # Opcional: limpiar estado sensible
    for k in ["login_password"]:
        if k in st.session_state:
            st.session_state.pop(k, None)
    st.rerun()

def cambiar_contraseña():
    st.header("🔑 Canviar contrasenya")

    usuario = st.text_input("Usuari (login)", key="chg_usuario").strip().lower()
    pw1 = st.text_input("Nova contrasenya", type="password", key="chg_pw1")
    pw2 = st.text_input("Repetir nova contrasenya", type="password", key="chg_pw2")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Guardar", use_container_width=True):
            if not usuario or not pw1 or not pw2:
                st.warning("Omple tots els camps.")
                return
            if pw1 != pw2:
                st.error("Les contrasenyes no coincideixen.")
                return

            try:
                DV.set_usuario_hash(usuario, _hash_password(pw1))
            except Exception as e:
                st.error(f"Error guardant contrasenya a Dataverse: {e}")
                return

            st.success("✅ Contrasenya guardada.")
            # Si estaba logueado, no lo expulsamos; solo volvemos
            st.session_state["vista_actual"] = "menu"
            st.rerun()

    with col2:
        if st.button("🏠 Tornar al menú", use_container_width=True):
            st.session_state["vista_actual"] = "menu"
            st.rerun()







# app_dataverse.py - Bloque 10
# -----------------------
# Lógica principal
# -----------------------
import io

def main():
    # --- Autenticación de usuario ---
    if "usuario_autenticado" not in st.session_state or not st.session_state["usuario_autenticado"]:
        login()
        return

    # --- Càrrega d'esportistes des de Dataverse (una vegada per sessió) ---
    if "alumnos_cargados" not in st.session_state:
        cargar_alumnos_desde_dataverse()
        st.session_state["alumnos_cargados"] = True

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

        st.divider()

        # ============================================================
        # HISTÓRICO INDIVIDUAL (Dataverse)
        # ============================================================
        if tipo == "Històric individual":
            # Asegurar que la lista de alumnos está cargada
            if not ALUMNOS:
                cargar_alumnos_desde_dataverse()

            # Selector de esportista con opción en blanco
            alumno_lista = [""] + ALUMNOS
            alumno = st.selectbox("Seleccionar esportista", alumno_lista, index=0)

            if st.button("📄 Generar històric individual"):
                if not alumno:
                    st.warning("Has de seleccionar un esportista.")
                else:
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
        # HISTÓRICO GENERAL (Dataverse)
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
        # HISTÓRICO TAXIS - PDF + EXCEL (Dataverse)
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
