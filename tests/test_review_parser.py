"""
Unit tests for src/review_parser.py
No API calls — 100% offline.
"""
import pytest
from src.review_parser import parse_review, ReviewParseError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_review(
    status="FAIL",
    score=75,
    mayor=2,
    medium=1,
    minor=3,
):
    return (
        f"STATUS: {status}\n"
        f"SCORE: {score}\n"
        f"MAYOR_FINDINGS: {mayor}\n"
        f"MEDIUM_FINDINGS: {medium}\n"
        f"MINOR_FINDINGS: {minor}\n"
    )


# ---------------------------------------------------------------------------
# Nominal cases
# ---------------------------------------------------------------------------

def test_nominal_fail():
    result = parse_review(_make_review(status="FAIL", score=70, mayor=3))
    assert result["status"] == "FAIL"
    assert result["score"] == 70
    assert result["major_findings"] == 3


def test_nominal_pass():
    result = parse_review(_make_review(status="PASS", score=95, mayor=0))
    assert result["status"] == "PASS"
    assert result["score"] == 95
    assert result["major_findings"] == 0


def test_all_fields_present():
    result = parse_review(_make_review(score=80, mayor=2, medium=1, minor=4))
    assert result["medium_findings"] == 1
    assert result["minor_findings"] == 4


# ---------------------------------------------------------------------------
# Markdown / formatting tolerance
# ---------------------------------------------------------------------------

def test_markdown_bold_fields():
    text = (
        "**STATUS: PASS**\n"
        "**SCORE: 92**\n"
        "**MAYOR_FINDINGS: 0**\n"
        "**MEDIUM_FINDINGS: 1**\n"
        "**MINOR_FINDINGS: 2**\n"
    )
    result = parse_review(text)
    assert result["status"] == "PASS"
    assert result["score"] == 92
    assert result["major_findings"] == 0


def test_extra_spaces_around_colon():
    text = (
        "STATUS :  FAIL\n"
        "SCORE  :  55\n"
        "MAYOR_FINDINGS  :  4\n"
        "MEDIUM_FINDINGS :  2\n"
        "MINOR_FINDINGS :  1\n"
    )
    result = parse_review(text)
    assert result["score"] == 55
    assert result["major_findings"] == 4


def test_case_insensitive_status():
    text = "status: pass\nscore: 90\nmayor_findings: 0\n"
    result = parse_review(text)
    assert result["status"] == "PASS"


def test_status_present_but_lowercase_fail():
    text = "status: fail\nSCORE: 40\nMAYOR_FINDINGS: 5\n"
    result = parse_review(text)
    assert result["status"] == "FAIL"
    assert result["score"] == 40


# ---------------------------------------------------------------------------
# Non-critical fields may default to zero (MEDIUM, MINOR)
# ---------------------------------------------------------------------------

def test_missing_minor_findings_defaults_to_zero():
    text = "STATUS: FAIL\nSCORE: 60\nMAYOR_FINDINGS: 2\nMEDIUM_FINDINGS: 1\n"
    result = parse_review(text)
    assert result["minor_findings"] == 0


def test_missing_medium_and_minor_defaults_to_zero():
    text = "STATUS: FAIL\nSCORE: 60\nMAYOR_FINDINGS: 2\n"
    result = parse_review(text)
    assert result["medium_findings"] == 0
    assert result["minor_findings"] == 0


# ---------------------------------------------------------------------------
# Critical field validation — missing any one must raise ReviewParseError
# These tests document the exact scenarios that previously could produce
# a false NO_MAJOR_FINDINGS stop via silent default of major_findings=0.
# ---------------------------------------------------------------------------

def test_missing_status_raises():
    """STATUS is a critical field — its absence must raise, not default to FAIL."""
    text = "SCORE: 65\nMAYOR_FINDINGS: 3\nMEDIUM_FINDINGS: 0\nMINOR_FINDINGS: 1\n"
    with pytest.raises(ReviewParseError, match="STATUS"):
        parse_review(text)


def test_status_present_score_absent_raises():
    """STATUS found + MAYOR found but SCORE absent → invalid review."""
    text = "STATUS: FAIL\nMAYOR_FINDINGS: 3\nMEDIUM_FINDINGS: 1\nMINOR_FINDINGS: 0\n"
    with pytest.raises(ReviewParseError, match="SCORE"):
        parse_review(text)


def test_status_present_mayor_absent_raises():
    """
    STATUS found + SCORE found but MAYOR_FINDINGS absent → invalid review.
    This is the primary false-positive scenario: without this check,
    major_findings would default to 0 and trigger NO_MAJOR_FINDINGS stop.
    """
    text = "STATUS: FAIL\nSCORE: 65\nMEDIUM_FINDINGS: 2\nMINOR_FINDINGS: 1\n"
    with pytest.raises(ReviewParseError, match="MAYOR_FINDINGS"):
        parse_review(text)


def test_score_present_status_and_mayor_absent_raises():
    """SCORE found but STATUS and MAYOR_FINDINGS absent → invalid review."""
    text = "SCORE: 70\nMEDIUM_FINDINGS: 2\nMINOR_FINDINGS: 1\n"
    with pytest.raises(ReviewParseError) as exc_info:
        parse_review(text)
    # Both missing fields must be mentioned
    assert "STATUS" in str(exc_info.value)
    assert "MAYOR_FINDINGS" in str(exc_info.value)


def test_partial_parse_that_previously_triggered_false_stop():
    """
    Regression test: GPT returns a partial response with STATUS and SCORE
    but MAYOR_FINDINGS is cut off or missing.  Before the fix, this would
    silently set major_findings=0 and trigger NO_MAJOR_FINDINGS → STOP.
    Now it must raise.
    """
    text = (
        "STATUS: FAIL\n"
        "SCORE: 72\n"
        "MEDIUM_FINDINGS: 2\n"
        "MINOR_FINDINGS: 3\n"
        "MAJOR_ISSUES:\n"
        "- Some unstructured text that does not contain the MAYOR_FINDINGS field\n"
    )
    with pytest.raises(ReviewParseError, match="MAYOR_FINDINGS"):
        parse_review(text)


# ---------------------------------------------------------------------------
# Parse failure — completely unrecognized format
# ---------------------------------------------------------------------------

def test_empty_string_raises():
    with pytest.raises(ReviewParseError):
        parse_review("")


def test_unrelated_text_raises():
    with pytest.raises(ReviewParseError):
        parse_review("Lo siento, no puedo procesar ese documento ahora mismo.")


def test_partial_unrecognized_format_raises():
    # Has some text but none of the critical field names
    with pytest.raises(ReviewParseError):
        parse_review("El documento presenta algunas deficiencias menores.\nRecomendaciones: revisar sección 3.")


def test_error_message_contains_missing_field_names():
    # Error message must name the missing critical fields
    text = "Respuesta inesperada del modelo sin campos estructurados."
    with pytest.raises(ReviewParseError) as exc_info:
        parse_review(text)
    msg = str(exc_info.value)
    assert "STATUS" in msg
    assert "SCORE" in msg
    assert "MAYOR_FINDINGS" in msg


# ---------------------------------------------------------------------------
# Return contract — dict keys always present
# ---------------------------------------------------------------------------

def test_return_keys():
    result = parse_review(_make_review())
    expected_keys = {"status", "score", "major_findings", "medium_findings", "minor_findings"}
    assert set(result.keys()) == expected_keys
