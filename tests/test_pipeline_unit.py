"""
Unit tests for Pipeline internal helpers — no API calls, 100% offline.

Covers:
  - Pipeline._build_rewrite_input: the static method responsible for
    injecting validator blocking findings into Claude's rewrite input.
    This is the critical output of the Sprint 2A dual-gate when a GPT
    PASS is rejected by the structural validator.
  - Pipeline._build_metadata: shape, defaults, and completeness across
    Sprint 1/2A/2B/3 fields; error-path fields; final_status override.
"""
from unittest.mock import patch
from src.pipeline import Pipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rejection(blocking_findings: list) -> dict:
    return {
        "valid": False,
        "blocking_findings": blocking_findings,
        "observations": [],
        "validar_count": 0,
    }


def _finding(rule_id: str, section: str, message: str, evidence: str = "") -> dict:
    return {
        "rule_id": rule_id,
        "section": section,
        "message": message,
        "evidence": evidence,
    }


BASE_PROMPT = "REWRITE PROMPT"
BASE_DOC = "Texto del documento actual."
BASE_REVIEW = "STATUS: FAIL\nSCORE: 65\nMAYOR_FINDINGS: 2"

EXPECTED_BASE = (
    f"{BASE_PROMPT}\n\n"
    f"=== DOCUMENTO ORIGINAL ===\n{BASE_DOC}\n\n"
    f"=== AUDITORÍA ===\n{BASE_REVIEW}"
)


# ---------------------------------------------------------------------------
# No validator rejection → output identical to Sprint 1 format
# ---------------------------------------------------------------------------

def test_no_rejection_returns_base_format():
    result = Pipeline._build_rewrite_input(BASE_PROMPT, BASE_DOC, BASE_REVIEW, None)
    assert result == EXPECTED_BASE


def test_no_rejection_no_structural_section():
    result = Pipeline._build_rewrite_input(BASE_PROMPT, BASE_DOC, BASE_REVIEW, None)
    assert "VALIDACIÓN ESTRUCTURAL" not in result


def test_empty_rejection_dict_returns_base():
    """validator_rejection with empty blocking_findings → no injection."""
    result = Pipeline._build_rewrite_input(
        BASE_PROMPT, BASE_DOC, BASE_REVIEW, _rejection([])
    )
    assert result == EXPECTED_BASE
    assert "VALIDACIÓN ESTRUCTURAL" not in result


# ---------------------------------------------------------------------------
# With validator rejection → structural section injected
# ---------------------------------------------------------------------------

def test_rejection_adds_structural_section():
    rejection = _rejection([_finding("RULE-001", "objetivo", "Sección OBJETIVO ausente o vacía")])
    result = Pipeline._build_rewrite_input(BASE_PROMPT, BASE_DOC, BASE_REVIEW, rejection)
    assert "=== VALIDACIÓN ESTRUCTURAL ===" in result


def test_rejection_preserves_base_content():
    """Base sections must still be present when validator section is added."""
    rejection = _rejection([_finding("RULE-001", "objetivo", "Sección OBJETIVO ausente o vacía")])
    result = Pipeline._build_rewrite_input(BASE_PROMPT, BASE_DOC, BASE_REVIEW, rejection)
    assert BASE_PROMPT in result
    assert "=== DOCUMENTO ORIGINAL ===" in result
    assert BASE_DOC in result
    assert "=== AUDITORÍA ===" in result
    assert BASE_REVIEW in result


def test_rejection_contains_rule_id():
    rejection = _rejection([_finding("RULE-004", "procedimiento", "Sección PROCEDIMIENTO ausente o vacía")])
    result = Pipeline._build_rewrite_input(BASE_PROMPT, BASE_DOC, BASE_REVIEW, rejection)
    assert "RULE-004" in result


def test_rejection_contains_section_name_uppercased():
    rejection = _rejection([_finding("RULE-003", "responsabilidades", "Sección RESPONSABILIDADES ausente o vacía")])
    result = Pipeline._build_rewrite_input(BASE_PROMPT, BASE_DOC, BASE_REVIEW, rejection)
    assert "RESPONSABILIDADES" in result


def test_rejection_with_evidence_includes_evidence():
    rejection = _rejection([
        _finding("RULE-007", "responsabilidades", "[VALIDAR] pendiente", "el responsable es [VALIDAR]")
    ])
    result = Pipeline._build_rewrite_input(BASE_PROMPT, BASE_DOC, BASE_REVIEW, rejection)
    assert "el responsable es [VALIDAR]" in result


