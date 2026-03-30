import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import ssl
import io
import urllib.request

# =========================================
# BYPASS SSL
# =========================================
ssl._create_default_https_context = ssl._create_unverified_context

st.set_page_config(
    page_title="Dashboard Seguimiento Repartos",
    layout="wide"
)

# =========================================
# CONFIG
# =========================================
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/18vbqYiBLv1M-F4JXg45Fn8E9a-rBYFfF/export?format=csv&gid=1737217651"

COLUMNAS_OBJETIVO = ["Fecha entrega", "Cliente", "Producto", "Total producto"]
DIAS_LABORALES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]

# sábado = 5
DIA_CORTE = 5

# =========================================
# ESTILO
# =========================================
st.markdown("""
<style>
.block-container {
    padding-top: 2rem;
    padding-bottom: 2rem;
    max-width: 1450px;
}
h1, h2, h3 {
    letter-spacing: -0.4px;
}
[data-testid="stMetric"] {
    background: #f7f7f9;
    border: 1px solid #e6e6ea;
    padding: 16px;
    border-radius: 14px;
}
</style>
""", unsafe_allow_html=True)

# =========================================
# FUNCIONES
# =========================================
def normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip() for c in df.columns]
    return df

def descargar_csv(url: str) -> str:
    with urllib.request.urlopen(url) as response:
        return response.read().decode("utf-8")

def encontrar_header(csv_texto: str, columnas_objetivo: list[str], max_filas: int = 30) -> int:
    preview = pd.read_csv(io.StringIO(csv_texto), header=None, nrows=max_filas, dtype=str)
    objetivo = {c.strip().lower() for c in columnas_objetivo}

    for i in range(len(preview)):
        fila = {
            str(v).strip().lower()
            for v in preview.iloc[i].tolist()
            if pd.notna(v)
        }
        if objetivo.issubset(fila):
            return i
    return -1

def limpiar_numeros(col: pd.Series) -> pd.Series:
    def convertir(x):
        s = str(x).strip()

        if s == "" or s.lower() == "nan":
            return 0.0

        s = s.replace("Gs", "").replace("₲", "").replace(" ", "")

        # Caso Paraguay: 83.875 / 1.250.000
        if "." in s and "," not in s:
            partes = s.split(".")
            if len(partes) > 1 and all(len(p) == 3 for p in partes[1:]):
                s = "".join(partes)
                try:
                    return float(s)
                except:
                    return 0.0

        # Caso europeo: 1.234,56
        if "." in s and "," in s:
            s = s.replace(".", "").replace(",", ".")
            try:
                return float(s)
            except:
                return 0.0

        # Caso decimal con coma
        if "," in s and "." not in s:
            partes = s.split(",")
            if len(partes) > 1 and all(len(p) == 3 for p in partes[1:]):
                s = "".join(partes)
                try:
                    return float(s)
                except:
                    return 0.0
            else:
                s = s.replace(",", ".")
                try:
                    return float(s)
                except:
                    return 0.0

        try:
            return float(s)
        except:
            return 0.0

    return col.apply(convertir)

def formatear_entero(x) -> str:
    try:
        return f"{int(round(float(x))):,}".replace(",", ".")
    except:
        return ""

def nombre_dia_es(fecha) -> str:
    dias = {
        0: "Lunes",
        1: "Martes",
        2: "Miércoles",
        3: "Jueves",
        4: "Viernes",
        5: "Sábado",
        6: "Domingo",
    }
    return dias[fecha.weekday()]

def obtener_domingo_de_semana(fecha):
    dias_desde_domingo = (fecha.weekday() + 1) % 7
    return fecha - timedelta(days=dias_desde_domingo)

def obtener_rango_semana_objetivo():
    """
    Lógica operativa:
    - domingo a viernes: mostrar semana actual de reparto
    - sábado en adelante: mostrar semana siguiente
    """
    hoy = datetime.today().date()

    domingo_actual = obtener_domingo_de_semana(hoy)
    sabado_actual = domingo_actual + timedelta(days=6)

    if hoy.weekday() >= DIA_CORTE:
        domingo_objetivo = domingo_actual + timedelta(days=7)
        sabado_objetivo = domingo_objetivo + timedelta(days=6)
    else:
        domingo_objetivo = domingo_actual
        sabado_objetivo = sabado_actual

    return domingo_objetivo, sabado_objetivo

