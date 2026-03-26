"""
Unit tests for src/document_validator.py
No API calls — 100% offline.
"""
import pytest
from src.document_validator import validate_document, VALIDATOR_VERSION


# ---------------------------------------------------------------------------
# Fixtures — reusable document strings
# ---------------------------------------------------------------------------

def _make_full_doc(
    objetivo="Establecer el procedimiento de mantenimiento preventivo.",
    alcance="Aplica a todos los equipos de laboratorio.",
    responsabilidades="El Técnico de Mantenimiento ejecuta las actividades.",
    procedimiento="Realizar inspección visual y verificación de conexiones.",
    gestion_desviaciones="Documentar y clasificar hallazgos según severidad.",
    registros="FOR-MTO-001: Registro de mantenimiento preventivo.",
    extra_sections="",
):
    """Build a minimal POE with all required sections."""
    return f"""\
## 1. OBJETIVO

{objetivo}

## 2. ALCANCE

{alcance}

## 3. RESPONSABILIDADES

{responsabilidades}

## 5. PROCEDIMIENTO

{procedimiento}

### 5.5 Acciones ante desviaciones

{gestion_desviaciones}

## 6. REGISTROS

{registros}
{extra_sections}
"""


FULL_VALID_DOC = _make_full_doc()

DOC_WITH_OPTIONAL_SECTIONS = _make_full_doc() + """\
## 4. DEFINICIONES

Términos aplicables al procedimiento.

## 8. REFERENCIAS

Normativa ISO 9001:2015.

## 9. CONTROL DE CAMBIOS

Versión 01 — emisión inicial.

## 10. HISTORIAL DE MODIFICACIONES

| Versión | Fecha | Descripción |
|---------|-------|-------------|
| 01      | ...   | Emisión inicial |
"""

DOC_NO_PROCEDIMIENTO = """\
## 1. OBJETIVO

Establecer el procedimiento.

## 2. ALCANCE

Aplica a todos los equipos.

## 3. RESPONSABILIDADES

El Técnico ejecuta.

### 5.5 Acciones ante desviaciones

Documentar hallazgos.

## 6. REGISTROS

FOR-MTO-001.
"""

DOC_VALIDAR_IN_RESPONSABILIDADES = _make_full_doc(
    responsabilidades="El responsable es [VALIDAR] según asignación de área."
)

DOC_VALIDAR_IN_PROCEDIMIENTO = _make_full_doc(
    procedimiento="Ejecutar actividad [VALIDAR] según protocolo pendiente."
)

DOC_VALIDAR_IN_GESTION = _make_full_doc(
    gestion_desviaciones="Escalar a [VALIDAR] según severidad del hallazgo."
)

DOC_VALIDAR_IN_REGISTROS = _make_full_doc(
    registros="FOR-MTO-[VALIDAR]: Registro pendiente de asignación."
)

DOC_VALIDAR_IN_REFERENCIAS_ONLY = _make_full_doc() + """\
## 7. REFERENCIAS

Ver normativa aplicable [VALIDAR] pendiente de revisión.
"""

ALT_HEADINGS_DOC = """\
# Objetivo del Procedimiento

Establecer la metodología de mantenimiento.

# Alcance y Aplicación

Aplica a todos los equipos.

# Roles y Responsabilidades

El Técnico ejecuta las actividades programadas.

# Procedimiento Detallado

Realizar las actividades de mantenimiento según cronograma.

# Acciones ante Desviaciones

Documentar y clasificar hallazgos.

# Registros Asociados

FOR-MTO-001: Registro de mantenimiento.
"""


# ---------------------------------------------------------------------------
# Test: valid document
# ---------------------------------------------------------------------------

def test_full_valid_doc_is_valid():
    result = validate_document(FULL_VALID_DOC)
    assert result["valid"] is True
    assert result["blocking_findings"] == []


def test_valid_doc_with_optional_sections_is_valid():
    result = validate_document(DOC_WITH_OPTIONAL_SECTIONS)
    assert result["valid"] is True
    assert result["blocking_findings"] == []


def test_alternative_headings_doc_is_valid():
    """Document using non-numbered alternative headings must pass validation."""
    result = validate_document(ALT_HEADINGS_DOC)
    assert result["valid"] is True, (
        f"Alt headings doc falló — blocking: {result['blocking_findings']}"
    )


