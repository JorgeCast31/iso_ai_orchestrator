"""Sprint 2B — plan_loader.py

Loads and normalizes a maintenance plan from an Excel (.xlsx) file.

Design constraints:
  - Uses openpyxl only (no pandas).
  - A single .xlsx must represent exactly ONE familia_equipo.
    Multiple distinct familia_equipo values in valid rows → PlanLoadError.
  - actividad_id uniqueness is assumed by design; duplicates → PlanLoadError.
  - Returning None (not raising) when path is empty allows the pipeline
    to operate in Sprint-2A-compatible mode without plan validation.

Public API:
    PlanLoadError(Exception)
    load_plan_xlsx(path: str) -> dict | None

plan_data contract (returned dict):
  {
    "source_path":    str,           path passed by the caller
    "loaded_at":      str,           ISO timestamp
    "sheet_name":     str,           actual sheet read
    "familia_equipo": str,           stripped, uppercased canonical family code
    "actividades":    list[dict],    one entry per non-empty data row
    "responsables":   list[str],     unique responsable_norm values (sorted)
    "registros":      list[str],     unique registro_codigo values (sorted)
    "frecuencias":    list[str],     unique frecuencia (canonical) values (sorted)
    "nombres_norm":   list[str],     unique nombre_norm values (sorted)
  }

Each actividad dict:
  {
    "equipo_id":       str,   original value
    "actividad_id":    str,   original value
    "nombre":          str,   original value
    "nombre_norm":     str,   lowercased, accent-free, punctuation-stripped
    "frecuencia":      str,   canonical ("mensual", "trimestral", …)
    "frecuencia_raw":  str,   original value from Excel
    "responsable":     str,   original value
    "responsable_norm":str,   lowercased, accent-free, punctuation-stripped
    "registro_codigo": str,   original value (matching is case-insensitive)
  }
"""
import re
import unicodedata
from datetime import datetime

try:
    import openpyxl
    _OPENPYXL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _OPENPYXL_AVAILABLE = False

# ---------------------------------------------------------------------------
# Column name mapping — canonical key → accepted header variants
# (compared after lowercase + strip + underscore-collapse)
# ---------------------------------------------------------------------------
_REQUIRED_COL_ALIASES: dict[str, list[str]] = {
    "equipo_id": [
        "equipo_id", "equipo id", "id_equipo", "id equipo", "equipment_id",
    ],
    "familia_equipo": [
        "familia_equipo", "familia equipo", "familia", "family",
        "familia_equipos",
    ],
    "actividad_id": [
        "actividad_id", "actividad id", "id_actividad", "id actividad",
        "activity_id",
    ],
    "actividad_nombre": [
        "actividad_nombre", "actividad nombre", "nombre_actividad",
        "nombre actividad", "nombre", "actividad", "activity_name",
    ],
    "frecuencia": [
        "frecuencia", "frequency", "periodicidad",
    ],
    "responsable": [
        "responsable", "responsible", "rol_responsable", "rol responsable",
        "rol",
    ],
    "registro_codigo": [
        "registro_codigo", "registro codigo", "codigo_registro",
        "codigo registro", "registro", "formulario", "form_code",
    ],
}

_OPTIONAL_COL_ALIASES: dict[str, list[str]] = {
    "criterio_referencia": [
        "criterio_referencia", "criterio referencia", "criterio",
        "reference", "criterio_de_aceptacion",
    ],
    "observaciones": [
        "observaciones", "notes", "notas", "remarks",
    ],
}

# ---------------------------------------------------------------------------
# Frequency normalization table
# ---------------------------------------------------------------------------
_FRECUENCIA_ALIASES: dict[str, list[str]] = {
    "mensual":     ["mensual", "monthly", "cada mes", "1/mes", "30 dias",
                    "30 días", "cada 30 dias"],
    "trimestral":  ["trimestral", "quarterly", "cada 3 meses",
                    "cada tres meses", "90 dias", "90 días"],
    "semestral":   ["semestral", "semiannual", "semi-annual", "cada 6 meses",
                    "cada seis meses", "180 dias", "180 días"],
    "anual":       ["anual", "yearly", "annual", "cada año", "cada anio",
                    "12 meses", "365 dias", "365 días"],
    "semanal":     ["semanal", "weekly", "cada semana", "7 dias", "7 días"],
    "quincenal":   ["quincenal", "biweekly", "cada 15 dias", "cada 15 días",
                    "cada quince dias"],
}

