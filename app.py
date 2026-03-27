import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import ssl
import io
import urllib.request

# =========================
# BYPASS SSL PARA MAC
# =========================
ssl._create_default_https_context = ssl._create_unverified_context

st.set_page_config(
    page_title="Dashboard Seguimiento Repartos",
    layout="wide"
)

# =========================
# ESTILO
# =========================
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

st.title("Dashboard de Seguimiento de Clientes - Repartos")

# =========================
# CONFIG
# =========================
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/18vbqYiBLv1M-F4JXg45Fn8E9a-rBYFfF/export?format=csv&gid=1737217651"

COLUMNAS_OBJETIVO = ["Fecha entrega", "Cliente", "Producto", "Total producto"]
DIAS_LABORALES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]

# =========================
# FUNCIONES
# =========================
def normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(col).strip() for col in df.columns]
    return df

def obtener_rango_semana_actual():
    hoy = datetime.today()
    lunes = hoy - timedelta(days=hoy.weekday())
    viernes = lunes + timedelta(days=4)
    return lunes.date(), viernes.date()

def nombre_dia_es(fecha):
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

def limpiar_monto(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(
        serie.astype(str)
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
        .str.replace("Gs", "", regex=False)
        .str.strip(),
        errors="coerce"
    ).fillna(0)

def descargar_csv_como_texto(url: str) -> str:
    with urllib.request.urlopen(url) as response:
        return response.read().decode("utf-8")

def encontrar_fila_encabezado(csv_texto: str, columnas_objetivo: list[str], max_filas: int = 20) -> int:
    preview = pd.read_csv(io.StringIO(csv_texto), header=None, nrows=max_filas)

    columnas_objetivo_lower = {c.strip().lower() for c in columnas_objetivo}

    for i in range(len(preview)):
        valores_fila = {
            str(v).strip().lower()
            for v in preview.iloc[i].tolist()
            if pd.notna(v)
        }
        if columnas_objetivo_lower.issubset(valores_fila):
            return i

    return -1

@st.cache_data(ttl=120)
def cargar_pedidos(url: str) -> tuple[pd.DataFrame, int, list]:
    csv_texto = descargar_csv_como_texto(url)

    fila_header = encontrar_fila_encabezado(csv_texto, COLUMNAS_OBJETIVO)

    if fila_header == -1:
        preview = pd.read_csv(io.StringIO(csv_texto), header=None, nrows=10)
        raise ValueError(
            "No encontré automáticamente la fila de encabezados. "
            f"Primeras filas detectadas: {preview.values.tolist()}"
        )

    df = pd.read_csv(io.StringIO(csv_texto), header=fila_header)
    df = normalizar_columnas(df)
    return df, fila_header, list(df.columns)

# =========================
# CARGA DE DATOS
# =========================
try:
    pedidos, fila_header_detectada, columnas_detectadas = cargar_pedidos(GOOGLE_SHEET_CSV_URL)
except Exception as e:
    st.error(f"No pude leer la hoja de Google Sheets: {e}")
    st.stop()

with st.expander("Ver diagnóstico de lectura"):
    st.write(f"Fila de encabezado detectada automáticamente: {fila_header_detectada + 1}")
    st.write("Columnas detectadas:")
    st.write(columnas_detectadas)

# =========================
# VALIDACIÓN DE COLUMNAS
# =========================
faltantes_pedidos = [c for c in COLUMNAS_OBJETIVO if c not in pedidos.columns]

if faltantes_pedidos:
    st.error(f"Faltan columnas en la hoja Detalle: {faltantes_pedidos}")
    st.stop()

# =========================
# LIMPIEZA
# =========================
pedidos["Fecha entrega"] = pd.to_datetime(
    pedidos["Fecha entrega"],
    errors="coerce",
    dayfirst=True
)

pedidos["Cliente"] = pedidos["Cliente"].astype(str).str.strip()
pedidos["Producto"] = pedidos["Producto"].astype(str).str.strip()
pedidos["Total producto"] = limpiar_monto(pedidos["Total producto"])

pedidos = pedidos.dropna(subset=["Fecha entrega"])
pedidos = pedidos[pedidos["Cliente"] != ""]
pedidos = pedidos[pedidos["Cliente"].str.lower() != "nan"]

# =========================
# VENDEDORA
# =========================
if "Vendedora" not in pedidos.columns:
    pedidos["Vendedora"] = "Sin asignar"
else:
    pedidos["Vendedora"] = pedidos["Vendedora"].astype(str).str.strip()
    pedidos["Vendedora"] = pedidos["Vendedora"].replace("", "Sin asignar")
    pedidos["Vendedora"] = pedidos["Vendedora"].fillna("Sin asignar")

# =========================
# PEDIDO TOTAL POR CLIENTE Y FECHA
# =========================
pedidos_por_fecha = (
    pedidos.groupby(["Cliente", "Vendedora", "Fecha entrega"], as_index=False)["Total producto"]
    .sum()
    .rename(columns={"Total producto": "Total pedido"})
)

# =========================
# RESUMEN HISTÓRICO
# =========================
resumen_historico = (
    pedidos_por_fecha.groupby(["Cliente", "Vendedora"], as_index=False)
    .agg(
        ultima_fecha_pedido=("Fecha entrega", "max"),
        pedido_promedio=("Total pedido", "mean")
    )
)

# =========================
# SEMANA ACTUAL
# =========================
lunes_semana, viernes_semana = obtener_rango_semana_actual()

pedidos_semana = pedidos_por_fecha[
    (pedidos_por_fecha["Fecha entrega"].dt.date >= lunes_semana) &
    (pedidos_por_fecha["Fecha entrega"].dt.date <= viernes_semana)
].copy()

pedidos_semana["Dia"] = pedidos_semana["Fecha entrega"].apply(nombre_dia_es)
pedidos_semana = pedidos_semana[pedidos_semana["Dia"].isin(DIAS_LABORALES)]

if not pedidos_semana.empty:
    pedidos_semana["Monto dia"] = pedidos_semana["Total pedido"].round(0).astype(int)

    pivot_semana = pedidos_semana.pivot_table(
        index=["Cliente", "Vendedora"],
        columns="Dia",
        values="Monto dia",
        aggfunc="sum"
    ).reset_index()
else:
    pivot_semana = pd.DataFrame(columns=["Cliente", "Vendedora"] + DIAS_LABORALES)

for dia in DIAS_LABORALES:
    if dia not in pivot_semana.columns:
        pivot_semana[dia] = 0

# =========================
# BASE FINAL
# =========================
dashboard = resumen_historico.merge(
    pivot_semana,
    on=["Cliente", "Vendedora"],
    how="left"
)

for dia in DIAS_LABORALES:
    dashboard[dia] = dashboard[dia].fillna(0).astype(int)

dashboard["Última fecha pedido"] = pd.to_datetime(
    dashboard["ultima_fecha_pedido"],
    errors="coerce"
).dt.strftime("%d/%m/%Y")

dashboard["Última fecha pedido"] = dashboard["Última fecha pedido"].fillna("")
dashboard["Pedido promedio"] = dashboard["pedido_promedio"].fillna(0).round(0).astype(int)

dashboard["Tiene pedido"] = (
    (dashboard["Lunes"] > 0) |
    (dashboard["Martes"] > 0) |
    (dashboard["Miércoles"] > 0) |
    (dashboard["Jueves"] > 0) |
    (dashboard["Viernes"] > 0)
)

dashboard = dashboard.sort_values(
    by=["Tiene pedido", "Pedido promedio"],
    ascending=[True, False]
)

dashboard_mostrar = dashboard[[
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
    dashboard_mostrar[dia] = dashboard_mostrar[dia].replace(0, "")

# =========================
# FILTROS
# =========================
st.sidebar.header("Filtros")

vendedoras = ["Todas"] + sorted(dashboard_mostrar["Vendedora"].dropna().unique().tolist())
filtro_vendedora = st.sidebar.selectbox("Vendedora", vendedoras)

if filtro_vendedora != "Todas":
    dashboard_filtrado = dashboard_mostrar[dashboard_mostrar["Vendedora"] == filtro_vendedora].copy()
    dashboard_base_filtrado = dashboard[dashboard["Vendedora"] == filtro_vendedora].copy()
else:
    dashboard_filtrado = dashboard_mostrar.copy()
    dashboard_base_filtrado = dashboard.copy()

# =========================
# KPIS
# =========================
clientes_total = len(dashboard_base_filtrado)
clientes_con_pedido = dashboard_base_filtrado[dashboard_base_filtrado["Tiene pedido"]].copy()
clientes_sin_pedido = dashboard_base_filtrado[~dashboard_base_filtrado["Tiene pedido"]].copy()

col1, col2, col3 = st.columns(3)
col1.metric("Clientes totales", clientes_total)
col2.metric("Con pedido esta semana", len(clientes_con_pedido))
col3.metric("Sin pedido esta semana", len(clientes_sin_pedido))

# =========================
# TABLAS
# =========================
st.subheader("Seguimiento general")
st.dataframe(
    dashboard_filtrado,
    use_container_width=True,
    hide_index=True
)

st.subheader("Clientes sin pedido esta semana")
clientes_sin_pedido_mostrar = clientes_sin_pedido[[
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
    clientes_sin_pedido_mostrar[dia] = ""

st.dataframe(
    clientes_sin_pedido_mostrar,
    use_container_width=True,
    hide_index=True
)
