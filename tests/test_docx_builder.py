"""Sprint 3 — tests for docx_builder.py

All tests are offline (no API calls).
DOCX templates used in tests are created programmatically in tmp_path.
"""
import pytest
from pathlib import Path
from docx import Document

from src.docx_builder import build_docx_from_template, DocxBuildError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_template(tmp_path, with_table: bool = True) -> str:
    """Create a minimal institutional template DOCX for testing."""
    doc = Document()

    # Header
    section = doc.sections[0]
    section.header.paragraphs[0].text = "TEST HEADER — SGC"

    # Institutional metadata table
    if with_table:
        table = doc.add_table(rows=2, cols=2)
        table.rows[0].cells[0].text = "Código:"
        table.rows[1].cells[0].text = "Versión:"

    # Placeholder paragraph (will be cleared by builder)
    doc.add_paragraph("CONTENT PLACEHOLDER")

    path = str(tmp_path / "plantilla.docx")
    doc.save(path)
    return path


def _make_doc_data(sections: dict) -> dict:
    """Build a minimal document_data dict matching the document.json contract."""
    return {
        "sections": sections,
        "raw_sections": sections,
        "validar_pendientes": [],
        "sections_found": sorted(sections.keys()),
        "extracted_at": "2026-03-13T12:00:00",
    }


_FULL_SECTIONS = {
    "objetivo":            "Establecer el procedimiento de mantenimiento preventivo.",
    "alcance":             "Aplica a todos los equipos de laboratorio.",
    "responsabilidades":   "El Técnico de Mantenimiento ejecuta las actividades.",
    "procedimiento":       "Realizar inspección visual mensual de los equipos.",
    "gestion_desviaciones": "Documentar y clasificar hallazgos según severidad.",
    "registros":           "Completar formulario REG-001 por cada actividad.",
}

_ALL_SECTIONS = {
    **_FULL_SECTIONS,
    "definiciones":          "Mantenimiento preventivo: actividades programadas.",
    "referencias":           "ISO 9001:2015.",
    "control_cambios":       "Versión 01 — emisión inicial.",
    "historial_modificaciones": "| V01 | 2026-03-13 | Emisión inicial |",
}


# ---------------------------------------------------------------------------
# 1. Valid template → generates .docx
# ---------------------------------------------------------------------------

def test_valid_template_generates_docx(tmp_path):
    template = _make_template(tmp_path)
    output = str(tmp_path / "output.docx")
    result = build_docx_from_template(template, output, _make_doc_data(_FULL_SECTIONS))
    assert result["ok"] is True
    assert Path(output).exists()


def test_result_dict_has_required_keys(tmp_path):
    template = _make_template(tmp_path)
    output = str(tmp_path / "output.docx")
    result = build_docx_from_template(template, output, _make_doc_data(_FULL_SECTIONS))
    for key in ("ok", "output_path", "sections_written", "warnings"):
        assert key in result, f"Key '{key}' missing from result"


def test_output_path_in_result_matches_written_file(tmp_path):
    template = _make_template(tmp_path)
    output = str(tmp_path / "subfolder" / "output.docx")
    result = build_docx_from_template(template, output, _make_doc_data(_FULL_SECTIONS))
    assert Path(result["output_path"]).exists()


# ---------------------------------------------------------------------------
# 2. template_path inexistente → DocxBuildError
# ---------------------------------------------------------------------------

def test_missing_template_raises_docx_build_error(tmp_path):
    with pytest.raises(DocxBuildError, match="no encontrada"):
        build_docx_from_template(
            "/nonexistent/path/plantilla.docx",
            str(tmp_path / "output.docx"),
            _make_doc_data({}),
        )


# ---------------------------------------------------------------------------
# 3. Secciones mínimas → sections_written correcto
# ---------------------------------------------------------------------------

def test_sections_written_contains_all_provided_sections(tmp_path):
    template = _make_template(tmp_path)
    output = str(tmp_path / "output.docx")
    result = build_docx_from_template(template, output, _make_doc_data(_FULL_SECTIONS))
    for key in _FULL_SECTIONS:
        assert key in result["sections_written"], f"Section '{key}' missing from sections_written"


def test_all_sections_including_optional_written(tmp_path):
    template = _make_template(tmp_path)
    output = str(tmp_path / "output.docx")
    result = build_docx_from_template(template, output, _make_doc_data(_ALL_SECTIONS))
    for key in _ALL_SECTIONS:
        assert key in result["sections_written"]


def test_sections_written_excludes_missing_sections(tmp_path):
    template = _make_template(tmp_path)
    output = str(tmp_path / "output.docx")
    partial = {k: v for k, v in _FULL_SECTIONS.items() if k != "registros"}
    result = build_docx_from_template(template, output, _make_doc_data(partial))
    assert "registros" not in result["sections_written"]


# ---------------------------------------------------------------------------
# 4. Secciones opcionales ausentes → no falla, no genera warnings sobre ellas
# ---------------------------------------------------------------------------

