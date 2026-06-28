# Pipeline ETL — Conciliación Contable

Automatización completa de un proceso de conciliación contable usando Python, Google Sheets y Looker Studio. El sistema procesa más de 121,000 registros diarios, eliminando tareas manuales en Excel y centralizando la información en un dashboard en tiempo real.

> Los datos utilizados en este proyecto son simulados con fines de portfolio.

---

## ¿Qué hace este proyecto?

1. **Extrae** archivos Excel desde OneDrive usando `pandas` y `glob`
2. **Transforma** los datos: limpia fechas, rellena vacíos, aplica reglas de negocio (clasificación de bolsas FCR, estado de avance)
3. **Carga** los registros procesados a Google Sheets via API usando `gspread`
4. **Visualiza** los KPIs en un dashboard de Looker Studio conectado al Sheet

---

## Arquitectura del pipeline

```
Excel (OneDrive)
    → pandas (extracción y transformación)
    → Google Sheets API (carga)
    → Looker Studio (visualización)
```

---

## Tecnologías utilizadas

| Herramienta | Uso |
|-------------|-----|
| Python 3.14 | Lenguaje principal |
| pandas | Procesamiento y transformación de datos |
| openpyxl | Lectura de archivos Excel (.xlsx) |
| gspread | Conexión con Google Sheets API |
| Google OAuth2 | Autenticación via service account |
| Looker Studio | Dashboard y visualización de KPIs |
| FastAPI + SQLite | App interna de trazabilidad del proceso |

---

## Estructura del proyecto

```
pipeline-etl-rimac/
├── Apy_Google_Sheet.py          # ETL principal → Google Sheets
├── conciliacion.py              # Proceso de conciliación
├── conciliacion_app/            # App web de trazabilidad
│   ├── main.py                  # Punto de entrada FastAPI
│   ├── app/
│   │   ├── config/              # Configuración
│   │   ├── database/            # Conexión SQLite
│   │   ├── models/              # Schemas Pydantic
│   │   ├── routers/             # Endpoints API
│   │   └── services/            # Lógica de negocio
│   └── templates/
│       └── index.html           # Frontend
└── .gitignore
```

---

## KPIs del dashboard

- % Avance de conciliación
- Bolsas FCR pendientes
- Estado del proceso por producto
- Monto dolarizado por estado
- Evolución diaria de registros procesados

---

## Dashboard en vivo

[Ver dashboard en Looker Studio](https://datastudio.google.com/reporting/3c8da9dd-e46f-4847-b60a-8d33e36a088e)

---

## App de trazabilidad

La app interna desarrollada con FastAPI permite:
- Mantenimiento manual de registros
- Log operacional con historial de cambios
- Vista de movimientos delta (diferencias entre actualizaciones)
- Auditoría de estados antes y después de cada modificación

---

## Autor

**Pavel Villegas Moreno**  
Analista de Datos | BI & Automatización de Procesos  
[GitHub](https://github.com/JOAKO2510) | pavel.villegasmo@gmail.com