_PREFERRED_SHEET = "Plan_Mantenimiento"


# ---------------------------------------------------------------------------
# Error class
# ---------------------------------------------------------------------------

class PlanLoadError(Exception):
    """Raised when the maintenance plan file cannot be loaded or normalized."""
    pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize_col_name(value) -> str:
    """Normalize a column header for alias matching."""
    if value is None:
        return ""
    return (
        str(value).strip().lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace(".", "_")
    )


def _normalize_text(text: str) -> str:
    """
    Full normalization for nombre/responsable: lowercase, remove accents,
    collapse whitespace, remove non-word characters (except spaces).
    """
    nfd = unicodedata.normalize("NFD", text)
    ascii_text = nfd.encode("ascii", "ignore").decode("ascii")
    lower = ascii_text.lower()
    cleaned = re.sub(r'[^\w\s]', '', lower)
    return re.sub(r'\s+', ' ', cleaned).strip()


def _normalize_frecuencia(raw: str) -> str:
    """
    Map raw frequency string to a canonical form.
    If not recognized, returns the lowercased stripped raw value so the
    load does not fail — the pipeline continues with a best-effort value.
    """
    raw_norm = _normalize_text(raw)
    for canonical, aliases in _FRECUENCIA_ALIASES.items():
        for alias in aliases:
            alias_norm = _normalize_text(alias)
            if alias_norm == raw_norm or alias_norm in raw_norm:
                return canonical
    # Not recognized — return lowercased original
    return raw.strip().lower()


def _map_columns(
    header_row: tuple,
    all_aliases: dict[str, list[str]],
) -> dict[str, int]:
    """
    Map canonical column names to their 0-based positions in the header row.
    Matching is case-insensitive via _normalize_col_name.
    """
    norm_headers = [_normalize_col_name(h) for h in header_row]
    col_map: dict[str, int] = {}

    for canonical, aliases in all_aliases.items():
        for pos, norm_header in enumerate(norm_headers):
            if norm_header and (norm_header in aliases or norm_header == canonical):
                col_map[canonical] = pos
                break  # first match wins

    return col_map


def _cell_str(row: tuple, pos: int) -> str:
    """Safely extract and stringify a cell value from a row tuple."""
    if pos >= len(row):
        return ""
    val = row[pos]
    return "" if val is None else str(val).strip()


