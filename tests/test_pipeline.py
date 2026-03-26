import os
import pytest
from src.pipeline import Pipeline

# Skip the end-to-end test when API credentials are not configured.
# This prevents confusing RuntimeError messages in CI or offline environments.
_MISSING_CREDENTIALS = not (
    os.getenv("ANTHROPIC_API_KEY") and os.getenv("OPENAI_API_KEY")
)


@pytest.mark.skipif(
    _MISSING_CREDENTIALS,
    reason="ANTHROPIC_API_KEY and/or OPENAI_API_KEY not set — skipping live API test",
)
def test_pipeline_runs():
    pipeline = Pipeline()
    pipeline.run()
    assert os.path.exists("outputs/poe_output.txt")
    with open("outputs/poe_output.txt", "r", encoding="utf-8") as f:
        content = f.read()
    assert len(content) > 0
