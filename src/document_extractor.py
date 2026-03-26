"""Sprint 2A — document_extractor.py

Minimal, conservative extractor for POE document structure.

Detects canonical sections by scanning heading lines at any level (# through ######).
If a heading matches a known canonical alias, a new section starts.
Unrecognized sub-headings are absorbed as content into the currently active section.

Public API:
    extract_document_structure(document_text: str) -> dict
"""
import re
from datetime import datetime

# ---------------------------------------------------------------------------
# Section aliases — mapping canonical key → list of substrings to look for
# in the normalized (lowercased, number-stripped) heading text.
# Longer aliases are tested first to prefer more specific matches.
# ---------------------------------------------------------------------------
SECTION_ALIASES: dict[str, list[str]] = {
    "objetivo": [
        "objetivo",
        "propósito",
        "proposito",
        "purpose",
    ],
    "alcance": [
        "ámbito de aplicación",
        "ambito de aplicacion",
        "alcance",
        "scope",
        "ámbito",
        "ambito",
    ],
    "responsabilidades": [
        "roles y responsabilidades",
        "responsabilidades",
        "responsibilities",
        "responsabilidad",
    ],
    "definiciones": [
        "términos y definiciones",
        "terminos y definiciones",
        "definiciones",
        "definitions",
        "glosario",
        "abreviaturas",
    ],
    "procedimiento": [
        "desarrollo del procedimiento",
        "procedimientos",
        "procedimiento",
        "procedure",
        "actividades",
        "metodología",
        "metodologia",
    ],
    "gestion_desviaciones": [
        "desviaciones y no conformidades",
        "acciones ante desviaciones",
        "acciones ante no conformidades",
        "gestión de desviaciones",
        "gestion de desviaciones",
        "manejo de desviaciones",
        "manejo de no conformidades",
        "no conformidades",
    ],
    "registros": [
        "formularios y registros",
        "documentación generada",
        "documentacion generada",
        "registros asociados",
        "registros",
        "records",
        "formularios",
    ],
    "referencias": [
        "documentos de referencia",
        "documentos relacionados",
        "normativa aplicable",
        "marco normativo",
        "referencias",
        "references",
        "normativa",
    ],
    "control_cambios": [
        "gestión de cambios",
        "gestion de cambios",
        "control de cambios",
        "change control",
    ],
    "historial_modificaciones": [
        "historial de modificaciones",
        "historial de revisiones",
        "historial de cambios",
        "tabla de versiones",
        "revision history",
        "modificaciones",
        "historial",
    ],
}

# Precomputed flat candidate list, sorted longest-alias-first.
# Built once at import time so _match_section does not re-sort on every call.
_SECTION_CANDIDATES: list[tuple[str, str]] = sorted(
    [
        (canonical, alias)
        for canonical, aliases in SECTION_ALIASES.items()
        for alias in aliases
    ],
    key=lambda x: len(x[1]),
    reverse=True,
)

# Sections required for a valid document — exported for use by the validator.
REQUIRED_SECTIONS = frozenset({
    "objetivo",
    "alcance",
    "responsabilidades",
    "procedimiento",
    "gestion_desviaciones",
    "registros",
})


def _normalize_heading(text: str) -> str:
    """
    Strip leading numeric/alphanumeric prefixes and lowercase.

    Examples:
      "5.5 Acciones ante desviaciones" → "acciones ante desviaciones"
      "1. OBJETIVO"                    → "objetivo"
      "A. Alcance"                     → "alcance"
      "RESPONSABILIDADES"              → "responsabilidades"
    """
    # Strip leading number+separator patterns: "5.5 ", "1. ", "1) ", "A. "
    text = re.sub(r'^[\d]+[\d.]*\s*[.\-)\s]\s*', '', text.strip())
    text = re.sub(r'^[A-Za-z][.\-)\s]\s*', '', text)
    return text.strip().lower()


def _match_section(heading_text: str) -> str | None:
    """
    Return canonical section key if heading_text matches a known alias, else None.

    Two-pass strategy (longer aliases checked first in both passes):

    Pass 1 — alias anchored at the START of the normalized heading.
      Prevents "Objetivo del Procedimiento" from matching "procedimiento"
      (a substring) when the primary word is clearly "objetivo".

    Pass 2 — alias found anywhere (substring fallback for compound headings
      like "Formularios y Registros" where the key word appears mid-string).
    """
    normalized = _normalize_heading(heading_text)
    if not normalized:
        return None

    # Pass 1: alias must appear at the very start of the normalized heading
    for canonical, alias in _SECTION_CANDIDATES:
        if re.match(rf'{re.escape(alias)}(\s|$)', normalized):
            return canonical

    # Pass 2: alias found anywhere (substring fallback)
    for canonical, alias in _SECTION_CANDIDATES:
        if alias in normalized:
            return canonical

    return None


def _find_validar_markers(text: str, section: str) -> list[dict]:
    """Return all [VALIDAR] occurrences in text with surrounding context."""
    findings: list[dict] = []
    for match in re.finditer(r'\[VALIDAR\]', text, re.IGNORECASE):
        start = max(0, match.start() - 50)
        end = min(len(text), match.end() + 50)
        evidence = text[start:end].replace('\n', ' ').strip()
        findings.append({"section": section, "evidence": evidence})
    return findings


def extract_document_structure(document_text: str) -> dict:
    """
    Extract canonical sections from a POE document text.

    Scans every heading line (# to ######). If the heading text matches a
    canonical section alias, a new section starts and prior content is flushed.
    Unrecognized headings are kept as content within the active section.

    Returns:
      {
        "sections":          dict[str, str]  — trimmed content per canonical key,
        "raw_sections":      dict[str, str]  — alias for sections (backward compat),
        "validar_pendientes": list[dict]     — [VALIDAR] markers found,
        "sections_found":    list[str]       — sorted canonical keys detected,
        "extracted_at":      str             — ISO timestamp,
      }
    """
    lines = document_text.split('\n')
    sections: dict[str, str] = {}
    current_canonical: str | None = None
    current_lines: list[str] = []

    def _flush() -> None:
        """Save accumulated lines into sections under current_canonical."""
        nonlocal current_lines
        if current_canonical is not None and current_lines:
            content = '\n'.join(current_lines).strip()
            if content:
                existing = sections.get(current_canonical, '')
                sections[current_canonical] = (
                    (existing + '\n' + content).strip() if existing else content
                )
        current_lines = []

    for line in lines:
        heading_match = re.match(r'^(#{1,6})\s+(.+)', line)
        if heading_match:
            heading_text = heading_match.group(2).strip()
            canonical = _match_section(heading_text)
            if canonical:
                _flush()
                current_canonical = canonical
                # The heading line itself is NOT included in the section content.
            else:
                # Unrecognized heading — treat as body content of current section.
                if current_canonical is not None:
                    current_lines.append(line)
        else:
            if current_canonical is not None:
                current_lines.append(line)

    _flush()

    # Collect [VALIDAR] markers from all extracted section bodies.
    validar_pendientes: list[dict] = []
    for canonical, content in sections.items():
        validar_pendientes.extend(_find_validar_markers(content, canonical))

    return {
        "sections": sections,
        "raw_sections": sections,          # backward-compat alias — same object as sections
        "validar_pendientes": validar_pendientes,
        "sections_found": sorted(sections.keys()),
        "extracted_at": datetime.now().isoformat(),
    }
