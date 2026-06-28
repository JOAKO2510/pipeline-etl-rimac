# =============================================================================
# app/routers/conciliacion.py
# Endpoints de conciliación: buscar, guardar, importar, recargar.
# =============================================================================

import os
from fastapi import APIRouter, HTTPException
import pandas as pd

from app.config.config import (
    RUTA_PLANTILLA, HOJA_PLANTILLA,
    COLS_READONLY, COLS_EDITABLES,
)
from app.models.schemas import GuardarCambiosRequest, ImportarRequest
from app.services.conciliacion_service import (
    estado, normalizar_id, limpiar_valor,
    cargar_base, escribir_excel, check_sync, get_opciones_combo,
)
from app.database.connection import registrar_log

router = APIRouter(prefix="/api", tags=["conciliacion"])


@router.get("/estado")
def get_estado():
    """Info general de la base cargada — total filas, archivo, timestamp."""
    df = estado["df"]
    if df is None:
        raise HTTPException(503, "Base no cargada")
    return {
        "total_registros": len(df),
        "cargado_en":      estado["cargado_en"],
        "archivo":         os.path.basename(estado["archivo"]),
    }


@router.get("/opciones")
def get_opciones():
    """Valores únicos para los combos de ESTADO y DETALLE."""
    return get_opciones_combo()


@router.get("/check-sync")
def api_check_sync():
    """Detecta si el Excel fue modificado externamente desde la última carga."""
    return check_sync()


@router.post("/recargar")
def recargar():
    """Fuerza recarga del Excel desde disco."""
    cargar_base()
    return {"ok": True, "cargado_en": estado["cargado_en"]}


@router.get("/buscar/{id_registro}")
def buscar_registro(id_registro: str):
    """
    Busca un registro por ID en el DataFrame en RAM.
    Devuelve campos separados en readonly y editables para la GUI.
    Instantáneo — opera sobre datos en memoria.
    """
    df      = estado["df"]
    id_norm = normalizar_id(id_registro)
    mask    = df["ID"] == id_norm

    if not mask.any():
        raise HTTPException(404, f"ID {id_registro} no encontrado")

    fila = df[mask].iloc[0].to_dict()
    return {
        "readonly":  {k: limpiar_valor(fila.get(k)) for k in COLS_READONLY  if k in df.columns},
        "editables": {k: limpiar_valor(fila.get(k)) for k in COLS_EDITABLES if k in df.columns},
    }


@router.post("/guardar")
def guardar(req: GuardarCambiosRequest):
    """
    Guarda cambios de un registro individual.
    1. Valida columnas permitidas
    2. Aplica en RAM
    3. Escribe Excel
    4. Registra en log operacional + historial_id
    """
    df = estado["df"]
    cols_invalidas = [c for c in req.cambios if c not in COLS_EDITABLES]
    if cols_invalidas:
        raise HTTPException(400, f"Columnas no permitidas: {cols_invalidas}")

    id_norm = normalizar_id(req.id_registro)
    mask    = df["ID"] == id_norm
    if not mask.any():
        raise HTTPException(404, f"ID {req.id_registro} no encontrado")

    fila_idx = df.index[mask][0]

    # Captura el estado COMPLETO del registro ANTES de modificar RAM
    # Esto es crítico para la trazabilidad — el log necesita saber
    # de dónde venía el registro, no a dónde llegó
    antes = {c: limpiar_valor(df.at[fila_idx, c]) for c in df.columns}

    # Ahora sí modifica RAM
    for campo, valor in req.cambios.items():
        if campo in df.columns:
            df.at[fila_idx, campo] = valor

    try:
        escribir_excel(df)
    except Exception as e:
        raise HTTPException(500, f"Error al guardar Excel: {e}")

    # Pasa el DataFrame ANTES de la modificación para que registrar_log
    # capture el estado_origen correcto
    # Construimos un snapshot de la fila anterior para pasarlo al log
    for campo, valor_nuevo in req.cambios.items():
        registrar_log(
            req.id_registro,
            campo,
            antes.get(campo, ""),   # valor_antes del campo específico
            valor_nuevo,
            df,
            estado_antes = antes,   # estado completo antes del cambio
        )

    return {"ok": True, "mensaje": f"Registro {req.id_registro} actualizado"}


