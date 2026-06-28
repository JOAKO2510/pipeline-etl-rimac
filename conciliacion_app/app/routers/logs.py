# =============================================================================
# app/routers/logs.py
# Endpoints del datamart analítico.
#
# DIFERENCIA GET vs POST — MUY IMPORTANTE:
#
#   GET  → Lee datos, NO modifica nada.
#          Los parámetros van en la URL: /api/log?fecha=2026-06-22
#          Cacheable por el navegador. Idempotente (repetirlo da igual).
#          Ejemplos: buscar un registro, ver el log, ver el dashboard.
#
#   POST → Crea o modifica datos.
#          Los parámetros van en el BODY (JSON).
#          NO cacheable. Cada llamada puede cambiar algo.
#          Ejemplos: guardar cambios, importar plantilla, recargar base.
#
# REGLA: si el endpoint solo LEE → GET. Si ESCRIBE o DISPARA acción → POST.
# =============================================================================

import sqlite3
from datetime import datetime
from fastapi import APIRouter, HTTPException

from app.config.config import (
    RUTA_LOG_DB,
    ESTADO_GANADOR_AVANCE, ESTADO_GANADOR_DETALLE,
    META_SEMANAL,
)
from app.services.conciliacion_service import estado

router = APIRouter(prefix="/api", tags=["logs"])


# =============================================================================
# ENDPOINT: GET /api/log
# Lee el log operacional del día — 1 fila por ID, ordenado por monto.
#
# Parámetros de query (van en la URL):
#   ?fecha=2026-06-22        → filtra por fecha (default: hoy)
#   ?base=FCR 2              → filtra por base
#   ?estado_final=Finalizado → filtra por estado final
#   ?limite=500              → máximo de filas a devolver
#
# Ejemplo de uso:
#   GET /api/log
#   GET /api/log?fecha=2026-06-22
#   GET /api/log?fecha=2026-06-22&base=FCR 2&limite=100
# =============================================================================
@router.get("/log")
def get_log(
    fecha:        str = None,
    base:         str = None,
    estado_final: str = None,
    limite:       int = 500,
):
    fecha_consulta = fecha or datetime.now().strftime("%Y-%m-%d")
    conn   = sqlite3.connect(RUTA_LOG_DB)
    where  = ["fecha = ?"]
    params = [fecha_consulta]

    if base:
        where.append("base = ?")
        params.append(base)
    if estado_final:
        where.append("UPPER(TRIM(estado_final)) = ?")
        params.append(estado_final.upper().strip())

    params.append(limite)

    rows = conn.execute(
        f"""SELECT
                fecha, primera_mod, ultima_mod, usuario,
                id_registro, base, moneda, anio, fecha_oper,
                monto_dolar, certificado, numero_la, mto_la,
                estado_origen, detalle_origen,
                estado_final,  detalle_final,
                q_cambios
            FROM  log_operacional
            WHERE {' AND '.join(where)}
            ORDER BY monto_dolar DESC NULLS LAST
            LIMIT ?""",
        params
    ).fetchall()
    conn.close()

    total_monto = sum(r[9] or 0 for r in rows)

    return {
        "fecha":       fecha_consulta,
        "total_casos": len(rows),
        "total_monto": round(total_monto, 2),
        "registros": [
            {
                "fecha":          r[0],
                "primera_mod":    r[1],
                "ultima_mod":     r[2],
                "usuario":        r[3],
                "id":             r[4],
                "base":           r[5],
                "moneda":         r[6],
                "anio":           r[7],
                "fecha_oper":     r[8],
                "monto_dolar":    round(float(r[9]), 2) if r[9] else 0,
                "certificado":    r[10],
                "numero_la":      r[11],
                "mto_la":         r[12],
                "estado_origen":  r[13],
                "detalle_origen": r[14],
                "estado_final":   r[15],
                "detalle_final":  r[16],
                "q_cambios":      r[17],
            }
            for r in rows
        ],
    }


