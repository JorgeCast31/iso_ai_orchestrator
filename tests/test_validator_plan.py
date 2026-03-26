"""Sprint 2B — tests for document_validator.py cross-rules with plan_data.

All tests are offline.  plan_data dicts are constructed directly
(not loaded from .xlsx) to avoid I/O in unit tests.
"""
import pytest

from src.document_validator import validate_document


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FULL_VALID_DOC = """\
## 1. Objetivo
Establecer el procedimiento para el mantenimiento de sistemas de gas FAM:GAS.

## 2. Alcance
Aplica a todos los sistemas de gases del laboratorio.

## 3. Responsabilidades
El tecnico de mantenimiento es responsable de ejecutar las actividades.

## 4. Procedimiento
Se realiza inspección visual mensual de los equipos.
Verificar conexiones y detectar fugas.

## 5. Gestión de Desviaciones
Ante cualquier desviación se notifica al supervisor.

## 6. Registros
Se debe completar el formulario REG-001 para cada actividad.
"""


def _make_plan(
    familia="FAM:GAS",
    responsables=None,
    registros=None,
    frecuencias=None,
    actividades=None,
):
    """Build a minimal plan_data dict for testing."""
    if responsables is None:
        responsables = ["tecnico de mantenimiento"]
    if registros is None:
        registros = ["REG-001"]
    if frecuencias is None:
        frecuencias = ["mensual"]
    if actividades is None:
        actividades = [
            {
                "equipo_id": "EQ-001",
                "actividad_id": "ACT-001",
                "nombre": "Inspección visual",
                "nombre_norm": "inspeccion visual",
                "frecuencia": "mensual",
                "frecuencia_raw": "mensual",
                "responsable": "Técnico de Mantenimiento",
                "responsable_norm": "tecnico de mantenimiento",
                "registro_codigo": "REG-001",
            }
        ]
    return {
        "source_path": "inputs/plan_test.xlsx",
        "familia_equipo": familia,
        "actividades": actividades,
        "responsables": responsables,
        "registros": registros,
        "frecuencias": frecuencias,
        "nombres_norm": [a["nombre_norm"] for a in actividades],
    }


# ---------------------------------------------------------------------------
# OBS-P02: no plan loaded
# ---------------------------------------------------------------------------

def test_no_plan_adds_obs_p02():
    result = validate_document(_FULL_VALID_DOC, plan_data=None)
    obs_ids = [o["rule_id"] for o in result["observations"]]
    assert "OBS-P02" in obs_ids


def test_plan_present_no_obs_p02():
    result = validate_document(_FULL_VALID_DOC, plan_data=_make_plan())
    obs_ids = [o["rule_id"] for o in result["observations"]]
    assert "OBS-P02" not in obs_ids


# ---------------------------------------------------------------------------
# RULE-P01: familia_equipo in document
# ---------------------------------------------------------------------------

def test_rule_p01_passes_when_familia_in_doc():
    result = validate_document(_FULL_VALID_DOC, plan_data=_make_plan(familia="FAM:GAS"))
    blocking_ids = [f["rule_id"] for f in result["blocking_findings"]]
    assert "RULE-P01" not in blocking_ids


def test_rule_p01_fires_when_familia_missing():
    result = validate_document(_FULL_VALID_DOC, plan_data=_make_plan(familia="FAM:XXX"))
    blocking_ids = [f["rule_id"] for f in result["blocking_findings"]]
    assert "RULE-P01" in blocking_ids


def test_rule_p01_case_insensitive():
    # FAM:GAS in doc (uppercase), plan has lowercase version
    doc = _FULL_VALID_DOC.replace("FAM:GAS", "fam:gas")
    result = validate_document(doc, plan_data=_make_plan(familia="FAM:GAS"))
    blocking_ids = [f["rule_id"] for f in result["blocking_findings"]]
    assert "RULE-P01" not in blocking_ids


