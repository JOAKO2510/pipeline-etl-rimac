# =============================================================================
# app/models/schemas.py
# Modelos Pydantic — validan automáticamente el body JSON de los endpoints.
# =============================================================================

from pydantic import BaseModel
from typing import Optional


class GuardarCambiosRequest(BaseModel):
    """Body para guardar cambios de un registro individual."""
    id_registro: str
    cambios: dict   # { "ESTADO DE AVANCE": "Finalizado", ... }


class ImportarRequest(BaseModel):
    """Body para importación masiva desde CSV."""
    registros: list  # lista de dicts con ID + campos editables