# =============================================================================
# ENDPOINT: GET /api/log/resumen
# Resumen analítico del día — totales, por base, por estado, matriz
# de transiciones y KPIs de avance hacia el estado ganador.
#
# Este endpoint alimenta el Dashboard y el tablero de Karen.
#
# Parámetros de query:
#   ?fecha=2026-06-22  → default: hoy
#
# Ejemplo:
#   GET /api/log/resumen
#   GET /api/log/resumen?fecha=2026-06-22
# =============================================================================
@router.get("/log/resumen")
def get_log_resumen(fecha: str = None):
    fecha_consulta = fecha or datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(RUTA_LOG_DB)

    # ── Totales del día ──────────────────────────────────────────────────────
    tot = conn.execute("""
        SELECT COUNT(*), COALESCE(SUM(monto_dolar), 0)
        FROM   log_operacional
        WHERE  fecha = ?
    """, (fecha_consulta,)).fetchone()

    # ── Por base ─────────────────────────────────────────────────────────────
    por_base = conn.execute("""
        SELECT   base,
                 COUNT(*)                      AS casos,
                 COALESCE(SUM(monto_dolar), 0) AS monto
        FROM     log_operacional
        WHERE    fecha = ?
        GROUP BY base
        ORDER BY monto DESC
    """, (fecha_consulta,)).fetchall()

    # ── Por estado final ─────────────────────────────────────────────────────
    por_estado_final = conn.execute("""
        SELECT   estado_final,
                 COUNT(*)                      AS casos,
                 COALESCE(SUM(monto_dolar), 0) AS monto
        FROM     log_operacional
        WHERE    fecha = ?
        GROUP BY estado_final
        ORDER BY casos DESC
    """, (fecha_consulta,)).fetchall()

    # ── Por detalle final (top 15) ───────────────────────────────────────────
    por_detalle_final = conn.execute("""
        SELECT   detalle_final,
                 COUNT(*)                      AS casos,
                 COALESCE(SUM(monto_dolar), 0) AS monto
        FROM     log_operacional
        WHERE    fecha = ?
        GROUP BY detalle_final
        ORDER BY monto DESC
        LIMIT 15
    """, (fecha_consulta,)).fetchall()

    # ── Matriz de transiciones: estado origen → estado final ─────────────────
    # Responde: "¿de qué estado venían los registros que hoy cambiaron?"
    matriz = conn.execute("""
        SELECT   estado_origen,
                 estado_final,
                 COUNT(*)                      AS casos,
                 COALESCE(SUM(monto_dolar), 0) AS monto
        FROM     log_operacional
        WHERE    fecha = ?
        GROUP BY estado_origen, estado_final
        ORDER BY casos DESC
    """, (fecha_consulta,)).fetchall()

    # ── Ganadores: IDs que llegaron al estado ganador ────────────────────────
    # Estado ganador = FINALIZADO + PENDIENTE ENVIAR A COBRANZAS
    # Estos son los casos que "mueven la aguja" — la producción real del día
    ganadores = conn.execute("""
        SELECT COUNT(*), COALESCE(SUM(monto_dolar), 0)
        FROM   log_operacional
        WHERE  fecha = ?
        AND    UPPER(TRIM(estado_final))  = ?
        AND    UPPER(TRIM(detalle_final)) = ?
    """, (fecha_consulta,
          ESTADO_GANADOR_AVANCE.upper(),
          ESTADO_GANADOR_DETALLE.upper())).fetchone()

    conn.close()

    # ── KPIs de avance — tablero para Karen ─────────────────────────────────
    # Total de la base = cuántos IDs hay en RAM con estado ganador actualmente
    # Sirve como "meta del día": cuánto hay disponible para enviar
    df_base       = estado["df"]
    meta_casos    = 0
    meta_monto    = 0.0

    if df_base is not None and "ESTADO DE AVANCE" in df_base.columns:
        mask_gan = (
            df_base["ESTADO DE AVANCE"].str.strip().str.upper() == ESTADO_GANADOR_AVANCE.upper()
        ) & (
            df_base["DETALLE DE LOS CASOS"].str.strip().str.upper() == ESTADO_GANADOR_DETALLE.upper()
        )
        meta_casos = int(mask_gan.sum())
        if "MONTO DOLARIZADO" in df_base.columns:
            meta_monto = round(float(df_base.loc[mask_gan, "MONTO DOLARIZADO"].sum()), 2)

    gan_casos = int(ganadores[0] or 0)
    gan_monto = round(float(ganadores[1] or 0), 2)

    # Porcentaje de avance en casos y monto
    pct_casos = round((gan_casos / meta_casos  * 100), 1) if meta_casos  > 0 else 0.0
    pct_monto = round((gan_monto / meta_monto  * 100), 1) if meta_monto  > 0 else 0.0
    pct_meta_semanal = round((gan_monto / META_SEMANAL * 100), 1) if META_SEMANAL > 0 else 0.0

    return {
        "fecha":       fecha_consulta,
        "total_ids":   int(tot[0] or 0),
        "total_monto": round(float(tot[1] or 0), 2),

        # ── Estado ganador: la producción real ──
        "ganadores": {
            "casos":       gan_casos,
            "monto":       gan_monto,
            "descripcion": f"{ESTADO_GANADOR_AVANCE} + {ESTADO_GANADOR_DETALLE}",
        },

        # ── KPIs de avance (tablero Karen) ──
        "avance": {
            "meta_casos":        meta_casos,     # total en base con estado ganador
            "meta_monto":        meta_monto,     # monto total disponible
            "logrado_casos":     gan_casos,      # cuántos llegaron hoy
            "logrado_monto":     gan_monto,      # cuánto monto llegaron hoy
            "pct_casos":         pct_casos,      # % de casos logrados vs meta
            "pct_monto":         pct_monto,      # % de monto logrado vs meta
            "pct_meta_semanal":  pct_meta_semanal, # % de la meta semanal cubierto
            "meta_semanal":      META_SEMANAL,
        },

        # ── Desgloses ──
        "por_base": [
            {"base": r[0] or "(Sin base)", "casos": r[1], "monto": round(float(r[2]),2)}
            for r in por_base
        ],
        "por_estado_final": [
            {"estado": r[0] or "(Sin estado)", "casos": r[1], "monto": round(float(r[2]),2)}
            for r in por_estado_final
        ],
        "por_detalle_final": [
            {"detalle": r[0] or "(Sin detalle)", "casos": r[1], "monto": round(float(r[2]),2)}
            for r in por_detalle_final
        ],
        "matriz_transiciones": [
            {
                "origen":  r[0] or "(Sin origen)",
                "destino": r[1] or "(Sin destino)",
                "casos":   r[2],
                "monto":   round(float(r[3]), 2),
            }
            for r in matriz
        ],
    }


