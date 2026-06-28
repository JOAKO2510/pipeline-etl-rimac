# =============================================================================
# app/database/connection.py
# Manejo de SQLite: inicialización de tablas y registro del log operacional.
#
# DISEÑO DEL LOG: 1 fila por ID por día (UNIQUE en fecha + id_registro)
#   - Primera modificación del día → INSERT con estado_origen capturado
#   - Modificaciones posteriores   → UPDATE (no duplica)
# =============================================================================

import sqlite3
from datetime import datetime

import pandas as pd

from app.config.config import (
    RUTA_LOG_DB, USUARIO_ACTUAL,
    ESTADO_GANADOR_AVANCE, ESTADO_GANADOR_DETALLE,
)


def get_conn() -> sqlite3.Connection:
    """Retorna una conexión SQLite. Siempre cerrarla después de usar."""
    return sqlite3.connect(RUTA_LOG_DB)


def inicializar_db():
    """
    Crea las tablas del datamart si no existen.

    TABLA 1 — log_operacional
        1 fila por ID por día. Captura estado_origen (de dónde venía)
        y estado_final (a dónde llegó). Permite trazabilidad completa
        sin duplicados.

    TABLA 2 — historial_id
        1 fila por CADA cambio de cada ID (append-only).
        Permite ver la historia completa de un ID: todos los estados
        por los que pasó, con timestamp exacto.
        Karen puede ver: "el ID 120524 pasó por T.Directo → Por Analizar → Finalizado"
    """
    conn = get_conn()

    # ── TABLA 1: log operacional — 1 fila por ID por día ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS log_operacional (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha           TEXT NOT NULL,
            primera_mod     TEXT NOT NULL,
            ultima_mod      TEXT NOT NULL,
            usuario         TEXT NOT NULL,
            id_registro     TEXT NOT NULL,
            base            TEXT,
            moneda          TEXT,
            anio            TEXT,
            fecha_oper      TEXT,
            monto_dolar     REAL,
            certificado     TEXT,
            numero_la       TEXT,
            mto_la          TEXT,
            estado_origen   TEXT,
            detalle_origen  TEXT,
            estado_final    TEXT,
            detalle_final   TEXT,
            q_cambios       INTEGER DEFAULT 1,
            UNIQUE(fecha, id_registro)
        )
    """)

    # ── TABLA 2: historial_id — 1 fila por cada cambio (append-only) ──
    # Permite reconstruir el recorrido completo de cualquier ID
    conn.execute("""
        CREATE TABLE IF NOT EXISTS historial_id (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT NOT NULL,
            fecha       TEXT NOT NULL,
            usuario     TEXT NOT NULL,
            id_registro TEXT NOT NULL,
            campo       TEXT NOT NULL,   -- qué campo cambió
            valor_antes TEXT,            -- valor anterior
            valor_nuevo TEXT,            -- valor nuevo
            -- contexto del registro en ese momento
            base        TEXT,
            monto_dolar REAL,
            detalle_snapshot TEXT,       -- DETALLE DE LOS CASOS en ese momento
            estado_snapshot  TEXT        -- ESTADO DE AVANCE en ese momento
        )
    """)

    # ── TABLA 3: snapshot_base ──
    # Foto del estado de la base al arrancar el servidor cada día.
    # 1 fila por combinación ESTADO DE AVANCE + DETALLE DE LOS CASOS.
    # Permite comparar el estado inicial del día vs el estado actual
    # para calcular el movimiento real (delta) producido durante el día.
    #
    # UNIQUE(fecha, estado_avance, detalle_casos) → evita duplicados
    # si el servidor se reinicia varias veces el mismo día.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS snapshot_base (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha         TEXT NOT NULL,        -- YYYY-MM-DD
            hora          TEXT NOT NULL,        -- HH:MM:SS
            estado_avance TEXT NOT NULL,        -- ESTADO DE AVANCE
            detalle_casos TEXT NOT NULL,        -- DETALLE DE LOS CASOS
            q_casos       INTEGER DEFAULT 0,    -- cantidad de registros
            monto_dolar   REAL    DEFAULT 0,    -- suma MONTO DOLARIZADO
            UNIQUE(fecha, estado_avance, detalle_casos)
        )
    """)

    conn.commit()
    conn.close()
    print("✅ Datamart SQLite inicializado: log_operacional + historial_id + snapshot_base")


