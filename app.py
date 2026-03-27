import streamlit as st
import pandas as pd

st.set_page_config(page_title="Dashboard Repartos", layout="wide")

# ==============================
# CONFIG
# ==============================
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/18vbqYiBLv1M-F4JXg45Fn8E9a-rBYFfF/gviz/tq?tqx=out:csv&gid=1737217651"

# ==============================
# FUNCION LIMPIEZA NUMEROS (CLAVE)
# ==============================
def limpiar_numeros(col):
    return (
        col.astype(str)
        .str.replace(".", "", regex=False)   # elimina separador miles
        .str.replace(",", ".", regex=False)  # por si hay coma decimal
        .str.replace(" ", "", regex=False)
        .astype(float)
    )

# ==============================
# CARGA DATA
# ==============================
@st.cache_data
def cargar_datos():
    df = pd.read_csv(GOOGLE_SHEET_URL)

    # limpiar nombres columnas (por si vienen raros)
    df.columns = df.columns.str.strip()

    # renombrar si hace falta (por seguridad)
    df = df.rename(columns={
        "Fecha entrega": "Fecha entrega",
        "Cliente": "Cliente",
        "Producto": "Producto",
        "Total producto": "Total producto",
        "Vende": "Vendedora"
    })

    # 🔥 LIMPIEZA AUTOMATICA
    if "Total producto" in df.columns:
        df["Total producto"] = limpiar_numeros(df["Total producto"])

    # convertir fecha
    df["Fecha entrega"] = pd.to_datetime(df["Fecha entrega"], errors="coerce")

    return df

df = cargar_datos()

# ==============================
# KPI
# ==============================
clientes_totales = df["Cliente"].nunique()

# clientes con pedido esta semana
hoy = pd.Timestamp.today()
inicio_semana = hoy - pd.Timedelta(days=hoy.weekday())

df_semana = df[df["Fecha entrega"] >= inicio_semana]

clientes_con_pedido = df_semana["Cliente"].nunique()
clientes_sin_pedido = clientes_totales - clientes_con_pedido

# ==============================
# UI
# ==============================
st.title("Dashboard de Seguimiento de Clientes - Repartos")

col1, col2, col3 = st.columns(3)
col1.metric("Clientes totales", clientes_totales)
col2.metric("Con pedido esta semana", clientes_con_pedido)
col3.metric("Sin pedido esta semana", clientes_sin_pedido)

# ==============================
# TABLA GENERAL
# ==============================
st.subheader("Seguimiento general")

dashboard = df.groupby("Cliente").agg({
    "Fecha entrega": "max",
    "Total producto": "mean"
}).reset_index()

dashboard.columns = ["Cliente", "Última fecha pedido", "Pedido promedio"]

st.dataframe(dashboard, use_container_width=True)

# ==============================
# CLIENTES SIN PEDIDO
# ==============================
st.subheader("Clientes sin pedido esta semana")

clientes_semana = df_semana["Cliente"].unique()
clientes_sin = dashboard[~dashboard["Cliente"].isin(clientes_semana)]

st.dataframe(clientes_sin, use_container_width=True)
