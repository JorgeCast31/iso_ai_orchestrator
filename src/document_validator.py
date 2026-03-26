"""Sprint 2B — document_validator.py

Deterministic structural validator for POE documents.

Accepts raw document text + optional plan_data, calls extract_document_structure
internally, and applies the full Sprint 2A + Sprint 2B rule set:
  - Blocking rules : required sections absent/empty, [VALIDAR] in critical sections,
                     plan cross-checks (RULE-P01, RULE-P02, RULE-P03).
  - Observations   : optional sections absent, [VALIDAR] in non-critical sections,
                     plan cross-checks (OBS-P01, OBS-P02, OBS-P03, OBS-P04).

Public API:
    validate_document(document_text: str, plan_data: dict | None = None) -> dict

Return contract:
  {
    "valid":                          bool,
    "blocking_findings":              list[dict],  # [{rule_id, section, message, evidence}]
    "observations":                   list[dict],  # same shape
    "validar_count":                  int,
    "validated_at":                   str,         # ISO timestamp
    "validator_version":              str,
  }
"""
import unicodedata
from datetime import datetime

from src.document_extractor import extract_document_structure

VALIDATOR_VERSION = "2.0"

# ---------------------------------------------------------------------------
# Rule tables — centralized so Sprint 2B can extend without touching logic
# ---------------------------------------------------------------------------

# Sections that must be present and non-empty for a valid document
_REQUIRED_SECTION_RULES: dict[str, tuple[str, str]] = {
    "objetivo":             ("RULE-001", "Sección OBJETIVO ausente o vacía"),
    "alcance":              ("RULE-002", "Sección ALCANCE ausente o vacía"),
    "responsabilidades":    ("RULE-003", "Sección RESPONSABILIDADES ausente o vacía"),
    "procedimiento":        ("RULE-004", "Sección PROCEDIMIENTO ausente o vacía"),
    "gestion_desviaciones": ("RULE-005", "Sección GESTIÓN DE DESVIACIONES ausente o vacía"),
    "registros":            ("RULE-006", "Sección REGISTROS ausente o vacía"),
}

# Sections where [VALIDAR] is a blocking finding
_VALIDAR_BLOCKING_RULES: dict[str, str] = {
    "responsabilidades":    "RULE-007",
    "procedimiento":        "RULE-008",
    "gestion_desviaciones": "RULE-009",
    "registros":            "RULE-010",
}

# Optional sections whose absence generates an observation
_OPTIONAL_SECTION_RULES: dict[str, tuple[str, str]] = {
    "definiciones":             ("OBS-001", "Sección DEFINICIONES ausente (recomendada)"),
    "referencias":              ("OBS-002", "Sección REFERENCIAS ausente (recomendada)"),
    "control_cambios":          ("OBS-003", "Sección CONTROL DE CAMBIOS ausente"),
    "historial_modificaciones": ("OBS-004", "Sección HISTORIAL DE MODIFICACIONES ausente"),
}


# ---------------------------------------------------------------------------
# Normalized matching helper
# ---------------------------------------------------------------------------

def _nfm(text: str) -> str:
    """Normalize for loose matching: accent-free lowercase."""
    nfd = unicodedata.normalize("NFD", text)
    return nfd.encode("ascii", "ignore").decode("ascii").lower()


# ---------------------------------------------------------------------------
# Plan cross-rule helpers
# ---------------------------------------------------------------------------

