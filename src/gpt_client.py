import time
import logging
import openai          # needed for openai.RateLimitError et al.
from openai import OpenAI  # needed for the client class
from src.config import OPENAI_API_KEY, OPENAI_MODEL

logger = logging.getLogger(__name__)

# Errors that justify a retry — transient network/API/rate-limit conditions.
# Authentication errors, invalid model, etc. are NOT caught here and propagate immediately.
_TRANSIENT_ERRORS = (
    openai.RateLimitError,
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.InternalServerError,
)


class GPTClient:
    _MAX_RETRIES = 3
    _RETRY_DELAYS = [1, 2, 4]  # seconds between attempts (exponential backoff)

    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.model = OPENAI_MODEL

    def review(self, prompt: str, document: str, max_tokens: int = 4000) -> str:
        last_error: Exception | None = None

        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": document},
                    ],
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content.strip()

            except _TRANSIENT_ERRORS as e:
                last_error = e
                if attempt < self._MAX_RETRIES:
                    wait = self._RETRY_DELAYS[attempt - 1]
                    logger.warning(
                        "GPT API error (intento %d/%d): %s. Reintentando en %ds...",
                        attempt, self._MAX_RETRIES, e, wait,
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        "GPT API error (intento %d/%d): %s. Sin más reintentos.",
                        attempt, self._MAX_RETRIES, e,
                    )

        raise RuntimeError(
            f"GPT API falló tras {self._MAX_RETRIES} intentos. "
            f"Último error: {last_error}"
        ) from last_error