# ---------------------------------------------------------------------------
# RULE-P02: responsable in RESPONSABILIDADES section
# ---------------------------------------------------------------------------

def test_rule_p02_passes_when_responsable_in_section():
    result = validate_document(_FULL_VALID_DOC, plan_data=_make_plan())
    blocking_ids = [f["rule_id"] for f in result["blocking_findings"]]
    assert "RULE-P02" not in blocking_ids


def test_rule_p02_fires_when_responsable_missing():
    plan = _make_plan(responsables=["supervisor de calidad"])
    result = validate_document(_FULL_VALID_DOC, plan_data=plan)
    blocking_ids = [f["rule_id"] for f in result["blocking_findings"]]
    assert "RULE-P02" in blocking_ids


def test_rule_p02_skipped_when_section_already_blocked():
    """RULE-P02 should not fire when RESPONSABILIDADES is absent (RULE-003 already blocks)."""
    doc_without_resp = """\
## 1. Objetivo
Establecer el procedimiento.

## 2. Alcance
Aplica a todos.

## 4. Procedimiento
Proceso mensual.

## 5. Gestión de Desviaciones
Notificar supervisor.

## 6. Registros
Completar REG-001.
"""
    plan = _make_plan(responsables=["supervisor de calidad"])
    result = validate_document(doc_without_resp, plan_data=plan)
    blocking_ids = [f["rule_id"] for f in result["blocking_findings"]]
    # RULE-003 fires (section absent), but RULE-P02 should NOT add redundant finding
    assert "RULE-003" in blocking_ids
    assert "RULE-P02" not in blocking_ids


# ---------------------------------------------------------------------------
# RULE-P03: registro_codigo in REGISTROS section
# ---------------------------------------------------------------------------

def test_rule_p03_passes_when_registro_in_section():
    result = validate_document(_FULL_VALID_DOC, plan_data=_make_plan(registros=["REG-001"]))
    blocking_ids = [f["rule_id"] for f in result["blocking_findings"]]
    assert "RULE-P03" not in blocking_ids


def test_rule_p03_fires_when_registro_missing():
    plan = _make_plan(registros=["REG-999"])
    result = validate_document(_FULL_VALID_DOC, plan_data=plan)
    blocking_ids = [f["rule_id"] for f in result["blocking_findings"]]
    assert "RULE-P03" in blocking_ids


def test_rule_p03_skipped_when_section_already_blocked():
    """RULE-P03 should not fire when REGISTROS section is absent."""
    doc_without_reg = """\
## 1. Objetivo
Establecer el procedimiento.

## 2. Alcance
Aplica a todos.

## 3. Responsabilidades
El tecnico de mantenimiento ejecuta.

## 4. Procedimiento
Proceso mensual.

## 5. Gestión de Desviaciones
Notificar supervisor.
"""
    plan = _make_plan(registros=["REG-999"])
    result = validate_document(doc_without_reg, plan_data=plan)
    blocking_ids = [f["rule_id"] for f in result["blocking_findings"]]
    assert "RULE-006" in blocking_ids
    assert "RULE-P03" not in blocking_ids


# ---------------------------------------------------------------------------
# OBS-P01: actividad nombre_norm not in PROCEDIMIENTO
# ---------------------------------------------------------------------------

def test_obs_p01_not_fired_when_actividad_in_procedimiento():
    result = validate_document(_FULL_VALID_DOC, plan_data=_make_plan())
    obs_ids = [o["rule_id"] for o in result["observations"]]
    assert "OBS-P01" not in obs_ids


def test_obs_p01_fires_when_actividad_missing_from_procedimiento():
    plan = _make_plan(
        actividades=[{
            "equipo_id": "EQ-001",
            "actividad_id": "ACT-002",
            "nombre": "Calibración de sensores",
            "nombre_norm": "calibracion de sensores",
            "frecuencia": "mensual",
            "frecuencia_raw": "mensual",
            "responsable": "Técnico de Mantenimiento",
            "responsable_norm": "tecnico de mantenimiento",
            "registro_codigo": "REG-001",
        }]
    )
    result = validate_document(_FULL_VALID_DOC, plan_data=plan)
    obs_ids = [o["rule_id"] for o in result["observations"]]
    assert "OBS-P01" in obs_ids