def _check_plan_rules(
    plan_data: dict,
    document_text: str,
    sections: dict,
    blocked_sections: set,
    blocking: list,
    observations: list,
) -> None:
    """
    Apply Sprint 2B cross-rules between plan_data and document content.
    Guard: skip cross-checks for sections already blocked by base rules to
    avoid redundant, noisy findings.
    """
    doc_norm = _nfm(document_text)

    # RULE-P01 — familia_equipo must appear somewhere in the document
    familia = plan_data.get("familia_equipo", "")
    if familia and _nfm(familia) not in doc_norm:
        blocking.append({
            "rule_id": "RULE-P01",
            "section": "document",
            "message": (
                f"La familia de equipo '{familia}' del plan no está mencionada "
                "en el documento POE."
            ),
            "evidence": familia,
        })

    # RULE-P02 — every responsable_norm from plan must appear in RESPONSABILIDADES
    if "responsabilidades" not in blocked_sections:
        resp_text = _nfm(sections.get("responsabilidades", ""))
        missing_resp = [
            r for r in plan_data.get("responsables", [])
            if r and r not in resp_text
        ]
        for resp in missing_resp:
            blocking.append({
                "rule_id": "RULE-P02",
                "section": "responsabilidades",
                "message": (
                    f"El responsable '{resp}' del plan no está mencionado "
                    "en la sección RESPONSABILIDADES del documento."
                ),
                "evidence": resp,
            })

    # RULE-P03 — every registro_codigo from plan must appear in REGISTROS (case-insensitive)
    if "registros" not in blocked_sections:
        reg_text = _nfm(sections.get("registros", ""))
        missing_reg = [
            r for r in plan_data.get("registros", [])
            if r and _nfm(r) not in reg_text
        ]
        for reg in missing_reg:
            blocking.append({
                "rule_id": "RULE-P03",
                "section": "registros",
                "message": (
                    f"El registro '{reg}' del plan no está mencionado "
                    "en la sección REGISTROS del documento."
                ),
                "evidence": reg,
            })

    frecuencias = plan_data.get("frecuencias", [])

    # OBS-P03 — multiple frecuencias in plan
    if len(frecuencias) > 1:
        observations.append({
            "rule_id": "OBS-P03",
            "section": "document",
            "message": (
                f"El plan contiene múltiples frecuencias: {sorted(frecuencias)}. "
                "Verifique que el documento aborde todas las periodicidades."
            ),
            "evidence": ", ".join(sorted(frecuencias)),
        })

    # OBS-P01 and OBS-P04 — both check the PROCEDIMIENTO section text;
    # compute once and skip entirely when that section is already blocked.
    if "procedimiento" not in blocked_sections:
        proc_text = _nfm(sections.get("procedimiento", ""))

        # OBS-P01 — actividad nombre_norm not found in PROCEDIMIENTO
        for actividad in plan_data.get("actividades", []):
            nombre_norm = actividad.get("nombre_norm", "")
            if nombre_norm and nombre_norm not in proc_text:
                act_id = actividad.get("actividad_id", "?")
                nombre = actividad.get("nombre", nombre_norm)
                observations.append({
                    "rule_id": "OBS-P01",
                    "section": "procedimiento",
                    "message": (
                        f"La actividad '{nombre}' (id: {act_id}) "
                        "no está mencionada en la sección PROCEDIMIENTO."
                    ),
                    "evidence": nombre_norm,
                })

        # OBS-P04 — each canonical frecuencia not found in PROCEDIMIENTO
        for frec in frecuencias:
            if frec and _nfm(frec) not in proc_text:
                observations.append({
                    "rule_id": "OBS-P04",
                    "section": "procedimiento",
                    "message": (
                        f"La frecuencia '{frec}' del plan no está mencionada "
                        "en la sección PROCEDIMIENTO."
                    ),
                    "evidence": frec,
                })