# ---------------------------------------------------------------------------
# Test: blocking rules — missing required sections
# ---------------------------------------------------------------------------

def test_missing_procedimiento_is_blocking():
    result = validate_document(DOC_NO_PROCEDIMIENTO)
    assert result["valid"] is False
    rule_ids = [f["rule_id"] for f in result["blocking_findings"]]
    assert "RULE-004" in rule_ids


def test_empty_document_all_required_sections_blocked():
    result = validate_document("")
    assert result["valid"] is False
    rule_ids = [f["rule_id"] for f in result["blocking_findings"]]
    # All 6 required sections missing → 6 blocking findings
    for rule_id in ("RULE-001", "RULE-002", "RULE-003", "RULE-004", "RULE-005", "RULE-006"):
        assert rule_id in rule_ids, f"{rule_id} missing from blocking_findings"


def test_missing_objetivo_blocking():
    doc = _make_full_doc(objetivo="")
    result = validate_document(doc)
    assert result["valid"] is False
    assert any(f["rule_id"] == "RULE-001" for f in result["blocking_findings"])


def test_missing_alcance_blocking():
    doc = _make_full_doc(alcance="")
    result = validate_document(doc)
    assert result["valid"] is False
    assert any(f["rule_id"] == "RULE-002" for f in result["blocking_findings"])


def test_missing_responsabilidades_blocking():
    doc = _make_full_doc(responsabilidades="")
    result = validate_document(doc)
    assert result["valid"] is False
    assert any(f["rule_id"] == "RULE-003" for f in result["blocking_findings"])


def test_missing_gestion_desviaciones_blocking():
    doc = _make_full_doc(gestion_desviaciones="")
    result = validate_document(doc)
    assert result["valid"] is False
    assert any(f["rule_id"] == "RULE-005" for f in result["blocking_findings"])


def test_missing_registros_blocking():
    doc = _make_full_doc(registros="")
    result = validate_document(doc)
    assert result["valid"] is False
    assert any(f["rule_id"] == "RULE-006" for f in result["blocking_findings"])


# ---------------------------------------------------------------------------
# Test: blocking rules — [VALIDAR] in critical sections
# ---------------------------------------------------------------------------

def test_validar_in_responsabilidades_is_blocking():
    result = validate_document(DOC_VALIDAR_IN_RESPONSABILIDADES)
    assert result["valid"] is False
    rule_ids = [f["rule_id"] for f in result["blocking_findings"]]
    assert "RULE-007" in rule_ids


def test_validar_in_procedimiento_is_blocking():
    result = validate_document(DOC_VALIDAR_IN_PROCEDIMIENTO)
    assert result["valid"] is False
    rule_ids = [f["rule_id"] for f in result["blocking_findings"]]
    assert "RULE-008" in rule_ids


def test_validar_in_gestion_desviaciones_is_blocking():
    result = validate_document(DOC_VALIDAR_IN_GESTION)
    assert result["valid"] is False
    rule_ids = [f["rule_id"] for f in result["blocking_findings"]]
    assert "RULE-009" in rule_ids


def test_validar_in_registros_is_blocking():
    result = validate_document(DOC_VALIDAR_IN_REGISTROS)
    assert result["valid"] is False
    rule_ids = [f["rule_id"] for f in result["blocking_findings"]]
    assert "RULE-010" in rule_ids


# ---------------------------------------------------------------------------
# Test: observations — [VALIDAR] in non-critical sections is NOT blocking
# ---------------------------------------------------------------------------

def test_validar_in_referencias_is_not_blocking():
    result = validate_document(DOC_VALIDAR_IN_REFERENCIAS_ONLY)
    # Should still be valid (no blocking findings from the [VALIDAR] in references)
    blocking_rule_ids = [f["rule_id"] for f in result["blocking_findings"]]
    # RULE-007 through RULE-010 must NOT be present
    for rule_id in ("RULE-007", "RULE-008", "RULE-009", "RULE-010"):
        assert rule_id not in blocking_rule_ids
    # The [VALIDAR] in referencias must appear as an OBS-005 observation
    obs_rule_ids = [o["rule_id"] for o in result["observations"]]
    assert "OBS-005" in obs_rule_ids


def test_validar_in_referencias_does_not_invalidate():
    result = validate_document(DOC_VALIDAR_IN_REFERENCIAS_ONLY)
    assert result["valid"] is True