def tomar_snapshot(df):
    """
    Toma una foto del estado actual de la base agrupando por
    ESTADO DE AVANCE + DETALLE DE LOS CASOS.

    Se llama UNA vez al día al arrancar el servidor.
    Si ya existe un snapshot del día (servidor reiniciado), lo ignora
    gracias al UNIQUE(fecha, estado_avance, detalle_casos).

    Parámetro:
        df: DataFrame completo cargado en RAM (estado["df"])
    """
    from datetime import datetime
    import pandas as pd

    if df is None:
        print("⚠️  Snapshot: base no cargada, saltando")
        return

    hoy   = datetime.now()
    fecha = hoy.strftime("%Y-%m-%d")
    hora  = hoy.strftime("%H:%M:%S")

    # Verifica si ya existe snapshot del día
    conn = get_conn()
    ya_existe = conn.execute(
        "SELECT COUNT(*) FROM snapshot_base WHERE fecha = ?", (fecha,)
    ).fetchone()[0]

    if ya_existe > 0:
        print(f"📸 Snapshot del {fecha} ya existe ({ya_existe} filas) — no se sobreescribe")
        conn.close()
        return

    # Asegura que las columnas necesarias existen
    col_estado  = "ESTADO DE AVANCE"
    col_detalle = "DETALLE DE LOS CASOS"
    col_monto   = "MONTO DOLARIZADO"

    if col_estado not in df.columns or col_detalle not in df.columns:
        print("⚠️  Snapshot: columnas ESTADO DE AVANCE o DETALLE DE LOS CASOS no encontradas")
        conn.close()
        return

    # Copia solo las columnas necesarias y limpia valores nulos
    d = df[[col_estado, col_detalle, col_monto]].copy() if col_monto in df.columns         else df[[col_estado, col_detalle]].copy()

    d[col_estado]  = d[col_estado].fillna("(Sin estado)").astype(str).str.strip()
    d[col_detalle] = d[col_detalle].fillna("(Sin detalle)").astype(str).str.strip()

    if col_monto in d.columns:
        d[col_monto] = pd.to_numeric(d[col_monto], errors="coerce").fillna(0)
    else:
        d[col_monto] = 0

    # Agrupa: 1 fila por combinación estado + detalle
    resumen = (
        d.groupby([col_estado, col_detalle])
         .agg(
             q_casos    = (col_estado, "count"),
             monto_dolar= (col_monto,  "sum"),
         )
         .reset_index()
    )

    # Inserta en snapshot_base — OR IGNORE evita error si ya existe
    filas_insertadas = 0
    for _, row in resumen.iterrows():
        try:
            conn.execute("""
                INSERT OR IGNORE INTO snapshot_base
                    (fecha, hora, estado_avance, detalle_casos, q_casos, monto_dolar)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                fecha, hora,
                str(row[col_estado]),
                str(row[col_detalle]),
                int(row["q_casos"]),
                round(float(row["monto_dolar"]), 2),
            ))
            filas_insertadas += 1
        except Exception as e:
            print(f"⚠️  Snapshot fila error: {e}")

    conn.commit()
    conn.close()
    print(f"📸 Snapshot tomado: {filas_insertadas} combinaciones | fecha={fecha} hora={hora}")


def registrar_log(
    id_registro: str,
    campo:       str,
    valor_antes: str,
    valor_nuevo: str,
    df=None,
    estado_antes: dict = None,   # snapshot completo del registro ANTES del cambio
):
    """
    Registra un cambio en las dos tablas del datamart.

    PARÁMETRO CLAVE — estado_antes:
        Diccionario con TODOS los campos del registro tal como estaban
        ANTES de que pandas los modificara en RAM.
        Si se pasa, se usa para capturar estado_origen y detalle_origen
        correctamente en lugar de leer del df (que ya tiene el valor nuevo).

        Sin este parámetro, estado_origen quedaría igual a estado_final
        porque df ya fue modificado cuando se llama a esta función.

    TABLA log_operacional → UPSERT (1 fila por ID por día):
        - Primera vez hoy → INSERT con estado_origen = valor ANTES del cambio
        - Siguiente vez   → UPDATE con estado_final  = valor actual

    TABLA historial_id → INSERT siempre (append-only):
        - 1 fila por cada cambio de campo
        - Permite reconstruir el recorrido completo de cualquier ID
    """
    hoy   = datetime.now()
    ts    = hoy.strftime("%Y-%m-%d %H:%M:%S")
    fecha = hoy.strftime("%Y-%m-%d")

    # ── Enriquece con contexto ACTUAL del registro (post-cambio) ──
    # Se usa para los campos que no cambiaron (base, monto, certificado, etc.)
    ctx = {
        "base": "", "moneda": "", "anio": "", "fecha_oper": "",
        "monto_dolar": None, "certificado": "", "numero_la": "", "mto_la": "",
        "estado_actual": "", "detalle_actual": "",
    }

    if df is not None:
        from app.services.conciliacion_service import normalizar_id
        mask = df["ID"] == normalizar_id(id_registro)
        if mask.any():
            fila = df[mask].iloc[0]

            def safe(col):
                if col not in df.columns: return ""
                v = fila[col]
                return "" if pd.isna(v) or str(v).strip() in ("nan","None","<NA>","NaT") else str(v).strip()

            ctx["base"]           = safe("BASE")
            ctx["moneda"]         = safe("MONEDA")
            ctx["anio"]           = safe("AÑO")
            ctx["fecha_oper"]     = safe("FECHA OPERACION")
            ctx["certificado"]    = safe("CERTIFICADO BANCO")
            ctx["numero_la"]      = safe("NUMERO_LA")
            ctx["mto_la"]         = safe("MTO_LA")
            ctx["estado_actual"]  = safe("ESTADO DE AVANCE")
            ctx["detalle_actual"] = safe("DETALLE DE LOS CASOS")

            try:
                raw = safe("MONTO DOLARIZADO")
                ctx["monto_dolar"] = float(raw.replace(",","")) if raw else None
            except (ValueError, AttributeError):
                ctx["monto_dolar"] = None

    # ── Determina estado_origen y detalle_origen ──────────────────────────
    # LÓGICA CORRECTA:
    #   Si tenemos estado_antes (snapshot pre-cambio) → usarlo directamente
    #   Si no → usar valor_antes del campo específico
    #
    # Esto evita el bug donde origen = destino porque df ya fue modificado

    def limpiar_ctx(v):
        if not v: return ""
        s = str(v).strip()
        return "" if s in ("nan","None","<NA>","NaT") else s

    if estado_antes is not None:
        # Usamos el snapshot completo del registro antes del cambio
        estado_origen  = limpiar_ctx(estado_antes.get("ESTADO DE AVANCE", ""))
        detalle_origen = limpiar_ctx(estado_antes.get("DETALLE DE LOS CASOS", ""))
    else:
        # Fallback: inferimos el origen desde el valor_antes del campo
        # Para los campos que no cambiaron usamos el valor actual del df
        # (puede ser el mismo que el final si el campo ya estaba así)
        estado_origen  = str(valor_antes) if campo == "ESTADO DE AVANCE"     else ctx["estado_actual"]
        detalle_origen = str(valor_antes) if campo == "DETALLE DE LOS CASOS" else ctx["detalle_actual"]

    conn = get_conn()

    # ── TABLA 1: log_operacional — UPSERT 1 fila por ID por día ──────────
    existe = conn.execute(
        "SELECT id FROM log_operacional WHERE fecha=? AND id_registro=?",
        (fecha, id_registro)
    ).fetchone()

    if not existe:
        # Primera modificación del día → INSERT con origen real
        conn.execute("""
            INSERT INTO log_operacional (
                fecha, primera_mod, ultima_mod, usuario,
                id_registro, base, moneda, anio, fecha_oper,
                monto_dolar, certificado, numero_la, mto_la,
                estado_origen, detalle_origen,
                estado_final,  detalle_final,
                q_cambios
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            fecha, ts, ts, USUARIO_ACTUAL, id_registro,
            ctx["base"], ctx["moneda"], ctx["anio"], ctx["fecha_oper"],
            ctx["monto_dolar"], ctx["certificado"], ctx["numero_la"], ctx["mto_la"],
            estado_origen,       # ← de dónde venía
            detalle_origen,      # ← de dónde venía
            ctx["estado_actual"],  # ← a dónde llegó
            ctx["detalle_actual"], # ← a dónde llegó
            1,
        ))
    else:
        # Modificaciones posteriores → UPDATE solo el estado final
        conn.execute("""
            UPDATE log_operacional SET
                ultima_mod    = ?,
                estado_final  = ?,
                detalle_final = ?,
                monto_dolar   = ?,
                q_cambios     = q_cambios + 1
            WHERE fecha=? AND id_registro=?
        """, (
            ts,
            ctx["estado_actual"],
            ctx["detalle_actual"],
            ctx["monto_dolar"],
            fecha, id_registro,
        ))

    # ── TABLA 2: historial_id — INSERT siempre (append-only) ─────────────
    # Guarda el estado del registro EN ESE MOMENTO EXACTO
    # Usa estado_antes si está disponible para el snapshot pre-cambio
    det_snap = limpiar_ctx(estado_antes.get("DETALLE DE LOS CASOS",""))                if estado_antes else ctx["detalle_actual"]
    est_snap = limpiar_ctx(estado_antes.get("ESTADO DE AVANCE",""))                if estado_antes else ctx["estado_actual"]

    conn.execute("""
        INSERT INTO historial_id (
            timestamp, fecha, usuario, id_registro,
            campo, valor_antes, valor_nuevo,
            base, monto_dolar,
            detalle_snapshot, estado_snapshot
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (
        ts, fecha, USUARIO_ACTUAL, id_registro,
        campo,
        str(valor_antes) if valor_antes is not None else "",
        str(valor_nuevo) if valor_nuevo is not None else "",
        ctx["base"],
        ctx["monto_dolar"],
        det_snap,   # detalle ANTES del cambio
        est_snap,   # estado  ANTES del cambio
    ))

    conn.commit()
    conn.close()