def validate_document(document_text: str, plan_data: "dict | None" = None) -> dict:
    """
    Run Sprint 2A + Sprint 2B structural validation on a POE document.

    plan_data: optional dict returned by load_plan_xlsx(); if None, cross-rules
    are not applied (pipeline continues in Sprint-2A-compatible mode).

    If the extractor raises unexpectedly, returns valid=False with RULE-000
    so the pipeline treats it as a validator reject rather than a fatal crash.
    """
    blocking: list[dict] = []
    observations: list[dict] = []

    try:
        doc_structure = extract_document_structure(document_text)
    except Exception as exc:  # pragma: no cover — defensive fallback
        return {
            "valid": False,
            "blocking_findings": [{
                "rule_id": "RULE-000",
                "section": "document",
                "message": f"El documento no puede ser analizado estructuralmente: {exc}",
                "evidence": document_text[:200].replace('\n', ' '),
            }],
            "observations": [],
            "validar_count": 0,
            "validated_at": datetime.now().isoformat(),
            "validator_version": VALIDATOR_VERSION,
        }

    sections = doc_structure["sections"]
    validar_pendientes = doc_structure["validar_pendientes"]
    sections_found = doc_structure["sections_found"]

    # -----------------------------------------------------------------------
    # Blocking: RULE-000 — document has content but no recognizable sections.
    # Fires only when the document is non-trivially long yet the extractor
    # found zero canonical headings, indicating a format/heading issue rather
    # than genuinely absent content.  Makes the diagnosis unambiguous.
    # -----------------------------------------------------------------------
    _MIN_UNSTRUCTURED_DOC_LEN = 100
    if not sections_found and len(document_text.strip()) >= _MIN_UNSTRUCTURED_DOC_LEN:
        blocking.append({
            "rule_id": "RULE-000",
            "section": "document",
            "message": (
                "No se detectaron secciones estructuradas en el documento. "
                "Verifique que el formato use encabezados markdown (## SECCIÓN)."
            ),
            "evidence": document_text[:200].replace('\n', ' ').strip(),
        })

    # -----------------------------------------------------------------------
    # Blocking rules: required sections must be present and non-empty
    # -----------------------------------------------------------------------
    blocked_sections: set = set()
    for section_key, (rule_id, message) in _REQUIRED_SECTION_RULES.items():
        if not sections.get(section_key, "").strip():
            blocked_sections.add(section_key)
            blocking.append({
                "rule_id": rule_id,
                "section": section_key,
                "message": message,
                "evidence": "",
            })

    # -----------------------------------------------------------------------
    # Blocking rules: [VALIDAR] in critical sections
    # -----------------------------------------------------------------------
    for marker in validar_pendientes:
        section = marker["section"]
        if section in _VALIDAR_BLOCKING_RULES:
            blocking.append({
                "rule_id": _VALIDAR_BLOCKING_RULES[section],
                "section": section,
                "message": f"[VALIDAR] pendiente en sección crítica '{section}'",
                "evidence": marker["evidence"],
            })

    # -----------------------------------------------------------------------
    # Observations: optional sections absent
    # -----------------------------------------------------------------------
    for section_key, (obs_id, message) in _OPTIONAL_SECTION_RULES.items():
        if section_key not in sections:
            observations.append({
                "rule_id": obs_id,
                "section": section_key,
                "message": message,
                "evidence": "",
            })

    # -----------------------------------------------------------------------
    # Observations: [VALIDAR] in non-critical sections
    # -----------------------------------------------------------------------
    for marker in validar_pendientes:
        if marker["section"] not in _VALIDAR_BLOCKING_RULES:
            observations.append({
                "rule_id": "OBS-005",
                "section": marker["section"],
                "message": f"[VALIDAR] pendiente en sección no crítica '{marker['section']}'",
                "evidence": marker["evidence"],
            })

    # -----------------------------------------------------------------------
    # Sprint 2B — Plan cross-rules
    # -----------------------------------------------------------------------
    if plan_data is not None:
        _check_plan_rules(
            plan_data, document_text, sections, blocked_sections, blocking, observations
        )
    else:
        observations.append({
            "rule_id": "OBS-P02",
            "section": "document",
            "message": (
                "No se cargó un plan de mantenimiento (.xlsx). "
                "No es posible verificar coherencia entre el plan y el documento."
            ),
            "evidence": "",
        })

    return {
        "valid": len(blocking) == 0,
        "blocking_findings": blocking,
        "observations": observations,
        "validar_count": len(validar_pendientes),
        "validated_at": datetime.now().isoformat(),
        "validator_version": VALIDATOR_VERSION,
    }