@st.cache_data(ttl=120)
def cargar_datos():
    csv_texto = descargar_csv(GOOGLE_SHEET_CSV_URL)
    fila_header = encontrar_header(csv_texto, COLUMNAS_OBJETIVO)

    if fila_header == -1:
        raise ValueError("No encontré la fila de encabezados en la hoja.")

    df = pd.read_csv(io.StringIO(csv_texto), header=fila_header, dtype=str)
    df = normalizar_columnas(df)

    faltantes = [c for c in COLUMNAS_OBJETIVO if c not in df.columns]
    if faltantes:
        raise ValueError(f"Faltan columnas: {faltantes}. Columnas detectadas: {list(df.columns)}")

    df["Fecha entrega"] = pd.to_datetime(df["Fecha entrega"], errors="coerce", dayfirst=True)
    df["Cliente"] = df["Cliente"].astype(str).str.strip()
    df["Producto"] = df["Producto"].astype(str).str.strip()
    df["Total producto"] = limpiar_numeros(df["Total producto"])

    if "Vende" in df.columns and "Vendedora" not in df.columns:
        df["Vendedora"] = df["Vende"]

    if "Vendedora" not in df.columns:
        df["Vendedora"] = "Sin asignar"

    df["Vendedora"] = df["Vendedora"].astype(str).str.strip()
    df["Vendedora"] = df["Vendedora"].replace("", "Sin asignar").fillna("Sin asignar")

    df = df.dropna(subset=["Fecha entrega"])
    df = df[df["Cliente"] != ""]
    df = df[df["Cliente"].str.lower() != "nan"]

    return df, fila_header

# =========================================
# CARGA
# =========================================
try:
    df, fila_header = cargar_datos()
except Exception as e:
    st.error(f"No pude leer la base: {e}")
    st.stop()

domingo_objetivo, sabado_objetivo = obtener_rango_semana_objetivo()

# =========================================
# DIAGNÓSTICO
# =========================================
with st.expander("Ver diagnóstico de lectura"):
    st.write(f"Fila de encabezado detectada: {fila_header + 1}")
    st.write("Columnas detectadas:")
    st.write(list(df.columns))
    st.write(f"Semana objetivo de seguimiento: {domingo_objetivo.strftime('%d/%m/%Y')} a {sabado_objetivo.strftime('%d/%m/%Y')}")
    st.dataframe(df.head(10), use_container_width=True, hide_index=True)

# =========================================
# PEDIDOS POR FECHA
# =========================================
pedidos_por_fecha = (
    df.groupby(["Cliente", "Vendedora", "Fecha entrega"], as_index=False)["Total producto"]
    .sum()
    .rename(columns={"Total producto": "Total pedido"})
)

# =========================================
# RESUMEN HISTÓRICO
# =========================================
resumen = (
    pedidos_por_fecha.groupby(["Cliente", "Vendedora"], as_index=False)
    .agg(
        ultima_fecha_pedido=("Fecha entrega", "max"),
        pedido_promedio=("Total pedido", "mean")
    )
)

# =========================================
# SEMANA OBJETIVO
# =========================================
pedidos_semana = pedidos_por_fecha[
    (pedidos_por_fecha["Fecha entrega"].dt.date >= domingo_objetivo) &
    (pedidos_por_fecha["Fecha entrega"].dt.date <= sabado_objetivo)
].copy()

pedidos_semana["Dia"] = pedidos_semana["Fecha entrega"].apply(nombre_dia_es)
pedidos_semana = pedidos_semana[pedidos_semana["Dia"].isin(DIAS_LABORALES)]

if not pedidos_semana.empty:
    pivot_semana = pedidos_semana.pivot_table(
        index=["Cliente", "Vendedora"],
        columns="Dia",
        values="Total pedido",
        aggfunc="sum"
    ).reset_index()
else:
    pivot_semana = pd.DataFrame(columns=["Cliente", "Vendedora"] + DIAS_LABORALES)

for dia in DIAS_LABORALES:
    if dia not in pivot_semana.columns:
        pivot_semana[dia] = 0