def test_rejection_without_evidence_no_evidencia_line():
    rejection = _rejection([_finding("RULE-001", "objetivo", "Sección OBJETIVO ausente o vacía", "")])
    result = Pipeline._build_rewrite_input(BASE_PROMPT, BASE_DOC, BASE_REVIEW, rejection)
    # Empty evidence → no "Evidencia:" line for that finding
    assert "Evidencia:" not in result


def test_multiple_findings_all_present():
    rejection = _rejection([
        _finding("RULE-001", "objetivo", "OBJETIVO ausente"),
        _finding("RULE-004", "procedimiento", "PROCEDIMIENTO ausente"),
        _finding("RULE-007", "responsabilidades", "[VALIDAR] en responsabilidades", "ctx [VALIDAR]"),
    ])
    result = Pipeline._build_rewrite_input(BASE_PROMPT, BASE_DOC, BASE_REVIEW, rejection)
    assert "RULE-001" in result
    assert "RULE-004" in result
    assert "RULE-007" in result
    assert "ctx [VALIDAR]" in result


def test_finding_count_message():
    """The injected section must state how many blocking findings were found."""
    rejection = _rejection([
        _finding("RULE-001", "objetivo", "OBJETIVO ausente"),
        _finding("RULE-002", "alcance", "ALCANCE ausente"),
    ])
    result = Pipeline._build_rewrite_input(BASE_PROMPT, BASE_DOC, BASE_REVIEW, rejection)
    assert "2" in result  # Count of findings mentioned


def test_structural_section_appears_after_audit_section():
    """=== VALIDACIÓN ESTRUCTURAL === must come after === AUDITORÍA ===."""
    rejection = _rejection([_finding("RULE-001", "objetivo", "OBJETIVO ausente")])
    result = Pipeline._build_rewrite_input(BASE_PROMPT, BASE_DOC, BASE_REVIEW, rejection)
    pos_auditoria = result.index("=== AUDITORÍA ===")
    pos_validacion = result.index("=== VALIDACIÓN ESTRUCTURAL ===")
    assert pos_validacion > pos_auditoria


# ---------------------------------------------------------------------------
# _build_metadata — shape and completeness
# ---------------------------------------------------------------------------

def _make_pipeline() -> Pipeline:
    """Instantiate Pipeline without real API clients."""
    with patch("src.pipeline.ClaudeClient"), patch("src.pipeline.GPTClient"):
        return Pipeline()


_BASE_REVIEW = {
    "status": "PASS",
    "score": 95,
    "major_findings": 0,
    "medium_findings": 1,
    "minor_findings": 2,
}

_ALL_METADATA_KEYS = {
    # Original contract fields
    "claude_model", "openai_model", "max_iterations", "iterations_completed",
    "final_reason", "final_status", "final_score", "final_major_findings",
    # Sprint 1
    "run_timestamp", "reviews_completed", "drafts_generated", "iteration_history",
    # Sprint 2A
    "validator_runs", "last_validator_status",
    "last_validator_blocking_findings_count", "last_validator_observation_count",
    "last_pass_rejected_by_validator", "validator_history",
    # Sprint 2B
    "plan_loaded", "plan_source", "plan_activities_count", "require_plan_xlsx",
    # Sprint 3
    "docx_enabled", "docx_generated", "docx_output_path", "docx_template_path",
    "docx_warnings", "docx_error_message",
}


def test_metadata_contains_all_required_keys():
    meta = _make_pipeline()._build_metadata(
        run_timestamp="2026-03-13T12:00:00",
        iterations_completed=2,
        stop_reason="PASS_VALIDATED",
        review_data=_BASE_REVIEW,
        iteration_history=[],
    )
    for key in _ALL_METADATA_KEYS:
        assert key in meta, f"Required metadata key '{key}' is missing"


def test_metadata_sprint2a_defaults():
    meta = _make_pipeline()._build_metadata(
        run_timestamp="2026-03-13T12:00:00",
        iterations_completed=1,
        stop_reason="PASS_VALIDATED",
        review_data=_BASE_REVIEW,
        iteration_history=[],
    )
    assert meta["validator_runs"] == 0
    assert meta["last_validator_status"] == "NOT_RUN"
    assert meta["last_validator_blocking_findings_count"] == 0
    assert meta["last_validator_observation_count"] == 0
    assert meta["last_pass_rejected_by_validator"] is False
    assert meta["validator_history"] == []