# =============================================================================
# ENDPOINT: GET /api/log/historial/{id_registro}
# Historial completo de un ID — todos los cambios que tuvo desde siempre.
#
# Responde: "¿por qué estados pasó el ID 120524 a lo largo del tiempo?"
# Ejemplo:
#   Timestamp            Campo                Antes         Después
#   2026-06-18 09:14     ESTADO DE AVANCE     T. Directo    Finalizado
#   2026-06-18 09:14     DETALLE DE LOS CASOS Ticket Ajuste Pend. Enviar Cobr.
#   2026-06-22 10:30     ESTADO DE AVANCE     Finalizado    Por Analizar
#
# Parámetros de path:
#   /api/log/historial/120524
#
# Parámetros de query opcionales:
#   ?campo=ESTADO DE AVANCE   → filtra por campo específico
# =============================================================================
@router.get("/log/historial/{id_registro}")
def get_historial_id(id_registro: str, campo: str = None):
    """
    Devuelve el historial completo de cambios de un ID específico.
    Fuente: tabla historial_id (append-only, 1 fila por cambio).

    Útil para auditar cualquier registro y ver por qué estados pasó.
    """
    conn   = sqlite3.connect(RUTA_LOG_DB)
    where  = ["id_registro = ?"]
    params = [id_registro]

    if campo:
        where.append("campo = ?")
        params.append(campo)

    rows = conn.execute(
        f"""SELECT
                timestamp, fecha, usuario,
                campo, valor_antes, valor_nuevo,
                base, monto_dolar,
                detalle_snapshot, estado_snapshot
            FROM  historial_id
            WHERE {' AND '.join(where)}
            ORDER BY id ASC""",
        params
    ).fetchall()
    conn.close()

    if not rows:
        # No lanza 404 — puede ser que el ID no tenga historial aún
        return {
            "id_registro": id_registro,
            "total_cambios": 0,
            "historial": [],
            "mensaje": f"Sin historial registrado para ID {id_registro}",
        }

    return {
        "id_registro":   id_registro,
        "total_cambios": len(rows),
        "historial": [
            {
                "timestamp":        r[0],
                "fecha":            r[1],
                "usuario":          r[2],
                "campo":            r[3],
                "valor_antes":      r[4],
                "valor_nuevo":      r[5],
                "base":             r[6],
                "monto_dolar":      round(float(r[7]),2) if r[7] else 0,
                "detalle_snapshot": r[8],
                "estado_snapshot":  r[9],
            }
            for r in rows
        ],
    }


