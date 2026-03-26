"""
Unit tests for src/decision.py
No API calls — 100% offline.
"""
from src.decision import should_stop


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _data(status="FAIL", score=50, major=3, medium=1, minor=2):
    return {
        "status": status,
        "score": score,
        "major_findings": major,
        "medium_findings": medium,
        "minor_findings": minor,
    }


# ---------------------------------------------------------------------------
# PASS condition
# ---------------------------------------------------------------------------

def test_pass_status_stops():
    stop, reason = should_stop(_data(status="PASS"), iteration=1, max_iterations=4)
    assert stop is True
    assert reason == "PASS"


def test_pass_takes_priority_over_score():
    # PASS + score >= threshold: PASS should win
    stop, reason = should_stop(
        _data(status="PASS", score=95), iteration=1, max_iterations=4, score_threshold=90
    )
    assert reason == "PASS"


def test_pass_takes_priority_over_max_iterations():
    stop, reason = should_stop(_data(status="PASS"), iteration=4, max_iterations=4)
    assert reason == "PASS"


# ---------------------------------------------------------------------------
# SCORE_THRESHOLD condition
# ---------------------------------------------------------------------------

def test_score_at_threshold_stops():
    stop, reason = should_stop(
        _data(score=90), iteration=1, max_iterations=4, score_threshold=90
    )
    assert stop is True
    assert reason == "SCORE_THRESHOLD"


def test_score_above_threshold_stops():
    stop, reason = should_stop(
        _data(score=97), iteration=2, max_iterations=4, score_threshold=90
    )
    assert stop is True
    assert reason == "SCORE_THRESHOLD"


def test_score_below_threshold_continues():
    stop, _ = should_stop(
        _data(score=89, major=3), iteration=1, max_iterations=4, score_threshold=90
    )
    assert stop is False


def test_score_threshold_takes_priority_over_major_findings():
    # score >= threshold AND major == 0: SCORE_THRESHOLD should win
    stop, reason = should_stop(
        _data(score=91, major=0), iteration=1, max_iterations=4, score_threshold=90
    )
    assert reason == "SCORE_THRESHOLD"


def test_custom_score_threshold():
    # Custom threshold of 80
    stop, reason = should_stop(
        _data(score=80, major=2), iteration=1, max_iterations=4, score_threshold=80
    )
    assert stop is True
    assert reason == "SCORE_THRESHOLD"


# ---------------------------------------------------------------------------
# NO_MAJOR_FINDINGS condition
# ---------------------------------------------------------------------------

def test_zero_major_findings_stops():
    stop, reason = should_stop(_data(major=0, score=70), iteration=1, max_iterations=4)
    assert stop is True
    assert reason == "NO_MAJOR_FINDINGS"


def test_nonzero_major_findings_does_not_trigger():
    stop, _ = should_stop(_data(major=1, score=70), iteration=1, max_iterations=4)
    assert stop is False


def test_major_findings_takes_priority_over_max_iterations():
    # major == 0 AND at max iterations: NO_MAJOR_FINDINGS wins
    stop, reason = should_stop(_data(major=0, score=70), iteration=4, max_iterations=4)
    assert reason == "NO_MAJOR_FINDINGS"


# ---------------------------------------------------------------------------
# MAX_ITERATIONS_REACHED condition
# ---------------------------------------------------------------------------

def test_max_iterations_exact_stops():
    stop, reason = should_stop(_data(major=3, score=50), iteration=4, max_iterations=4)
    assert stop is True
    assert reason == "MAX_ITERATIONS_REACHED"


def test_max_iterations_exceeded_stops():
    # Defensive: iteration > max_iterations still stops
    stop, reason = should_stop(_data(major=3, score=50), iteration=5, max_iterations=4)
    assert stop is True
    assert reason == "MAX_ITERATIONS_REACHED"


def test_below_max_iterations_continues():
    stop, reason = should_stop(_data(major=3, score=50), iteration=3, max_iterations=4)
    assert stop is False
    assert reason == "CONTINUE"


# ---------------------------------------------------------------------------
# CONTINUE — none of the stop conditions met
# ---------------------------------------------------------------------------

def test_continue_nominal():
    stop, reason = should_stop(
        _data(status="FAIL", score=60, major=2),
        iteration=2,
        max_iterations=4,
        score_threshold=90,
    )
    assert stop is False
    assert reason == "CONTINUE"


def test_continue_first_iteration():
    stop, reason = should_stop(_data(), iteration=1, max_iterations=4)
    assert stop is False
    assert reason == "CONTINUE"


# ---------------------------------------------------------------------------
# Default values — ensure config defaults are preserved
# ---------------------------------------------------------------------------

def test_default_max_iterations_is_4():
    # At iteration 4, should stop with MAX_ITERATIONS_REACHED by default
    stop, reason = should_stop(_data(major=5, score=30), iteration=4)
    assert stop is True
    assert reason == "MAX_ITERATIONS_REACHED"


def test_default_score_threshold_is_90():
    # Score of 89 should NOT trigger score threshold with default config
    stop, _ = should_stop(_data(score=89, major=3), iteration=2)
    assert stop is False

    # Score of 90 SHOULD trigger with default config
    stop, reason = should_stop(_data(score=90, major=3), iteration=2)
    assert stop is True
    assert reason == "SCORE_THRESHOLD"
