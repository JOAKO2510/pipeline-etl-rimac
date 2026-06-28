import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import glob
import os

# Configuracion
RUTA_EXCEL = r"D:\OneDrive - Rimac Seguros y Reaseguros\Archivos de Michael Jordan Chaponan Aguilar - COMPARTIDO CONCILIACIONES\ACTUALIZACIONES CONCILIACIÓN"
CREDENCIALES = r"C:\scripts\credenciales.json"
SHEET_ID = "1ezpJF0BQbXFUsLw7JN3KWi8cl9OPlRuZNbxng8lenCM"
HOJA = "GENERAL"  # cambia si tu hoja tiene otro nombre

COLUMNAS = [
    "BASE",
    "FECHA OPERACION",
    "AÑO",
    "MONTO DOLARIZADO",
    "DETALLE DE LOS CASOS",
    "ESTADO DE AVANCE",
    "PRODUCTO"
]

# Buscar el Excel mas reciente en la carpeta
archivos = glob.glob(os.path.join(RUTA_EXCEL, "*BASE CONCILIACIÓN*.xlsx"))
if not archivos:
    print("No se encontro ningun Excel en la carpeta")
    exit()

archivo_reciente = max(archivos, key=os.path.getmtime)
print(f"Leyendo: {archivo_reciente}")

# Leer Excel
df = pd.read_excel(archivo_reciente, sheet_name="BASE GENERAL", usecols=COLUMNAS)
df = df.fillna("")
df["FECHA OPERACION"] = pd.to_datetime(df["FECHA OPERACION"], errors='coerce').dt.strftime('%Y-%m-%d')
df["AÑO"] = pd.to_numeric(df["AÑO"], errors='coerce').astype(str).str.replace(".0", "", regex=False)
# 2. Aplicar cambios ← ACÁ
# 2. Aplicar cambios ← ACÁ
valores_fcr = [
    "Extorno Global - FCR2",
    "Extorno Global - FCR1",
    "Cargos devueltos a Rimac - FCR1"
]

df.loc[df["DETALLE DE LOS CASOS"].isin(valores_fcr), "ESTADO DE AVANCE"] = "Bolsas FCR"
#df.loc[df["DETALLE DE LOS CASOS"].str.contains("FCR", na=False), "ESTADO DE AVANCE"] = "Bolsas FCR"

#df["DETALLE DE LOS CASOS"] = df["DETALLE DE LOS CASOS"].str.replace("La Doble -Base Doble", "Pendiente Enviar a Cobranzas", regex=False)


# Conectar a Google Sheets
scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file(CREDENCIALES, scopes=scopes)
cliente = gspread.auth.local_server_flow
cliente = gspread.service_account(filename=CREDENCIALES)

sheet = cliente.open_by_key(SHEET_ID).worksheet(HOJA)

df = df.rename(columns={
    "PRODUCTO": "Productos",
    "FECHA OPERACION": "Fecha de Operación",
    "DETALLE DE LOS CASOS": "Detalle de los Casos",
    "ESTADO DE AVANCE": "Estado de Avance",
    "MONTO DOLARIZADO": "Monto Dolarizado",
    "BASE": "Base",
    "AÑO": "Año"
})

# Limpiar hoja y escribir datos
sheet.clear()
sheet.update([df.columns.tolist()] + df.values.tolist())

print(f"Listo! Se escribieron {len(df)} filas en Google Sheets")