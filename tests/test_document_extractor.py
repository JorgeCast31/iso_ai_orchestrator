"""
Unit tests for src/document_extractor.py
No API calls — 100% offline.
"""
import pytest
from src.document_extractor import extract_document_structure, REQUIRED_SECTIONS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FULL_STANDARD_DOC = """\
# PROCEDIMIENTO OPERATIVO ESTÁNDAR

## MANTENIMIENTO PREVENTIVO DE EQUIPOS DE LABORATORIO

**Código:** POE-MTO-001

---

## 1. OBJETIVO

Establecer la metodología para la ejecución del mantenimiento preventivo.

---

## 2. ALCANCE

Aplica a todos los equipos clasificados como laboratorio.

---

## 3. RESPONSABILIDADES

### 3.1 Técnico de Mantenimiento
Ejecutar las actividades de mantenimiento.

### 3.2 Supervisor de Mantenimiento
Revisar y aprobar los registros.

---

## 4. DEFINICIONES

**Mantenimiento preventivo:** Actividades programadas.

---

## 5. PROCEDIMIENTO

### 5.1 Frecuencia de ejecución
Mensual según cronograma.

### 5.2 Materiales necesarios
- Herramientas calibradas
- EPP correspondiente

### 5.5 Acciones ante desviaciones

Documentar inmediatamente cualquier hallazgo.
Clasificar según severidad: crítica, mayor, menor.

---

## 6. REGISTROS

FOR-MTO-001: Registro de mantenimiento preventivo.
"""

ALT_HEADINGS_DOC = """\
# Objetivo del Procedimiento

Texto del objetivo del procedimiento.

# Alcance y Aplicación

Texto del alcance.

# Roles y Responsabilidades

El Técnico de Mantenimiento ejecuta las actividades.
El Supervisor revisa y aprueba.

# Procedimiento Detallado

Pasos detallados del procedimiento.

# Acciones ante Desviaciones

Documentar y clasificar hallazgos.

# Registros Asociados

Formularios requeridos para el registro.
"""

DOC_WITH_VALIDAR = """\
## 1. OBJETIVO

Establecer el procedimiento de mantenimiento.

## 2. ALCANCE

Aplica a todos los equipos.

## 3. RESPONSABILIDADES

El responsable técnico es [VALIDAR] según asignación de área.

## 4. DEFINICIONES

Términos aplicables.

## 5. PROCEDIMIENTO

Ejecutar inspección visual completa.

### 5.5 Acciones ante desviaciones

Documentar y escalar según protocolo.

## 6. REGISTROS

FOR-001 [VALIDAR] pendiente de asignación de código.

## 7. REFERENCIAS

Ver normativa aplicable [VALIDAR] pendiente de revisión.
"""

DOC_NO_GESTION_DESVIACIONES = """\
## 1. OBJETIVO

Establecer el procedimiento.

## 2. ALCANCE

Aplica a todos los equipos.

## 3. RESPONSABILIDADES

El Técnico ejecuta.

## 5. PROCEDIMIENTO

Realizar las actividades de mantenimiento preventivo.

## 6. REGISTROS

FOR-MTO-001.
"""


# ---------------------------------------------------------------------------
# Test: extraction of standard document
# ---------------------------------------------------------------------------

def test_full_doc_extracts_all_required_sections():
    result = extract_document_structure(FULL_STANDARD_DOC)
    sections = result["sections"]
    for key in REQUIRED_SECTIONS:
        assert key in sections, f"Sección requerida '{key}' no detectada"
        assert sections[key].strip(), f"Sección '{key}' detectada pero vacía"


def test_full_doc_objective_content():
    result = extract_document_structure(FULL_STANDARD_DOC)
    assert "metodología" in result["sections"]["objetivo"].lower() or \
           "mantenimiento" in result["sections"]["objetivo"].lower()


def test_full_doc_responsabilidades_includes_subsections():
    result = extract_document_structure(FULL_STANDARD_DOC)
    # Sub-headings 3.1 and 3.2 should be absorbed into responsabilidades
    content = result["sections"]["responsabilidades"]
    assert "Técnico de Mantenimiento" in content or "Supervisor" in content


