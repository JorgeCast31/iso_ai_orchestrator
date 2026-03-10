import json
import logging
from datetime import datetime
from pathlib import Path

from src.file_manager import read_file, write_file, ensure_dir
from src.claude_client import ClaudeClient
from src.gpt_client import GPTClient
from src.review_parser import parse_review
from src.decision import should_stop
from src.config import (
    INPUT_PLANTILLA,
    INPUT_PLAN,
    PROMPT_CLAUDE_GENERATE,
    PROMPT_GPT_REVIEW,
    PROMPT_CLAUDE_REWRITE,
    OUTPUT_FINAL,
    CLAUDE_MODEL,
    OPENAI_MODEL,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class Pipeline:
    def __init__(self):
        self.max_iterations = 4
        self.claude = ClaudeClient()
        self.gpt = GPTClient()

    def run(self):
        logging.info("Inicio pipeline de revisión documental ISO")

        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        run_dir = Path("outputs") / f"run_{timestamp}"
        ensure_dir(str(run_dir))

        plantilla = read_file(INPUT_PLANTILLA)
        plan_maestro = read_file(INPUT_PLAN)
        prompt_generate = read_file(PROMPT_CLAUDE_GENERATE)
        prompt_review = read_file(PROMPT_GPT_REVIEW)
        prompt_rewrite = read_file(PROMPT_CLAUDE_REWRITE)

        logging.info("Generando borrador inicial con Claude")
        draft_input = (
            f"{prompt_generate}\n\n"
            f"=== PLANTILLA ===\n{plantilla}\n\n"
            f"=== PLAN MAESTRO ===\n{plan_maestro}"
        )
        current_doc = self.claude.generate(draft_input)
        write_file(str(run_dir / "draft_v1.txt"), current_doc)

        iteration = 1
        stop_reason = "UNKNOWN"
        review_data = {
            "status": "FAIL",
            "score": 0,
            "major_findings": 0,
            "medium_findings": 0,
            "minor_findings": 0,
        }

        while iteration <= self.max_iterations:
            logging.info(f"Auditoría iteración {iteration} con GPT")
            review = self.gpt.review(prompt_review, current_doc)
            write_file(str(run_dir / f"review_v{iteration}.txt"), review)

            review_data = parse_review(review)
            stop, reason = should_stop(review_data, iteration, self.max_iterations)

            if stop:
                stop_reason = reason
                logging.info(f"Criterio de parada alcanzado: {reason}")
                break

            logging.info(f"Corrección iteración {iteration} con Claude")
            rewrite_input = (
                f"{prompt_rewrite}\n\n"
                f"=== DOCUMENTO ORIGINAL ===\n{current_doc}\n\n"
                f"=== AUDITORÍA ===\n{review}"
            )
            current_doc = self.claude.generate(rewrite_input)
            write_file(str(run_dir / f"draft_v{iteration + 1}.txt"), current_doc)

            iteration += 1

        write_file(str(run_dir / "final.txt"), current_doc)

        metadata = {
            "claude_model": CLAUDE_MODEL,
            "openai_model": OPENAI_MODEL,
            "max_iterations": self.max_iterations,
            "iterations_completed": iteration,
            "final_reason": stop_reason,
            "final_status": review_data.get("status", "FAIL"),
            "final_score": review_data.get("score", 0),
            "final_major_findings": review_data.get("major_findings", 0),
        }

        write_file(
            str(run_dir / "metadata.json"),
            json.dumps(metadata, indent=2, ensure_ascii=False),
        )

        write_file(OUTPUT_FINAL, current_doc)

        logging.info("Pipeline finalizado exitosamente")