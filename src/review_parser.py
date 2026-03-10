import re


def parse_review(review_text: str) -> dict:
    def extract_int(label: str, default: int = 0) -> int:
        match = re.search(rf"{label}:\s*(\d+)", review_text, re.IGNORECASE)
        return int(match.group(1)) if match else default

    def extract_status() -> str:
        match = re.search(r"STATUS:\s*(PASS|FAIL)", review_text, re.IGNORECASE)
        return match.group(1).upper() if match else "FAIL"

    return {
        "status": extract_status(),
        "score": extract_int("SCORE"),
        "major_findings": extract_int("MAYOR_FINDINGS"),
        "medium_findings": extract_int("MEDIUM_FINDINGS"),
        "minor_findings": extract_int("MINOR_FINDINGS"),
    }