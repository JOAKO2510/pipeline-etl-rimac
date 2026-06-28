import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import glob
import os

# ============================================================
# CONFIGURACION — TUS DATOS
# ============================================================
RUTA_EXCEL    = r"C:\Users\pavel\OneDrive\ConciliacionRimac"
CREDENCIALES  = r"C:\Users\pavel\OneDrive\Script\conciliacion-script.json"
SHEET_ID = "11jMc4vQmH_ABlEQ6zrRaXkf5IhhmgaWrhPU906SglVE"
HOJA          = "GENERAL"  # cambia si tu hoja tiene otro nombre

# Columnas a extraer del Excel
COLUMNAS = [
    "BASE",
    "FECHA OPERACION",
    "AÑO",
    "MONTO DOLARIZADO",
    "DETALLE DE LOS CASOS",
    "ESTADO DE AVANCE",
    "PRODUCTO"
]

# ============================================================
# PASO 1 — Buscar el Excel más reciente con "BASE CONCILIACIÓN"
# ============================================================
archivos = glob.glob(os.path.join(RUTA_EXCEL, "*BASE CONCILIACIÓN*.xlsx"))

if not archivos:
    print("❌ No se encontró ningún Excel con 'BASE CONCILIACIÓN' en la carpeta")
    exit()

archivo_reciente = max(archivos, key=os.path.getmtime)
print(f"✅ Leyendo: {archivo_reciente}")

# ============================================================
# PASO 2 — Leer Excel con pandas
# ============================================================
df = pd.read_excel(archivo_reciente, sheet_name="BASE GENERAL", usecols=COLUMNAS)
df = df.fillna("")

# Formatear fechas
df["FECHA OPERACION"] = pd.to_datetime(
    df["FECHA OPERACION"], errors='coerce'
).dt.strftime('%Y-%m-%d')

# Limpiar columna AÑO
df["AÑO"] = (
    pd.to_numeric(df["AÑO"], errors='coerce')
    .astype(str)
    .str.replace(".0", "", regex=False)
)

# ============================================================
# PASO 3 — Aplicar cambios de negocio
# ============================================================
valores_fcr = [
    "Extorno Global - FCR2",
    "Extorno Global - FCR1",
    "Cargos devueltos a Rimac - FCR1"
]

df.loc[
    df["DETALLE DE LOS CASOS"].isin(valores_fcr),
    "ESTADO DE AVANCE"
] = "Bolsas FCR"

# ============================================================
# PASO 4 — Renombrar columnas para Google Sheets
# ============================================================
df = df.rename(columns={
    "PRODUCTO"          : "Productos",
    "FECHA OPERACION"   : "Fecha de Operación",
    "DETALLE DE LOS CASOS": "Detalle de los Casos",
    "ESTADO DE AVANCE"  : "Estado de Avance",
    "MONTO DOLARIZADO"  : "Monto Dolarizado",
    "BASE"              : "Base",
    "AÑO"               : "Año"
})

# ============================================================
# PASO 5 — Conectar a Google Sheets y escribir
# ============================================================
cliente = gspread.service_account(filename=CREDENCIALES)
sheet   = cliente.open_by_key(SHEET_ID).worksheet(HOJA)

sheet.clear()
sheet.update([df.columns.tolist()] + df.values.tolist())

print(f"✅ Listo! Se escribieron {len(df)} filas en Google Sheets")