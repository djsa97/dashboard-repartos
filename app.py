import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import ssl
import io
import urllib.request

ssl._create_default_https_context = ssl._create_unverified_context

st.set_page_config(page_title="Dashboard Repartos", layout="wide")

GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/18vbqYiBLv1M-F4JXg45Fn8E9a-rBYFfF/export?format=csv&gid=1737217651"

COLUMNAS_OBJETIVO = ["Fecha entrega", "Cliente", "Producto", "Total producto"]
DIAS_LABORALES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]

def normalizar_columnas(df):
    df.columns = [str(c).strip() for c in df.columns]
    return df

def limpiar_numeros(col):
    return pd.to_numeric(
        col.astype(str)
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
        .str.replace("Gs", "", regex=False)
        .str.strip(),
        errors="coerce"
    ).fillna(0)

def descargar_csv(url):
    with urllib.request.urlopen(url) as response:
        return response.read().decode("utf-8")

def encontrar_header(csv_texto, columnas_objetivo, max_filas=20):
    preview = pd.read_csv(io.StringIO(csv_texto), header=None, nrows=max_filas)
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

@st.cache_data(ttl=120)
def cargar_datos():
    csv_texto = descargar_csv(GOOGLE_SHEET_CSV_URL)
    fila_header = encontrar_header(csv_texto, COLUMNAS_OBJETIVO)

    if fila_header == -1:
        raise ValueError("No encontré la fila de encabezados en la hoja.")

    df = pd.read_csv(io.StringIO(csv_texto), header=fila_header)
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

    df["Vendedora"] = df["Vendedora"].astype(str).str.strip().replace("", "Sin asignar")

    df = df.dropna(subset=["Fecha entrega"])
    df = df[df["Cliente"] != ""]
    df = df[df["Cliente"].str.lower() != "nan"]

    return df, fila_header

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

def obtener_rango_semana_actual():
    hoy = datetime.today()
    lunes = hoy - timedelta(days=hoy.weekday())
    viernes = lunes + timedelta(days=4)
    return lunes.date(), viernes.date()

try:
    df, fila_header = cargar_datos()
except Exception as e:
    st.error(f"No pude leer la base: {e}")
    st.stop()

with st.expander("Ver diagnóstico de lectura"):
    st.write(f"Fila de encabezado detectada: {fila_header + 1}")
    st.write(list(df.columns))

pedidos_por_fecha = (
    df.groupby(["Cliente", "Vendedora", "Fecha entrega"], as_index=False)["Total producto"]
    .sum()
    .rename(columns={"Total producto": "Total pedido"})
)

resumen = (
    pedidos_por_fecha.groupby(["Cliente", "Vendedora"], as_index=False)
    .agg(
        ultima_fecha_pedido=("Fecha entrega", "max"),
        pedido_promedio=("Total pedido", "mean")
    )
)

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

dashboard = resumen.merge(pivot_semana, on=["Cliente", "Vendedora"], how="left")

for dia in DIAS_LABORALES:
    dashboard[dia] = dashboard[dia].fillna(0).astype(int)

dashboard["Última fecha pedido"] = pd.to_datetime(
    dashboard["ultima_fecha_pedido"], errors="coerce"
).dt.strftime("%d/%m/%Y").fillna("")

dashboard["Pedido promedio"] = dashboard["pedido_promedio"].fillna(0).round(0).astype(int)

dashboard["Tiene pedido"] = (
    (dashboard["Lunes"] > 0) |
    (dashboard["Martes"] > 0) |
    (dashboard["Miércoles"] > 0) |
    (dashboard["Jueves"] > 0) |
    (dashboard["Viernes"] > 0)
)

dashboard = dashboard.sort_values(by=["Tiene pedido", "Pedido promedio"], ascending=[True, False])

dashboard_mostrar = dashboard[[
    "Cliente", "Última fecha pedido", "Pedido promedio", "Vendedora",
    "Lunes", "Martes", "Miércoles", "Jueves", "Viernes"
]].copy()

for dia in DIAS_LABORALES:
    dashboard_mostrar[dia] = dashboard_mostrar[dia].replace(0, "")

st.title("Dashboard de Seguimiento de Clientes - Repartos")

st.sidebar.header("Filtros")
vendedoras = ["Todas"] + sorted(dashboard_mostrar["Vendedora"].dropna().unique().tolist())
filtro_vendedora = st.sidebar.selectbox("Vendedora", vendedoras)

if filtro_vendedora != "Todas":
    dashboard_filtrado = dashboard_mostrar[dashboard_mostrar["Vendedora"] == filtro_vendedora].copy()
    dashboard_base_filtrado = dashboard[dashboard["Vendedora"] == filtro_vendedora].copy()
else:
    dashboard_filtrado = dashboard_mostrar.copy()
    dashboard_base_filtrado = dashboard.copy()

clientes_total = len(dashboard_base_filtrado)
clientes_con_pedido = dashboard_base_filtrado[dashboard_base_filtrado["Tiene pedido"]].copy()
clientes_sin_pedido = dashboard_base_filtrado[~dashboard_base_filtrado["Tiene pedido"]].copy()

col1, col2, col3 = st.columns(3)
col1.metric("Clientes totales", clientes_total)
col2.metric("Con pedido esta semana", len(clientes_con_pedido))
col3.metric("Sin pedido esta semana", len(clientes_sin_pedido))

st.subheader("Seguimiento general")
st.dataframe(dashboard_filtrado, use_container_width=True, hide_index=True)

st.subheader("Clientes sin pedido esta semana")
clientes_sin_pedido_mostrar = clientes_sin_pedido[[
    "Cliente", "Última fecha pedido", "Pedido promedio", "Vendedora",
    "Lunes", "Martes", "Miércoles", "Jueves", "Viernes"
]].copy()

for dia in DIAS_LABORALES:
    clientes_sin_pedido_mostrar[dia] = ""

st.dataframe(clientes_sin_pedido_mostrar, use_container_width=True, hide_index=True)
