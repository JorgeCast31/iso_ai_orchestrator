def should_stop(review_data: dict, iteration: int, max_iterations: int = 4) -> tuple[bool, str]:
    if review_data["status"] == "PASS":
        return True, "PASS"

    if review_data["score"] >= 90:
        return True, "SCORE_THRESHOLD"

    if review_data["major_findings"] == 0:
        return True, "NO_MAJOR_FINDINGS"

    if iteration >= max_iterations:
        return True, "MAX_ITERATIONS_REACHED"

    return False, "CONTINUE"