def test_metadata_sprint2b_defaults():
    meta = _make_pipeline()._build_metadata(
        run_timestamp="2026-03-13T12:00:00",
        iterations_completed=1,
        stop_reason="PASS_VALIDATED",
        review_data=_BASE_REVIEW,
        iteration_history=[],
    )
    assert meta["plan_loaded"] is False
    assert meta["plan_source"] == ""
    assert meta["plan_activities_count"] == 0
    assert meta["require_plan_xlsx"] is False


def test_metadata_sprint3_defaults():
    meta = _make_pipeline()._build_metadata(
        run_timestamp="2026-03-13T12:00:00",
        iterations_completed=1,
        stop_reason="PASS_VALIDATED",
        review_data=_BASE_REVIEW,
        iteration_history=[],
    )
    assert meta["docx_enabled"] is False
    assert meta["docx_generated"] is False
    assert meta["docx_output_path"] == ""
    assert meta["docx_template_path"] == ""
    assert meta["docx_warnings"] == []
    assert meta["docx_error_message"] is None


def test_metadata_final_status_uses_review_data_when_no_override():
    meta = _make_pipeline()._build_metadata(
        run_timestamp="2026-03-13T12:00:00",
        iterations_completed=2,
        stop_reason="PASS_VALIDATED",
        review_data=_BASE_REVIEW,
        iteration_history=[],
    )
    assert meta["final_status"] == "PASS"


def test_metadata_final_status_override_takes_precedence():
    meta = _make_pipeline()._build_metadata(
        run_timestamp="2026-03-13T12:00:00",
        iterations_completed=1,
        stop_reason="PIPELINE_ERROR",
        review_data=_BASE_REVIEW,
        iteration_history=[],
        final_status="ERROR",
    )
    assert meta["final_status"] == "ERROR"


def test_metadata_error_fields_absent_by_default():
    meta = _make_pipeline()._build_metadata(
        run_timestamp="2026-03-13T12:00:00",
        iterations_completed=2,
        stop_reason="PASS_VALIDATED",
        review_data=_BASE_REVIEW,
        iteration_history=[],
    )
    assert "error_message" not in meta
    assert "error_iteration" not in meta
    assert "error_stage" not in meta


def test_metadata_error_fields_present_when_provided():
    meta = _make_pipeline()._build_metadata(
        run_timestamp="2026-03-13T12:00:00",
        iterations_completed=1,
        stop_reason="PIPELINE_ERROR",
        review_data={"status": "FAIL", "score": 0, "major_findings": 0},
        iteration_history=[],
        final_status="ERROR",
        error_message="Algo salió mal",
        error_iteration=1,
        error_stage="review_v1",
    )
    assert meta["error_message"] == "Algo salió mal"
    assert meta["error_iteration"] == 1
    assert meta["error_stage"] == "review_v1"


def test_metadata_validator_history_none_becomes_empty_list():
    meta = _make_pipeline()._build_metadata(
        run_timestamp="2026-03-13T12:00:00",
        iterations_completed=1,
        stop_reason="PASS_VALIDATED",
        review_data=_BASE_REVIEW,
        iteration_history=[],
        validator_history=None,
    )
    assert meta["validator_history"] == []


def test_metadata_docx_warnings_none_becomes_empty_list():
    meta = _make_pipeline()._build_metadata(
        run_timestamp="2026-03-13T12:00:00",
        iterations_completed=1,
        stop_reason="PASS_VALIDATED",
        review_data=_BASE_REVIEW,
        iteration_history=[],
        docx_warnings=None,
    )
    assert meta["docx_warnings"] == []


def test_metadata_reviews_and_drafts_equal_iterations_completed():
    meta = _make_pipeline()._build_metadata(
        run_timestamp="2026-03-13T12:00:00",
        iterations_completed=3,
        stop_reason="MAX_ITERATIONS_REACHED",
        review_data={"status": "FAIL", "score": 60, "major_findings": 2},
        iteration_history=[],
    )
    assert meta["reviews_completed"] == 3
    assert meta["drafts_generated"] == 3