def test_obs_p01_skipped_when_procedimiento_blocked():
    """OBS-P01 should not fire when PROCEDIMIENTO section is absent."""
    doc_without_proc = """\
## 1. Objetivo
Establecer el procedimiento.

## 2. Alcance
Aplica a todos.

## 3. Responsabilidades
El tecnico de mantenimiento ejecuta.

## 5. Gestión de Desviaciones
Notificar supervisor.

## 6. Registros
Completar REG-001.
"""
    plan = _make_plan(actividades=[{
        "equipo_id": "EQ-001", "actividad_id": "ACT-001",
        "nombre": "Calibración", "nombre_norm": "calibracion",
        "frecuencia": "mensual", "frecuencia_raw": "mensual",
        "responsable": "Técnico", "responsable_norm": "tecnico",
        "registro_codigo": "REG-001",
    }])
    result = validate_document(doc_without_proc, plan_data=plan)
    obs_ids = [o["rule_id"] for o in result["observations"]]
    assert "RULE-004" in [f["rule_id"] for f in result["blocking_findings"]]
    assert "OBS-P01" not in obs_ids


# ---------------------------------------------------------------------------
# OBS-P03: multiple frecuencias
# ---------------------------------------------------------------------------

def test_obs_p03_fires_with_multiple_frecuencias():
    plan = _make_plan(frecuencias=["mensual", "trimestral"])
    result = validate_document(_FULL_VALID_DOC, plan_data=plan)
    obs_ids = [o["rule_id"] for o in result["observations"]]
    assert "OBS-P03" in obs_ids


def test_obs_p03_not_fired_with_single_frecuencia():
    plan = _make_plan(frecuencias=["mensual"])
    result = validate_document(_FULL_VALID_DOC, plan_data=plan)
    obs_ids = [o["rule_id"] for o in result["observations"]]
    assert "OBS-P03" not in obs_ids


# ---------------------------------------------------------------------------
# OBS-P04: frecuencia not in PROCEDIMIENTO
# ---------------------------------------------------------------------------

def test_obs_p04_not_fired_when_frecuencia_in_procedimiento():
    # _FULL_VALID_DOC has "mensual" in procedimiento
    result = validate_document(_FULL_VALID_DOC, plan_data=_make_plan(frecuencias=["mensual"]))
    obs_ids = [o["rule_id"] for o in result["observations"]]
    assert "OBS-P04" not in obs_ids


def test_obs_p04_fires_when_frecuencia_missing_from_procedimiento():
    plan = _make_plan(frecuencias=["trimestral"])
    result = validate_document(_FULL_VALID_DOC, plan_data=plan)
    obs_ids = [o["rule_id"] for o in result["observations"]]
    assert "OBS-P04" in obs_ids


# ---------------------------------------------------------------------------
# Full valid doc + valid plan → valid=True
# ---------------------------------------------------------------------------

def test_full_valid_doc_with_valid_plan_passes():
    result = validate_document(_FULL_VALID_DOC, plan_data=_make_plan())
    assert result["valid"] is True
    assert result["blocking_findings"] == []


# ---------------------------------------------------------------------------
# Backward compatibility: no plan_data (Sprint 2A mode)
# ---------------------------------------------------------------------------

def test_validate_document_without_plan_data_still_works():
    """validate_document with no plan_data should behave as Sprint 2A."""
    result = validate_document(_FULL_VALID_DOC)
    assert "valid" in result
    assert "blocking_findings" in result
    assert "observations" in result
    # OBS-P02 should appear (no plan loaded)
    assert any(o["rule_id"] == "OBS-P02" for o in result["observations"])