@router.post("/importar-plantilla")
def importar_plantilla():
    """
    Importación masiva desde Update_Conciliacion_PLANTILLA.xlsx.
    Aplica TODOS los cambios en RAM primero, luego escribe el Excel UNA vez.
    """
    if not os.path.exists(RUTA_PLANTILLA):
        raise HTTPException(404, f"No se encontró la plantilla en: {RUTA_PLANTILLA}")

    try:
        df_plantilla = pd.read_excel(RUTA_PLANTILLA, sheet_name=HOJA_PLANTILLA, dtype=str)
        df_plantilla.columns = df_plantilla.columns.str.strip()
    except Exception as e:
        raise HTTPException(500, f"Error al leer plantilla: {e}")

    if "ID" not in df_plantilla.columns:
        raise HTTPException(400, "La plantilla no tiene columna ID")

    df_plantilla = df_plantilla[df_plantilla["ID"].notna()].copy()
    df_plantilla["ID"] = df_plantilla["ID"].apply(normalizar_id)
    df_plantilla = df_plantilla[df_plantilla["ID"] != ""]

    cols_presentes = [c for c in COLS_EDITABLES if c in df_plantilla.columns]
    if not cols_presentes:
        raise HTTPException(400, f"Sin columnas editables. Encontradas: {list(df_plantilla.columns)}")

    print(f"📋 Plantilla: {len(df_plantilla)} registros | Columnas: {cols_presentes}")

    df_base = estado["df"]
    resultados  = {"ok": 0, "no_cruza": [], "errores": [], "total": len(df_plantilla)}
    cambios_log = []

    for _, row in df_plantilla.iterrows():
        id_val = str(row["ID"]).strip()
        if not id_val: continue

        mask = df_base["ID"] == id_val
        if not mask.any():
            resultados["no_cruza"].append(id_val)
            continue

        fila_idx = df_base.index[mask][0]
        cambios  = {col: limpiar_valor(row.get(col,"")) for col in cols_presentes if limpiar_valor(row.get(col,""))}
        if not cambios: continue

        # Captura estado COMPLETO antes de modificar RAM
        antes = {c: limpiar_valor(df_base.at[fila_idx,c]) for c in df_base.columns}
        for campo, valor in cambios.items():
            if campo in df_base.columns:
                df_base.at[fila_idx, campo] = valor

        cambios_log.append({"id": id_val, "antes": antes, "nuevos": cambios})
        resultados["ok"] += 1

    if resultados["ok"] > 0:
        try:
            print("💾 Escribiendo Excel una sola vez para todo el lote...")
            escribir_excel(df_base)
        except Exception as e:
            raise HTTPException(500, f"Error al guardar Excel: {e}")

    for item in cambios_log:
        for campo, valor_nuevo in item["nuevos"].items():
            registrar_log(
                item["id"],
                campo,
                item["antes"].get(campo, ""),
                valor_nuevo,
                df_base,
                estado_antes=item["antes"],  # estado completo antes del cambio
            )

    print(f"📊 {resultados['ok']} OK | {len(resultados['no_cruza'])} no cruzaron")
    return resultados


@router.post("/importar")
def importar(req: ImportarRequest):
    """Importación masiva desde CSV subido manualmente."""
    df_base = estado["df"]
    resultados  = {"ok": 0, "no_cruza": [], "errores": [], "total": len(req.registros)}
    cambios_log = []

    for item in req.registros:
        id_val  = normalizar_id(str(item.get("ID","")))
        cambios = {k: v for k,v in item.items() if k != "ID" and k in COLS_EDITABLES and str(v).strip()}
        if not id_val or not cambios: continue

        mask = df_base["ID"] == id_val
        if not mask.any():
            resultados["no_cruza"].append(id_val)
            continue

        fila_idx = df_base.index[mask][0]
        antes    = {c: limpiar_valor(df_base.at[fila_idx,c]) for c in cambios if c in df_base.columns}
        for campo, valor in cambios.items():
            if campo in df_base.columns:
                df_base.at[fila_idx, campo] = valor

        cambios_log.append({"id": id_val, "antes": antes, "nuevos": cambios})
        resultados["ok"] += 1

    if resultados["ok"] > 0:
        try:
            escribir_excel(df_base)
        except Exception as e:
            raise HTTPException(500, f"Error al guardar Excel: {e}")

    for item in cambios_log:
        for campo, valor_nuevo in item["nuevos"].items():
            registrar_log(
                item["id"],
                campo,
                item["antes"].get(campo, ""),
                valor_nuevo,
                df_base,
                estado_antes=item["antes"],  # estado completo antes del cambio
            )

    return resultados