def _is_empty_row(row: tuple) -> bool:
    """True when all cells in the row are None or blank strings."""
    return all(v is None or str(v).strip() == "" for v in row)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_plan_xlsx(path: str) -> "dict | None":
    """
    Load and normalize a maintenance plan from an .xlsx file.

    Returns plan_data dict on success, or None if path is empty/None.
    Raises PlanLoadError for any structural or data integrity issue.
    """
    if not path:
        return None

    if not _OPENPYXL_AVAILABLE:  # pragma: no cover
        raise PlanLoadError(
            "openpyxl no está instalado. Instala con: pip install openpyxl"
        )

    # --- Open workbook ---
    try:
        wb = openpyxl.load_workbook(path, data_only=True)
    except FileNotFoundError:
        raise PlanLoadError(f"Archivo de plan no encontrado: {path!r}")
    except Exception as exc:
        raise PlanLoadError(
            f"No se pudo abrir el archivo de plan '{path}': {exc}"
        ) from exc

    # --- Select sheet ---
    if _PREFERRED_SHEET in wb.sheetnames:
        ws = wb[_PREFERRED_SHEET]
    else:
        ws = wb.active

    sheet_name = ws.title
    rows = list(ws.values)

    if not rows:
        raise PlanLoadError(
            f"La hoja '{sheet_name}' en '{path}' está completamente vacía."
        )

    # --- Map columns ---
    header_row = rows[0]
    all_aliases = {**_REQUIRED_COL_ALIASES, **_OPTIONAL_COL_ALIASES}
    col_map = _map_columns(header_row, all_aliases)

    missing_required = [
        col for col in _REQUIRED_COL_ALIASES if col not in col_map
    ]
    if missing_required:
        detected = [
            str(h).strip() for h in header_row
            if h is not None and str(h).strip()
        ]
        raise PlanLoadError(
            f"Columnas obligatorias no encontradas en '{sheet_name}': "
            f"{sorted(missing_required)}. "
            f"Columnas detectadas: {detected}"
        )

    # --- Parse data rows ---
    actividades: list[dict] = []
    seen_actividad_ids: set[str] = set()
    familias: set[str] = set()

    for row_num, row in enumerate(rows[1:], start=2):
        if _is_empty_row(row):
            continue  # skip blank separator rows

        equipo_id      = _cell_str(row, col_map["equipo_id"])
        familia_raw    = _cell_str(row, col_map["familia_equipo"])
        actividad_id   = _cell_str(row, col_map["actividad_id"])
        nombre         = _cell_str(row, col_map["actividad_nombre"])
        frecuencia_raw = _cell_str(row, col_map["frecuencia"])
        responsable    = _cell_str(row, col_map["responsable"])
        registro_codigo= _cell_str(row, col_map["registro_codigo"])

        # Validate required fields per row
        empty_fields = [
            field for field, val in [
                ("equipo_id", equipo_id),
                ("familia_equipo", familia_raw),
                ("actividad_id", actividad_id),
                ("actividad_nombre", nombre),
                ("frecuencia", frecuencia_raw),
                ("responsable", responsable),
                ("registro_codigo", registro_codigo),
            ] if not val
        ]
        if empty_fields:
            raise PlanLoadError(
                f"Fila {row_num}: campos obligatorios vacíos: {empty_fields}"
            )

        # Check actividad_id uniqueness
        if actividad_id in seen_actividad_ids:
            raise PlanLoadError(
                f"actividad_id duplicado '{actividad_id}' en fila {row_num}. "
                "Los identificadores de actividad deben ser únicos en el plan."
            )
        seen_actividad_ids.add(actividad_id)

        # Track familia_equipo for consistency check (uppercase for comparison)
        familias.add(familia_raw.strip().upper())

        actividades.append({
            "equipo_id":        equipo_id,
            "actividad_id":     actividad_id,
            "nombre":           nombre,
            "nombre_norm":      _normalize_text(nombre),
            "frecuencia":       _normalize_frecuencia(frecuencia_raw),
            "frecuencia_raw":   frecuencia_raw,
            "responsable":      responsable,
            "responsable_norm": _normalize_text(responsable),
            "registro_codigo":  registro_codigo,
        })

    if not actividades:
        raise PlanLoadError(
            f"El plan en '{path}' (hoja '{sheet_name}') no contiene "
            "filas de datos válidas."
        )

    # --- Enforce single familia_equipo ---
    if len(familias) > 1:
        raise PlanLoadError(
            f"El plan contiene múltiples familias de equipo: {sorted(familias)}. "
            "Cada archivo .xlsx debe representar una sola familia."
        )

    familia_equipo = familias.pop()  # already uppercased

    # --- Build derived views ---
    responsables = sorted({a["responsable_norm"] for a in actividades})
    registros    = sorted({a["registro_codigo"]   for a in actividades})
    frecuencias  = sorted({a["frecuencia"]         for a in actividades})
    nombres_norm = sorted({a["nombre_norm"]        for a in actividades})

    return {
        "source_path":    path,
        "loaded_at":      datetime.now().isoformat(),
        "sheet_name":     sheet_name,
        "familia_equipo": familia_equipo,
        "actividades":    actividades,
        "responsables":   responsables,
        "registros":      registros,
        "frecuencias":    frecuencias,
        "nombres_norm":   nombres_norm,
    }