# =============================================================================
# ENDPOINT: GET /api/dashboard
# KPIs generales de la Base General en RAM.
# No toca SQLite — lee directo del DataFrame en memoria → instantáneo.
#
# Responde: estado actual de todos los 121k registros por estado y detalle.
# =============================================================================
@router.get("/dashboard")
def get_dashboard():
    """
    KPIs de la base general en RAM.
    Instantáneo — no toca disco ni SQLite.
    """
    df = estado["df"]
    if df is None:
        raise HTTPException(503, "Base no cargada")

    cols = ["ID", "ESTADO DE AVANCE", "DETALLE DE LOS CASOS", "MONTO DOLARIZADO", "BASE"]
    d    = df[[c for c in cols if c in df.columns]].copy()

    for col in ["ESTADO DE AVANCE", "DETALLE DE LOS CASOS", "BASE"]:
        if col in d.columns:
            d[col] = d[col].fillna("").astype(str).str.strip().str.upper()

    d["MONTO_NUM"] = pd.to_numeric(d["MONTO DOLARIZADO"], errors="coerce").fillna(0) \
        if "MONTO DOLARIZADO" in d.columns else 0

    total = len(d)

    def kpi(mask, label):
        return {
            "label": label,
            "casos": int(mask.sum()),
            "monto": round(float(d.loc[mask, "MONTO_NUM"].sum()), 2),
        }

    mask_backlog   = (d["ESTADO DE AVANCE"] == ESTADO_GANADOR_AVANCE.upper()) \
                   & (d["DETALLE DE LOS CASOS"] == ESTADO_GANADOR_DETALLE.upper())
    mask_conc      = d["DETALLE DE LOS CASOS"] == "CONCILIADO CONTABLEMENTE"
    mask_cobr      = d["DETALLE DE LOS CASOS"] == "ENVIADO A COBRANZAS"
    mask_extorno   = d["DETALLE DE LOS CASOS"].str.startswith("EXTORNO GLOBAL", na=False)
    mask_analizar  = d["ESTADO DE AVANCE"] == "POR ANALIZAR"
    mask_pend_base = d["DETALLE DE LOS CASOS"].str.startswith("PENDIENTE ENVIO DE BASE", na=False)

    bl_casos = int(mask_backlog.sum())
    pct_bl   = round(bl_casos / total * 100, 1) if total else 0
    semaforo = "verde" if bl_casos < 500 else "amarillo" if bl_casos < 1000 else "rojo"

    # Distribución por base
    dist_base = {}
    if "BASE" in d.columns:
        for base, grp in d.groupby("BASE"):
            if base:
                dist_base[base] = {
                    "casos": int(len(grp)),
                    "monto": round(float(grp["MONTO_NUM"].sum()), 2),
                }

    # Por estado de avance
    dist_estado = []
    if "ESTADO DE AVANCE" in d.columns:
        for est, grp in d.groupby("ESTADO DE AVANCE"):
            if est:
                dist_estado.append({
                    "estado": est,
                    "casos":  int(len(grp)),
                    "monto":  round(float(grp["MONTO_NUM"].sum()), 2),
                })
        dist_estado.sort(key=lambda x: x["casos"], reverse=True)

    # Top 10 detalles
    dist_detalle = []
    if "DETALLE DE LOS CASOS" in d.columns:
        top = (
            d.groupby("DETALLE DE LOS CASOS")
             .agg(casos=("MONTO_NUM","count"), monto=("MONTO_NUM","sum"))
             .sort_values("casos", ascending=False)
             .head(10).reset_index()
        )
        for _, row in top.iterrows():
            det = str(row["DETALLE DE LOS CASOS"]).strip()
            if det:
                dist_detalle.append({
                    "detalle": det,
                    "casos":   int(row["casos"]),
                    "monto":   round(float(row["monto"]), 2),
                })

    return {
        "resumen": {
            "total_registros": total,
            "monto_total":     round(float(d["MONTO_NUM"].sum()), 2),
            "cargado_en":      estado["cargado_en"],
        },
        "kpis": {
            "backlog":        {**kpi(mask_backlog,"Pendiente Enviar a Cobranzas"), "pct": pct_bl, "semaforo": semaforo},
            "conciliados":    kpi(mask_conc,      "Conciliado Contablemente"),
            "cobranza":       kpi(mask_cobr,      "Enviado A Cobranzas"),
            "extornos":       kpi(mask_extorno,   "Extorno Global FCR1+FCR2"),
            "por_analizar":   kpi(mask_analizar,  "Por Analizar"),
            "pendiente_base": kpi(mask_pend_base, "Pendiente Envío de Base"),
        },
        "distribucion": {
            "por_base":    dist_base,
            "por_estado":  dist_estado,
            "por_detalle": dist_detalle,
        },
    }


