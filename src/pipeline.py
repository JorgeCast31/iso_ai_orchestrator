import logging

from src.file_manager import read_file, write_file, ensure_dir
from src.claude_client import ClaudeClient
from src.gpt_client import GPTClient
from src.config import (
    INPUT_PLANTILLA,
    INPUT_PLAN,
    PROMPT_CLAUDE_GENERATE,
    PROMPT_GPT_REVIEW,
    PROMPT_CLAUDE_REWRITE,
    OUTPUT_DRAFT,
    OUTPUT_REVIEW,
    OUTPUT_FINAL,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


class Pipeline:
    def __init__(self):
        self.claude = ClaudeClient()
        self.gpt = GPTClient()

    def run(self):
        logging.info("Leyendo archivos de entrada...")
        plantilla = read_file(INPUT_PLANTILLA)
        plan_maestro = read_file(INPUT_PLAN)

        prompt_claude = read_file(PROMPT_CLAUDE_GENERATE)
        prompt_gpt = read_file(PROMPT_GPT_REVIEW)
        prompt_rewrite = read_file(PROMPT_CLAUDE_REWRITE)

        ensure_dir("outputs")

        logging.info("Paso 1/3: Generando borrador con Claude...")
        draft_input = (
            f"{prompt_claude}\n\n"
            f"=== PLANTILLA ===\n{plantilla}\n\n"
            f"=== PLAN MAESTRO ===\n{plan_maestro}"
        )
        draft = self.claude.generate(draft_input)
        write_file(OUTPUT_DRAFT, draft)

        logging.info("Paso 2/3: Auditando borrador con GPT...")
        review = self.gpt.review(prompt_gpt, draft)
        write_file(OUTPUT_REVIEW, review)

        logging.info("Paso 3/3: Reescribiendo con Claude...")
        rewrite_input = (
            f"{prompt_rewrite}\n\n"
            f"=== POE ORIGINAL ===\n{draft}\n\n"
            f"=== AUDITORÍA ===\n{review}"
        )
        final_doc = self.claude.generate(rewrite_input)
        write_file(OUTPUT_FINAL, final_doc)

        logging.info("Pipeline completado correctamente.")