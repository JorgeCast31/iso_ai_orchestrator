import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5-20250929")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

INPUT_PLANTILLA = os.getenv("INPUT_PLANTILLA", "inputs/plantilla_poe.txt")
INPUT_PLAN = os.getenv("INPUT_PLAN", "inputs/plan_maestro.txt")

PROMPT_CLAUDE_GENERATE = os.getenv("PROMPT_CLAUDE_GENERATE", "prompts/claude_generate.txt")
PROMPT_GPT_REVIEW = os.getenv("PROMPT_GPT_REVIEW", "prompts/gpt_review.txt")
PROMPT_CLAUDE_REWRITE = os.getenv("PROMPT_CLAUDE_REWRITE", "prompts/claude_rewrite.txt")

OUTPUT_DRAFT = os.getenv("OUTPUT_DRAFT", "outputs/poe_draft.txt")
OUTPUT_REVIEW = os.getenv("OUTPUT_REVIEW", "outputs/poe_review.txt")
OUTPUT_FINAL = os.getenv("OUTPUT_FINAL", "outputs/poe_output.txt")


def validate_env():
    missing = []
    if not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")
    if not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")

    if missing:
        raise RuntimeError(f"Faltan variables de entorno: {', '.join(missing)}")