# Importación necesaria para el dashboard (pandas en el router)
import pandas as pd


# =============================================================================
# ENDPOINT: GET /api/snapshot
# Devuelve el snapshot del día — foto inicial de la base al arrancar.
#
# Parámetros de query:
#   ?fecha=2026-06-23  → default: hoy
#
# Ejemplo:
#   GET /api/snapshot
#   GET /api/snapshot?fecha=2026-06-23
# =============================================================================
@router.get("/snapshot")
def get_snapshot(fecha: str = None):
    """
    Devuelve la foto del estado de la base al inicio del día.
    Agrupa por ESTADO DE AVANCE + DETALLE DE LOS CASOS.
    """
    fecha_consulta = fecha or datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(RUTA_LOG_DB)

    rows = conn.execute("""
        SELECT estado_avance, detalle_casos, q_casos, monto_dolar, hora
        FROM   snapshot_base
        WHERE  fecha = ?
        ORDER  BY monto_dolar DESC
    """, (fecha_consulta,)).fetchall()

    conn.close()

    total_casos = sum(r[2] for r in rows)
    total_monto = sum(r[3] for r in rows)

    return {
        "fecha":       fecha_consulta,
        "total_filas": len(rows),
        "total_casos": total_casos,
        "total_monto": round(total_monto, 2),
        "snapshot": [
            {
                "estado_avance": r[0],
                "detalle_casos": r[1],
                "q_casos":       r[2],
                "monto_dolar":   round(float(r[3]), 2),
                "hora":          r[4],
            }
            for r in rows
        ],
    }


