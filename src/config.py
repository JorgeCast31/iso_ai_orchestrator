import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5-20250929")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

INPUT_PLANTILLA = os.getenv("INPUT_PLANTILLA", "inputs/plantilla_poe.txt")
INPUT_PLAN = os.getenv("INPUT_PLAN", "inputs/plan_maestro.txt")

# Sprint 2B — plan Excel input (empty = disabled; Sprint-2A-compatible mode)
INPUT_PLAN_XLSX = os.getenv("INPUT_PLAN_XLSX", "")
REQUIRE_PLAN_XLSX = os.getenv("REQUIRE_PLAN_XLSX", "false").lower() == "true"

PROMPT_CLAUDE_GENERATE = os.getenv("PROMPT_CLAUDE_GENERATE", "prompts/claude_generate.txt")
PROMPT_GPT_REVIEW = os.getenv("PROMPT_GPT_REVIEW", "prompts/gpt_review.txt")
PROMPT_CLAUDE_REWRITE = os.getenv("PROMPT_CLAUDE_REWRITE", "prompts/claude_rewrite.txt")

# Pipeline control — configurables via .env; defaults preservan comportamiento original
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "4"))
SCORE_THRESHOLD = int(os.getenv("SCORE_THRESHOLD", "90"))

# Ruta canónica de salida final (compatibilidad con integraciones externas)
OUTPUT_FINAL = os.getenv("OUTPUT_FINAL", "outputs/poe_output.txt")

# Rutas legacy — definidas antes del patrón run_TIMESTAMP; no escritas por el pipeline actual
OUTPUT_DRAFT = os.getenv("OUTPUT_DRAFT", "outputs/poe_draft.txt")
OUTPUT_REVIEW = os.getenv("OUTPUT_REVIEW", "outputs/poe_review.txt")

# Sprint 3 — DOCX institucional
INPUT_TEMPLATE_DOCX = os.getenv("INPUT_TEMPLATE_DOCX", "inputs/plantilla_poe.docx")
OUTPUT_DOCX_ENABLED = os.getenv("OUTPUT_DOCX_ENABLED", "true").lower() == "true"
OUTPUT_DOCX_FILENAME = os.getenv("OUTPUT_DOCX_FILENAME", "final.docx")


def validate_env():
    missing = []
    if not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")
    if not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")

    if missing:
        raise RuntimeError(f"Faltan variables de entorno: {', '.join(missing)}")