def test_full_doc_procedimiento_does_not_include_desviaciones_content():
    result = extract_document_structure(FULL_STANDARD_DOC)
    # 5.5 Acciones ante desviaciones is a separate canonical section; its
    # content must NOT bleed into procedimiento.
    proc = result["sections"].get("procedimiento", "")
    desv = result["sections"].get("gestion_desviaciones", "")
    # Desviaciones heading/content must appear in gestion_desviaciones
    assert "Documentar inmediatamente" in desv
    # And NOT be duplicated in procedimiento
    assert "Documentar inmediatamente" not in proc


def test_subsection_desviaciones_captured_as_canonical():
    """### 5.5 Acciones ante desviaciones (level-3) must map to gestion_desviaciones."""
    result = extract_document_structure(FULL_STANDARD_DOC)
    assert "gestion_desviaciones" in result["sections"]
    assert result["sections"]["gestion_desviaciones"].strip()


def test_sections_found_is_sorted():
    result = extract_document_structure(FULL_STANDARD_DOC)
    assert result["sections_found"] == sorted(result["sections_found"])


def test_sections_found_matches_sections_keys():
    result = extract_document_structure(FULL_STANDARD_DOC)
    assert set(result["sections_found"]) == set(result["sections"].keys())


def test_raw_sections_is_alias_for_sections():
    result = extract_document_structure(FULL_STANDARD_DOC)
    assert result["raw_sections"] is result["sections"]


def test_extracted_at_present():
    result = extract_document_structure(FULL_STANDARD_DOC)
    assert "extracted_at" in result
    assert result["extracted_at"]


# ---------------------------------------------------------------------------
# Test: alternative headings (no numbering)
# ---------------------------------------------------------------------------

def test_alt_headings_extracts_required_sections():
    result = extract_document_structure(ALT_HEADINGS_DOC)
    sections = result["sections"]
    for key in REQUIRED_SECTIONS:
        assert key in sections, f"Alt heading: sección '{key}' no detectada"
        assert sections[key].strip(), f"Alt heading: sección '{key}' vacía"


def test_alt_headings_roles_maps_to_responsabilidades():
    result = extract_document_structure(ALT_HEADINGS_DOC)
    assert "responsabilidades" in result["sections"]


def test_alt_headings_acciones_ante_desviaciones_maps_to_gestion():
    result = extract_document_structure(ALT_HEADINGS_DOC)
    assert "gestion_desviaciones" in result["sections"]


# ---------------------------------------------------------------------------
# Test: [VALIDAR] markers
# ---------------------------------------------------------------------------

def test_validar_in_responsabilidades_detected():
    result = extract_document_structure(DOC_WITH_VALIDAR)
    sections_with_validar = [v["section"] for v in result["validar_pendientes"]]
    assert "responsabilidades" in sections_with_validar


def test_validar_in_registros_detected():
    result = extract_document_structure(DOC_WITH_VALIDAR)
    sections_with_validar = [v["section"] for v in result["validar_pendientes"]]
    assert "registros" in sections_with_validar


def test_validar_in_referencias_detected():
    result = extract_document_structure(DOC_WITH_VALIDAR)
    sections_with_validar = [v["section"] for v in result["validar_pendientes"]]
    assert "referencias" in sections_with_validar


def test_validar_evidence_contains_context():
    result = extract_document_structure(DOC_WITH_VALIDAR)
    for marker in result["validar_pendientes"]:
        assert "[VALIDAR]" in marker["evidence"] or "VALIDAR" in marker["evidence"].upper()
        assert marker["section"]


def test_no_validar_in_clean_doc():
    result = extract_document_structure(FULL_STANDARD_DOC)
    assert result["validar_pendientes"] == []


# ---------------------------------------------------------------------------
# Test: empty and unrecognized documents
# ---------------------------------------------------------------------------

def test_empty_string_returns_empty_sections():
    result = extract_document_structure("")
    assert result["sections"] == {}
    assert result["validar_pendientes"] == []
    assert result["sections_found"] == []


def test_plain_text_no_headings_returns_empty():
    plain = "Este es un documento sin secciones marcadas con headings.\nSolo texto plano."
    result = extract_document_structure(plain)
    assert result["sections"] == {}


def test_doc_missing_gestion_desviaciones():
    result = extract_document_structure(DOC_NO_GESTION_DESVIACIONES)
    assert "gestion_desviaciones" not in result["sections"]


# ---------------------------------------------------------------------------
# Test: return dict keys contract
# ---------------------------------------------------------------------------

def test_return_keys_always_present():
    result = extract_document_structure("")
    expected = {"sections", "raw_sections", "validar_pendientes", "sections_found", "extracted_at"}
    assert expected.issubset(set(result.keys()))
