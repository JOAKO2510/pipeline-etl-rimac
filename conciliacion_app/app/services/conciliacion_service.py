# =============================================================================
# app/services/conciliacion_service.py
# Lógica pesada de negocio: carga del Excel, escritura, normalización.
# Esta capa NO conoce FastAPI — solo pandas y lógica pura.
# =============================================================================

import os
import shutil
import tempfile
import warnings

import pandas as pd

from app.config.config import (
    RUTA_BASE_EXCEL, HOJA_BASE,
    COLS_EDITABLES, COLS_CON_COMBO,
)

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

# ── Estado global en RAM ────────────────────────────────────────────────────
# El DataFrame se carga UNA vez al arrancar. Todas las búsquedas
# operan sobre esta copia en memoria → instantáneo sin tocar el disco.
estado = {
    "df":         None,    # DataFrame completo (121k filas)
    "archivo":    None,    # ruta del Excel activo
    "cargado_en": None,    # timestamp de la última carga
}


# ── Utilidades ──────────────────────────────────────────────────────────────

def normalizar_id(valor) -> str:
    """
    Convierte cualquier variante de ID a string sin decimales.
    Excel guarda números como "3192.0" → aquí los convertimos a "3192".
    """
    if valor is None or str(valor).strip() in ("", "nan", "None", "<NA>"):
        return ""
    try:
        return str(int(float(str(valor).strip())))
    except (ValueError, TypeError):
        return str(valor).strip()


def limpiar_valor(v) -> str:
    """NaN, None, 'nan' → string vacío. Evita el error 'NaN is not JSON compliant'."""
    if v is None: return ""
    if isinstance(v, float) and v != v: return ""
    s = str(v).strip()
    return "" if s in ("nan", "None", "<NA>", "NaT") else s


# ── Carga del Excel ─────────────────────────────────────────────────────────

def cargar_base():
    """
    Lee el Excel completo en RAM. Se llama UNA vez al arrancar el servidor.
    También se puede llamar desde /api/recargar si alguien modificó el archivo.

    pandas lee con dtype=str para no truncar IDs numéricos largos.
    MONTO DOLARIZADO se convierte a numérico para el dashboard.
    """
    from datetime import datetime
    print(f"📂 Cargando base desde:\n   {RUTA_BASE_EXCEL}")

    df = pd.read_excel(RUTA_BASE_EXCEL, sheet_name=HOJA_BASE, dtype=str)
    df.columns = df.columns.str.strip()
    df["ID"]   = df["ID"].apply(normalizar_id)

    if "MONTO DOLARIZADO" in df.columns:
        df["MONTO DOLARIZADO"] = pd.to_numeric(
            df["MONTO DOLARIZADO"].astype(str).str.replace(",","").str.strip(),
            errors="coerce"
        ).fillna(0.0)

    estado["df"]         = df
    estado["archivo"]    = RUTA_BASE_EXCEL
    estado["cargado_en"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"✅ Base cargada: {len(df):,} filas | {len(df.columns)} columnas")


# ── Escritura al Excel ───────────────────────────────────────────────────────

def escribir_excel(df: pd.DataFrame):
    """
    Escribe el DataFrame de vuelta al Excel.
    Solo toca la hoja BASE GENERAL — el resto del archivo queda intacto.

    Si OneDrive tiene el archivo bloqueado → usa copia temporal.
    """
    def _escribir(ruta: str):
        with pd.ExcelWriter(
            ruta, engine="openpyxl", mode="a", if_sheet_exists="replace"
        ) as writer:
            df.to_excel(writer, sheet_name=HOJA_BASE, index=False)

    try:
        _escribir(RUTA_BASE_EXCEL)
        print("✅ Excel guardado directamente")
    except PermissionError:
        print("⚠️  OneDrive bloqueó el archivo, usando copia temporal...")
        ruta_temp = tempfile.mktemp(suffix=".xlsx")
        shutil.copy2(RUTA_BASE_EXCEL, ruta_temp)
        _escribir(ruta_temp)
        shutil.move(ruta_temp, RUTA_BASE_EXCEL)
        print("✅ Excel guardado via copia temporal")


# ── Check de sincronización ──────────────────────────────────────────────────

def check_sync() -> dict:
    """
    Compara la fecha de modificación del Excel en disco
    vs el timestamp de la última carga en RAM.
    Si el archivo cambió después de la carga → avisa al frontend.
    """
    from datetime import datetime
    if estado["cargado_en"] is None:
        return {"desincronizado": False}
    try:
        mtime   = os.path.getmtime(RUTA_BASE_EXCEL)
        dt_disco = datetime.fromtimestamp(mtime)
        dt_ram   = datetime.strptime(estado["cargado_en"], "%Y-%m-%d %H:%M:%S")
        return {
            "desincronizado": dt_disco > dt_ram,
            "modificado_en":  dt_disco.strftime("%Y-%m-%d %H:%M:%S"),
            "cargado_en":     estado["cargado_en"],
        }
    except Exception as e:
        return {"desincronizado": False, "error": str(e)}


# ── Opciones para combos ─────────────────────────────────────────────────────

def get_opciones_combo() -> dict:
    """
    Devuelve los valores únicos de DETALLE y ESTADO desde la base en RAM.
    Se usan en los combos inteligentes del frontend.
    """
    df = estado["df"]
    if df is None:
        return {}
    resultado = {}
    for col in COLS_CON_COMBO:
        if col in df.columns:
            valores = (
                df[col].dropna().astype(str).str.strip()
                .replace("", float("nan")).dropna().unique().tolist()
            )
            resultado[col] = sorted([
                v for v in valores if v not in ("nan","None","<NA>","NaT","")
            ])
    return resultado