# =========================================
# BASE FINAL
# =========================================
dashboard = resumen.merge(
    pivot_semana,
    on=["Cliente", "Vendedora"],
    how="left"
)

for dia in DIAS_LABORALES:
    dashboard[dia] = dashboard[dia].fillna(0)

dashboard["Última fecha pedido"] = pd.to_datetime(
    dashboard["ultima_fecha_pedido"], errors="coerce"
).dt.strftime("%d/%m/%Y")

dashboard["Última fecha pedido"] = dashboard["Última fecha pedido"].fillna("")
dashboard["Pedido promedio num"] = dashboard["pedido_promedio"].fillna(0)

dashboard["Tiene pedido"] = (
    (dashboard["Lunes"] > 0) |
    (dashboard["Martes"] > 0) |
    (dashboard["Miércoles"] > 0) |
    (dashboard["Jueves"] > 0) |
    (dashboard["Viernes"] > 0)
)

dashboard = dashboard.sort_values(
    by=["Tiene pedido", "Pedido promedio num"],
    ascending=[True, False]
)

dashboard_mostrar = dashboard[[
    "Cliente",
    "Última fecha pedido",
    "Pedido promedio num",
    "Vendedora",
    "Lunes",
    "Martes",
    "Miércoles",
    "Jueves",
    "Viernes",
    "Tiene pedido"
]].copy()

dashboard_mostrar = dashboard_mostrar.rename(columns={"Pedido promedio num": "Pedido promedio"})
dashboard_mostrar["Pedido promedio"] = dashboard_mostrar["Pedido promedio"].apply(formatear_entero)

for dia in DIAS_LABORALES:
    dashboard_mostrar[dia] = dashboard_mostrar[dia].apply(lambda x: formatear_entero(x) if x > 0 else "")

# =========================================
# UI
# =========================================
st.title("Dashboard de Seguimiento de Clientes - Repartos")
st.caption(f"Semana objetivo: {domingo_objetivo.strftime('%d/%m/%Y')} a {sabado_objetivo.strftime('%d/%m/%Y')}")

st.sidebar.header("Filtros")
vendedoras = ["Todas"] + sorted(dashboard_mostrar["Vendedora"].dropna().unique().tolist())
filtro_vendedora = st.sidebar.selectbox("Vendedora", vendedoras)

if filtro_vendedora != "Todas":
    dashboard_filtrado = dashboard_mostrar[dashboard_mostrar["Vendedora"] == filtro_vendedora].copy()
else:
    dashboard_filtrado = dashboard_mostrar.copy()

# =========================================
# SEPARAR CARGADOS / NO CARGADOS
# =========================================
clientes_cargados = dashboard_filtrado[dashboard_filtrado["Tiene pedido"]].copy()
clientes_no_cargados = dashboard_filtrado[~dashboard_filtrado["Tiene pedido"]].copy()

# =========================================
# KPIs
# =========================================
col1, col2, col3 = st.columns(3)
col1.metric("Clientes totales", len(dashboard_filtrado))
col2.metric("Con pedido cargado para esa semana", len(clientes_cargados))
col3.metric("Sin pedido cargado para esa semana", len(clientes_no_cargados))

# =========================================
# TABLA 1: SOLO CLIENTES CARGADOS
# =========================================
st.subheader("Seguimiento general")

clientes_cargados_mostrar = clientes_cargados[[
    "Cliente",
    "Última fecha pedido",
    "Pedido promedio",
    "Vendedora",
    "Lunes",
    "Martes",
    "Miércoles",
    "Jueves",
    "Viernes"
]].copy()

st.dataframe(clientes_cargados_mostrar, use_container_width=True, hide_index=True)

# =========================================
# TABLA 2: SOLO CLIENTES SIN PEDIDO
# =========================================
st.subheader("Clientes sin pedido para esa semana")

clientes_no_cargados_mostrar = clientes_no_cargados[[
    "Cliente",
    "Última fecha pedido",
    "Pedido promedio",
    "Vendedora",
    "Lunes",
    "Martes",
    "Miércoles",
    "Jueves",
    "Viernes"
]].copy()

for dia in DIAS_LABORALES:
    clientes_no_cargados_mostrar[dia] = ""

st.dataframe(clientes_no_cargados_mostrar, use_container_width=True, hide_index=True)