# =============================================================================
# ENDPOINT: GET /api/movimiento
# Calcula el DELTA entre el snapshot inicial y el estado actual de la base.
# Responde: ¿qué movió la aguja hoy?
#
# Para cada combinación ESTADO + DETALLE muestra:
#   q_inicio  → casos al inicio del día (snapshot)
#   q_actual  → casos ahora mismo (RAM)
#   delta_q   → diferencia (positivo = creció, negativo = se redujo)
#   m_inicio  → monto al inicio
#   m_actual  → monto actual
#   delta_m   → diferencia de monto
#
# Ejemplo:
#   GET /api/movimiento
#   GET /api/movimiento?fecha=2026-06-23
# =============================================================================
@router.get("/movimiento")
def get_movimiento(fecha: str = None):
    """
    Delta entre snapshot inicial del día y estado actual de la base en RAM.
    Muestra exactamente qué cambió desde que arrancó el servidor.
    """
    fecha_consulta = fecha or datetime.now().strftime("%Y-%m-%d")

    # ── Estado inicial: snapshot del día ──────────────────────────────────
    conn = sqlite3.connect(RUTA_LOG_DB)
    snap_rows = conn.execute("""
        SELECT estado_avance, detalle_casos, q_casos, monto_dolar
        FROM   snapshot_base
        WHERE  fecha = ?
    """, (fecha_consulta,)).fetchall()
    conn.close()

    # Convierte a dict para búsqueda rápida
    snap = {
        (r[0], r[1]): {"q": r[2], "m": round(float(r[3]), 2)}
        for r in snap_rows
    }

    # ── Estado actual: desde RAM ──────────────────────────────────────────
    df_base = estado["df"]
    if df_base is None:
        raise HTTPException(503, "Base no cargada")

    col_estado  = "ESTADO DE AVANCE"
    col_detalle = "DETALLE DE LOS CASOS"
    col_monto   = "MONTO DOLARIZADO"

    d = df_base[[col_estado, col_detalle, col_monto]].copy()         if col_monto in df_base.columns         else df_base[[col_estado, col_detalle]].copy()

    d[col_estado]  = d[col_estado].fillna("(Sin estado)").astype(str).str.strip()
    d[col_detalle] = d[col_detalle].fillna("(Sin detalle)").astype(str).str.strip()

    if col_monto in d.columns:
        d[col_monto] = pd.to_numeric(d[col_monto], errors="coerce").fillna(0)
    else:
        d[col_monto] = 0

    actual = (
        d.groupby([col_estado, col_detalle])
         .agg(q=( col_estado, "count"), m=(col_monto, "sum"))
         .reset_index()
    )

    # ── Calcula delta para cada combinación ──────────────────────────────
    resultados = []
    claves_actual = set()

    for _, row in actual.iterrows():
        clave   = (str(row[col_estado]), str(row[col_detalle]))
        claves_actual.add(clave)

        q_act = int(row["q"])
        m_act = round(float(row["m"]), 2)
        q_ini = snap.get(clave, {}).get("q", 0)
        m_ini = snap.get(clave, {}).get("m", 0.0)

        delta_q = q_act - q_ini
        delta_m = round(m_act - m_ini, 2)

        resultados.append({
            "estado_avance": clave[0],
            "detalle_casos": clave[1],
            "q_inicio":      q_ini,
            "q_actual":      q_act,
            "delta_q":       delta_q,   # + creció, - se redujo, 0 sin cambio
            "m_inicio":      m_ini,
            "m_actual":      m_act,
            "delta_m":       delta_m,
            "hay_movimiento": delta_q != 0 or delta_m != 0,
        })

    # Incluye filas del snapshot que ya no existen en la base actual
    for clave, vals in snap.items():
        if clave not in claves_actual:
            resultados.append({
                "estado_avance": clave[0],
                "detalle_casos": clave[1],
                "q_inicio":      vals["q"],
                "q_actual":      0,
                "delta_q":       -vals["q"],
                "m_inicio":      vals["m"],
                "m_actual":      0.0,
                "delta_m":       -vals["m"],
                "hay_movimiento": True,
            })

    # Ordena: primero los que tuvieron movimiento, luego por monto actual
    resultados.sort(key=lambda x: (not x["hay_movimiento"], -x["m_actual"]))

    # ── Totales ──────────────────────────────────────────────────────────
    con_movimiento = [r for r in resultados if r["hay_movimiento"]]

    return {
        "fecha":               fecha_consulta,
        "total_combinaciones": len(resultados),
        "con_movimiento":      len(con_movimiento),
        "sin_movimiento":      len(resultados) - len(con_movimiento),
        "snapshot_existe":     len(snap_rows) > 0,
        "movimientos":         resultados,
    }
