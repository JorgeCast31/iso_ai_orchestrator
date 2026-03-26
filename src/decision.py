from src.config import SCORE_THRESHOLD


def should_stop(
    review_data: dict,
    iteration: int,
    max_iterations: int = 4,
    score_threshold: int = SCORE_THRESHOLD,
) -> tuple[bool, str]:
    """
    Evaluate stop conditions in priority order:
      1. STATUS == PASS
      2. SCORE >= score_threshold
      3. MAYOR_FINDINGS == 0
      4. iteration >= max_iterations
    Returns (should_stop: bool, reason: str).
    """
    if review_data["status"] == "PASS":
        return True, "PASS"

    if review_data["score"] >= score_threshold:
        return True, "SCORE_THRESHOLD"

    if review_data["major_findings"] == 0:
        return True, "NO_MAJOR_FINDINGS"

    if iteration >= max_iterations:
        return True, "MAX_ITERATIONS_REACHED"

    return False, "CONTINUE"