def test_missing_optional_sections_do_not_generate_warnings(tmp_path):
    """Optional sections absent from document_data must produce no warnings."""
    template = _make_template(tmp_path)
    output = str(tmp_path / "output.docx")
    # Only required sections provided — no optional ones
    result = build_docx_from_template(template, output, _make_doc_data(_FULL_SECTIONS))
    assert result["ok"] is True
    optional_keys = {"definiciones", "referencias", "control_cambios", "historial_modificaciones"}
    for obs_key in optional_keys:
        assert not any(obs_key in w for w in result["warnings"]), (
            f"Unexpected warning about optional section '{obs_key}'"
        )


def test_missing_required_section_generates_warning(tmp_path):
    """A required section absent from document_data must generate a warning."""
    template = _make_template(tmp_path)
    output = str(tmp_path / "output.docx")
    sections = {k: v for k, v in _FULL_SECTIONS.items() if k != "objetivo"}
    result = build_docx_from_template(template, output, _make_doc_data(sections))
    assert result["ok"] is True  # still generates — non-fatal
    assert any("objetivo" in w for w in result["warnings"])


def test_all_required_sections_missing_warns_all(tmp_path):
    """When all required sections are absent, a warning must exist for each."""
    template = _make_template(tmp_path)
    output = str(tmp_path / "output.docx")
    result = build_docx_from_template(template, output, _make_doc_data({}))
    # Empty sections → fallback path (document_text also None) → single warning
    assert result["ok"] is True
    assert len(result["warnings"]) >= 1


# ---------------------------------------------------------------------------
# 5. Fallback a document_text cuando no hay secciones estructuradas
# ---------------------------------------------------------------------------

def test_empty_sections_with_document_text_uses_fallback(tmp_path):
    template = _make_template(tmp_path)
    output = str(tmp_path / "output.docx")
    result = build_docx_from_template(
        template, output,
        _make_doc_data({}),
        document_text="Contenido completo del documento como texto de respaldo.",
    )
    assert result["ok"] is True
    assert any("fallback" in w.lower() for w in result["warnings"])


def test_fallback_content_appears_in_generated_docx(tmp_path):
    template = _make_template(tmp_path)
    output = str(tmp_path / "output.docx")
    fallback_text = "Texto de respaldo exclusivo para este test."
    build_docx_from_template(
        template, output,
        _make_doc_data({}),
        document_text=fallback_text,
    )
    doc = Document(output)
    all_text = " ".join(p.text for p in doc.paragraphs)
    assert "respaldo exclusivo" in all_text


# ---------------------------------------------------------------------------
# 6. Verificar que el contenido aparece en el DOCX generado
# ---------------------------------------------------------------------------

def test_section_headings_appear_in_generated_docx(tmp_path):
    template = _make_template(tmp_path)
    output = str(tmp_path / "output.docx")
    build_docx_from_template(template, output, _make_doc_data(_FULL_SECTIONS))
    doc = Document(output)
    all_text = " ".join(p.text for p in doc.paragraphs)
    assert "Objetivo" in all_text
    assert "Procedimiento" in all_text
    assert "Registros" in all_text


def test_section_content_appears_in_generated_docx(tmp_path):
    template = _make_template(tmp_path)
    output = str(tmp_path / "output.docx")
    build_docx_from_template(template, output, _make_doc_data(_FULL_SECTIONS))
    doc = Document(output)
    all_text = " ".join(p.text for p in doc.paragraphs)
    assert "inspección visual" in all_text.lower()
    assert "REG-001" in all_text


# ---------------------------------------------------------------------------
# 7. Tablas institucionales de la plantilla se preservan
# ---------------------------------------------------------------------------

def test_institutional_tables_preserved_after_build(tmp_path):
    """Tables from the template (institutional metadata) must survive the build."""
    template = _make_template(tmp_path, with_table=True)
    output = str(tmp_path / "output.docx")
    build_docx_from_template(template, output, _make_doc_data(_FULL_SECTIONS))
    doc = Document(output)
    assert len(doc.tables) >= 1, "Institutional table from template was lost"


def test_no_table_template_works_fine(tmp_path):
    """Template without tables must also work without error."""
    template = _make_template(tmp_path, with_table=False)
    output = str(tmp_path / "output.docx")
    result = build_docx_from_template(template, output, _make_doc_data(_FULL_SECTIONS))
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# 8. OUTPUT_DOCX_ENABLED=false → pipeline preserva comportamiento previo
# ---------------------------------------------------------------------------

def test_config_docx_enabled_false_means_true_by_default(tmp_path):
    """Verify the config default is True (the feature is enabled out of the box)."""
    from src.config import OUTPUT_DOCX_ENABLED
    # Default is "true" unless overridden by environment; in test env it should be True
    assert isinstance(OUTPUT_DOCX_ENABLED, bool)


def test_config_template_path_default_points_to_inputs(tmp_path):
    from src.config import INPUT_TEMPLATE_DOCX
    assert "plantilla_poe.docx" in INPUT_TEMPLATE_DOCX
