import time
import logging
import anthropic
from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL

logger = logging.getLogger(__name__)

# Errors that justify a retry — transient network/API/rate-limit conditions.
# Authentication errors, invalid model, etc. are NOT caught here and propagate immediately.
_TRANSIENT_ERRORS = (
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.InternalServerError,
)


class ClaudeClient:
    _MAX_RETRIES = 3
    _RETRY_DELAYS = [1, 2, 4]  # seconds between attempts (exponential backoff)

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.model = CLAUDE_MODEL

    def generate(self, prompt: str, max_tokens: int = 4000) -> str:
        last_error: Exception | None = None

        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
                parts = [
                    block.text
                    for block in response.content
                    if getattr(block, "type", None) == "text"
                ]
                return "\n".join(parts).strip()

            except _TRANSIENT_ERRORS as e:
                last_error = e
                if attempt < self._MAX_RETRIES:
                    wait = self._RETRY_DELAYS[attempt - 1]
                    logger.warning(
                        "Claude API error (intento %d/%d): %s. Reintentando en %ds...",
                        attempt, self._MAX_RETRIES, e, wait,
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        "Claude API error (intento %d/%d): %s. Sin más reintentos.",
                        attempt, self._MAX_RETRIES, e,
                    )

        raise RuntimeError(
            f"Claude API falló tras {self._MAX_RETRIES} intentos. "
            f"Último error: {last_error}"
        ) from last_error