# ---------------------------------------------------------------------------
# Test: observations — optional sections
# ---------------------------------------------------------------------------

def test_minimal_doc_missing_optional_sections_generates_observations():
    result = validate_document(FULL_VALID_DOC)
    obs_rule_ids = [o["rule_id"] for o in result["observations"]]
    # Without optional sections: should have OBS-001 through OBS-004
    assert "OBS-001" in obs_rule_ids  # definiciones
    assert "OBS-002" in obs_rule_ids  # referencias
    assert "OBS-003" in obs_rule_ids  # control_cambios
    assert "OBS-004" in obs_rule_ids  # historial_modificaciones


def test_doc_with_all_optional_sections_no_obs_001_to_004():
    result = validate_document(DOC_WITH_OPTIONAL_SECTIONS)
    obs_rule_ids = [o["rule_id"] for o in result["observations"]]
    for obs_id in ("OBS-001", "OBS-002", "OBS-003", "OBS-004"):
        assert obs_id not in obs_rule_ids, f"{obs_id} should not appear when section is present"


# ---------------------------------------------------------------------------
# Test: validar_count
# ---------------------------------------------------------------------------

def test_validar_count_zero_for_clean_doc():
    result = validate_document(FULL_VALID_DOC)
    assert result["validar_count"] == 0


def test_validar_count_correct():
    # DOC_VALIDAR_IN_RESPONSABILIDADES has exactly 1 [VALIDAR]
    result = validate_document(DOC_VALIDAR_IN_RESPONSABILIDADES)
    assert result["validar_count"] == 1


# ---------------------------------------------------------------------------
# Test: RULE-000 — unstructured document (content present but no headings)
# ---------------------------------------------------------------------------

PLAIN_TEXT_DOC = (
    "Este documento describe el procedimiento de mantenimiento preventivo "
    "para los sistemas de gases instalados en el laboratorio. "
    "El técnico de mantenimiento ejecutará inspección visual, verificación "
    "de conexiones y revisión de fugas según las instrucciones del fabricante. "
    "Cualquier desviación deberá documentarse en el registro FOR-MTO-001."
)  # Long enough to trigger RULE-000 (>= 100 chars), no markdown headings


def test_unstructured_doc_triggers_rule_000():
    """Non-empty document without recognizable sections must produce RULE-000."""
    result = validate_document(PLAIN_TEXT_DOC)
    assert result["valid"] is False
    rule_ids = [f["rule_id"] for f in result["blocking_findings"]]
    assert "RULE-000" in rule_ids


def test_unstructured_doc_rule_000_has_evidence():
    result = validate_document(PLAIN_TEXT_DOC)
    r000 = next(f for f in result["blocking_findings"] if f["rule_id"] == "RULE-000")
    assert r000["evidence"]  # must have diagnostic context, not empty


def test_structured_doc_no_rule_000():
    """Valid structured document must never produce RULE-000."""
    result = validate_document(FULL_VALID_DOC)
    rule_ids = [f["rule_id"] for f in result["blocking_findings"]]
    assert "RULE-000" not in rule_ids


def test_empty_doc_no_rule_000():
    """Empty string is short → RULE-000 threshold not met; no spurious finding."""
    result = validate_document("")
    rule_ids = [f["rule_id"] for f in result["blocking_findings"]]
    assert "RULE-000" not in rule_ids


# ---------------------------------------------------------------------------
# Test: return dict contract
# ---------------------------------------------------------------------------

def test_return_keys_always_present():
    for doc in ("", FULL_VALID_DOC, DOC_NO_PROCEDIMIENTO):
        result = validate_document(doc)
        for key in ("valid", "blocking_findings", "observations",
                    "validar_count", "validated_at", "validator_version"):
            assert key in result, f"Key '{key}' missing for doc variant"


def test_validator_version():
    result = validate_document(FULL_VALID_DOC)
    assert result["validator_version"] == VALIDATOR_VERSION


def test_blocking_findings_shape():
    result = validate_document(DOC_NO_PROCEDIMIENTO)
    for finding in result["blocking_findings"]:
        for key in ("rule_id", "section", "message", "evidence"):
            assert key in finding, f"Key '{key}' missing in blocking_finding"


def test_observations_shape():
    result = validate_document(FULL_VALID_DOC)
    for obs in result["observations"]:
        for key in ("rule_id", "section", "message", "evidence"):
            assert key in obs, f"Key '{key}' missing in observation"
