# =============================================================================
# app/config/config.py
# Configuración global del sistema.
# Un solo lugar para cambiar rutas, usuarios y parámetros de negocio.
# =============================================================================

# ── Rutas de archivos ──────────────────────────────────────────────────────
RUTA_BASE_EXCEL = (
    r"D:\OneDrive - Rimac Seguros y Reaseguros"
    r"\Archivos de Michael Jordan Chaponan Aguilar - COMPARTIDO CONCILIACIONES"
    r"\INFORMACIÓN\PAVEL ARCHIVOS\Update_Conciliacion_Test"
    r"\18-06-2026 BASE CONCILIACIÓN.xlsx"
)

RUTA_PLANTILLA = (
    r"D:\OneDrive - Rimac Seguros y Reaseguros"
    r"\Archivos de Michael Jordan Chaponan Aguilar - COMPARTIDO CONCILIACIONES"
    r"\INFORMACIÓN\PAVEL ARCHIVOS\Update_Conciliacion_Test"
    r"\Update_Conciliacion_PLANTILLA.xlsx"
)

RUTA_LOG_DB = r"C:\scripts\conciliacion_log.db"

# ── Parámetros de negocio ──────────────────────────────────────────────────
HOJA_BASE      = "BASE GENERAL"
HOJA_PLANTILLA = "ID"
USUARIO_ACTUAL = "Pavel Villegas"
META_SEMANAL   = 250_000.00    # USD — meta semanal de Karen

# ── Columnas del Excel ─────────────────────────────────────────────────────
COLS_READONLY = [
    "ID", "BASE", "FUENTE", "ORIGEN", "CUENTA", "MONEDA", "AÑO",
    "FECHA OPERACION", "DETALLE", "N° DE OPERACIÓN", "MONTO",
    "MONTO DOLARIZADO", "NRORECLAMO", "LARGO CERTIFICADO",
    "CERTIFICADO DUPLICADO", "DIGITO 11", "SISTEMA",
    "CERTIFICADO BANCO", "CERTIFICADO 99", "PRODUCTO",
    "COD_PROD", "IDEPOL", "CONCAT-POLIZA", "COD_PROD DEL SISTEMA",
    "DIF X CUPON", "PRIMA TOTAL", "DIFERENCIA TOTAL", "dif",
    "DÍAS PAGADOS", "DÍAS A DEVOLVER", "FECHA DE ANULACIÓN",
]

COLS_EDITABLES = [
    "STSCERT", "FEC_INI_VIG_CERT", "FEC_FIN_VIG_CERT",
    "Fecha Ini Ult Cobertura", "Fecha Fin Ult Cobertura",
    "PRIMA COB", "CAN_LQ_COB", "CAN_LQ_INC", "CAN_LQ_ANU", "CAN_LQ_EMI",
    "NUMERO_LA", "MTO_LA", "ESTADO_LA", "CONTEO_LA", "EMISION_LA",
    "OBSERVACION GENERAL", "DETALLE DE LOS CASOS", "ESTADO DE AVANCE",
]

COLS_CON_COMBO = ["DETALLE DE LOS CASOS", "ESTADO DE AVANCE"]

# Estado ganador — cuando un ID llega aquí es producción real
ESTADO_GANADOR_AVANCE  = "FINALIZADO"
ESTADO_GANADOR_DETALLE = "PENDIENTE ENVIAR A COBRANZAS"
