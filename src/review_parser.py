import re


class ReviewParseError(Exception):
    """Raised when the review text cannot be reliably parsed."""
    pass


def _normalize(text: str) -> str:
    """Strip common markdown formatting and normalize line endings."""
    # Remove bold/italic markers: **text**, *text*, __text__, _text_
    text = re.sub(r'\*{1,2}([^*\n]+)\*{1,2}', r'\1', text)
    text = re.sub(r'_{1,2}([^_\n]+)_{1,2}', r'\1', text)
    # Normalize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    return text


def parse_review(review_text: str) -> dict:
    """
    Parse structured review output from GPT auditor.

    Returns a dict with keys: status, score, major_findings,
    medium_findings, minor_findings.

    Critical fields — ALL must be present in the text:
      STATUS, SCORE, MAYOR_FINDINGS

    Raises ReviewParseError if any critical field is absent.
    Defaulting MAYOR_FINDINGS to 0 silently would trigger a spurious
    NO_MAJOR_FINDINGS stop; we reject the review loudly instead.

    Non-critical fields (MEDIUM_FINDINGS, MINOR_FINDINGS) default to 0
    if absent — their absence does not affect stop conditions.
    """
    normalized = _normalize(review_text)
    found_fields: set = set()

    def extract_int(label: str, default: int = 0) -> int:
        # Tolerates extra whitespace between label, colon, and value
        match = re.search(
            rf"{re.escape(label)}\s*:\s*(\d+)",
            normalized,
            re.IGNORECASE,
        )
        if match:
            found_fields.add(label.upper())
            return int(match.group(1))
        return default

    def extract_status() -> str:
        match = re.search(r"STATUS\s*:\s*(PASS|FAIL)", normalized, re.IGNORECASE)
        if match:
            found_fields.add("STATUS")
            return match.group(1).upper()
        return "FAIL"

    status = extract_status()
    score = extract_int("SCORE")
    major_findings = extract_int("MAYOR_FINDINGS")
    medium_findings = extract_int("MEDIUM_FINDINGS")
    minor_findings = extract_int("MINOR_FINDINGS")

    # All three critical fields must be explicitly present in the response.
    # A partial parse (e.g. only STATUS found) would silently default
    # MAYOR_FINDINGS to 0 and trigger a false NO_MAJOR_FINDINGS stop.
    required_fields = {"STATUS", "SCORE", "MAYOR_FINDINGS"}
    missing_critical = required_fields - found_fields
    if missing_critical:
        snippet = review_text[:300].replace('\n', ' ')
        raise ReviewParseError(
            f"Parse de revisión incompleto: campos críticos ausentes: "
            f"{sorted(missing_critical)}. "
            f"Texto recibido (primeros 300 chars): '{snippet}'"
        )

    return {
        "status": status,
        "score": score,
        "major_findings": major_findings,
        "medium_findings": medium_findings,
        "minor_findings": minor_findings,
    }
