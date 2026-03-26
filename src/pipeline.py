import json
import logging
import traceback as tb
from datetime import datetime
from pathlib import Path

from src.file_manager import read_file, write_file, ensure_dir
from src.claude_client import ClaudeClient
from src.gpt_client import GPTClient
from src.review_parser import parse_review
from src.decision import should_stop
from src.document_extractor import extract_document_structure
from src.document_validator import validate_document
from src.plan_loader import load_plan_xlsx, PlanLoadError
from src.docx_builder import build_docx_from_template, DocxBuildError
from src.config import (
    INPUT_PLANTILLA,
    INPUT_PLAN,
    INPUT_PLAN_XLSX,
    REQUIRE_PLAN_XLSX,
    INPUT_TEMPLATE_DOCX,
    OUTPUT_DOCX_ENABLED,
    OUTPUT_DOCX_FILENAME,
    PROMPT_CLAUDE_GENERATE,
    PROMPT_GPT_REVIEW,
    PROMPT_CLAUDE_REWRITE,
    OUTPUT_FINAL,
    CLAUDE_MODEL,
    OPENAI_MODEL,
    MAX_ITERATIONS,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(
        self,
        *,
        run_dir: "str | Path | None" = None,
        input_plantilla: str | None = None,
        input_plan: str | None = None,
        input_plan_xlsx: str | None = None,
    ):
        if MAX_ITERATIONS < 1:
            raise ValueError(
                f"MAX_ITERATIONS debe ser >= 1; valor configurado: {MAX_ITERATIONS}"
            )
        self.max_iterations = MAX_ITERATIONS
        self.claude = ClaudeClient()
        self.gpt = GPTClient()
        # Per-job path overrides for API integration (None = use config defaults).
        # These do not affect any pipeline logic — only where files are read/written.
        self._run_dir_override: "Path | None" = Path(run_dir) if run_dir else None
        self._input_plantilla: str = input_plantilla or INPUT_PLANTILLA
        self._input_plan: str = input_plan or INPUT_PLAN
        self._input_plan_xlsx: str = (
            input_plan_xlsx if input_plan_xlsx is not None else INPUT_PLAN_XLSX
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_metadata(
        self,
        *,
        run_timestamp: str,
        iterations_completed: int,
        stop_reason: str,
        review_data: dict,
        iteration_history: list,
        final_status: str | None = None,
        error_message: str | None = None,
        error_iteration: int | None = None,
        error_stage: str | None = None,
        # Sprint 2A additions — all optional for backward compatibility
        validator_runs: int = 0,
        last_validator_status: str = "NOT_RUN",
        last_validator_blocking_findings_count: int = 0,
        last_validator_observation_count: int = 0,
        last_pass_rejected_by_validator: bool = False,
        validator_history: list | None = None,
        # Sprint 2B additions — all optional for backward compatibility
        plan_loaded: bool = False,
        plan_source: str = "",
        plan_activities_count: int = 0,
        require_plan_xlsx: bool = False,
        # Sprint 3 additions — all optional for backward compatibility
        docx_enabled: bool = False,
        docx_generated: bool = False,
        docx_output_path: str = "",
        docx_template_path: str = "",
        docx_warnings: "list | None" = None,
        docx_error_message: "str | None" = None,
    ) -> dict:
        """
        Build the metadata dict.  All original fields are preserved;
        Sprint 1 adds run_timestamp, iteration_history, and error fields.
        Sprint 2A adds validator tracking fields (all additive).
        Sprint 2B adds plan tracking fields (all additive).
        Sprint 3 adds DOCX generation tracking fields (all additive).
        """
        meta = {
            # Original fields — must not be removed or renamed
            "claude_model": CLAUDE_MODEL,
            "openai_model": OPENAI_MODEL,
            "max_iterations": self.max_iterations,
            "iterations_completed": iterations_completed,
            "final_reason": stop_reason,
            "final_status": final_status or review_data.get("status", "FAIL"),
            "final_score": review_data.get("score", 0),
            "final_major_findings": review_data.get("major_findings", 0),
            # Sprint 1 additions
            "run_timestamp": run_timestamp,
            # Explicit aliases: each equals the number of GPT review cycles completed.
            # drafts_generated: draft_v1 (pre-loop) + one new draft per completed rewrite.
            "reviews_completed": iterations_completed,
            "drafts_generated": iterations_completed,
            "iteration_history": iteration_history,
            # Sprint 2A additions
            "validator_runs": validator_runs,
            "last_validator_status": last_validator_status,
            "last_validator_blocking_findings_count": last_validator_blocking_findings_count,
            "last_validator_observation_count": last_validator_observation_count,
            "last_pass_rejected_by_validator": last_pass_rejected_by_validator,
            "validator_history": validator_history or [],
            # Sprint 2B additions
            "plan_loaded": plan_loaded,
            "plan_source": plan_source,
            "plan_activities_count": plan_activities_count,
            "require_plan_xlsx": require_plan_xlsx,
            # Sprint 3 additions
            "docx_enabled": docx_enabled,
            "docx_generated": docx_generated,
            "docx_output_path": docx_output_path,
            "docx_template_path": docx_template_path,
            "docx_warnings": docx_warnings or [],
            "docx_error_message": docx_error_message,
        }
        if error_message is not None:
            meta["error_message"] = error_message
        if error_iteration is not None:
            meta["error_iteration"] = error_iteration
        if error_stage is not None:
            meta["error_stage"] = error_stage
        return meta

    @staticmethod
    def _build_rewrite_input(
        prompt_rewrite: str,
        current_doc: str,
        review: str,
        validator_rejection: dict | None = None,
    ) -> str:
        """
        Build the rewrite input for Claude.

        When validator_rejection is provided (validator rejected a GPT PASS),
        a '=== VALIDACIÓN ESTRUCTURAL ===' section is appended listing the
        blocking findings Claude must address in its rewrite.

        The base format is identical to Sprint 1 when no rejection is present,
        so existing behaviour is fully preserved for the non-PASS path.
        """
        base = (
            f"{prompt_rewrite}\n\n"
            f"=== DOCUMENTO ORIGINAL ===\n{current_doc}\n\n"
            f"=== AUDITORÍA ===\n{review}"
        )
        if not validator_rejection or not validator_rejection.get("blocking_findings"):
            return base

        blocking = validator_rejection["blocking_findings"]
        lines = [
            f"\n\n=== VALIDACIÓN ESTRUCTURAL ===",
            f"El validador estructural encontró {len(blocking)} hallazgo(s) bloqueante(s).",
            "Debes resolver TODOS los hallazgos listados para obtener aprobación formal:",
        ]
        for i, finding in enumerate(blocking, 1):
            entry = (
                f"{i}. [{finding['rule_id']}] "
                f"Sección {finding['section'].upper()}: {finding['message']}"
            )
            if finding.get("evidence"):
                entry += f'\n   Evidencia: "{finding["evidence"]}"'
            lines.append(entry)
        return base + '\n'.join(lines)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self):
        logger.info("Inicio pipeline de revisión documental ISO")

        # These must be defined before the try block so they are
        # accessible in the except block for evidence preservation.
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        run_dir = (
            self._run_dir_override
            if self._run_dir_override is not None
            else Path("outputs") / f"run_{timestamp}"
        )

        iteration = 1
        current_stage = "init"
        current_doc = ""
        stop_reason = "UNKNOWN"
        review_data: dict = {
            "status": "FAIL",
            "score": 0,
            "major_findings": 0,
            "medium_findings": 0,
            "minor_findings": 0,
        }
        iteration_history: list = []

        # Sprint 2A: validator tracking state
        validator_runs = 0
        last_validator_status = "NOT_RUN"
        last_validator_blocking_count = 0
        last_validator_obs_count = 0
        last_pass_rejected = False
        validator_history: list = []

        # Sprint 2B: plan tracking state
        plan_data: dict | None = None
        plan_loaded = False
        plan_source = ""
        plan_activities_count = 0

        # Sprint 3: DOCX tracking state — initialised here so the error-path
        # _build_metadata call can always reference these, regardless of where
        # in the try block a crash occurs.
        docx_generated = False
        docx_output_path = ""
        docx_warnings: list = []
        docx_error_message: str | None = None

        try:
            ensure_dir(str(run_dir))

            # --- Load inputs ---
            current_stage = "load_inputs"
            plantilla = read_file(self._input_plantilla)
            plan_maestro = read_file(self._input_plan)
            prompt_generate = read_file(PROMPT_CLAUDE_GENERATE)
            prompt_review = read_file(PROMPT_GPT_REVIEW)
            prompt_rewrite = read_file(PROMPT_CLAUDE_REWRITE)

            # Sprint 2B: load plan Excel (optional; None if path not configured)
            current_stage = "load_plan_xlsx"
            try:
                plan_data = load_plan_xlsx(self._input_plan_xlsx)
            except PlanLoadError as plan_err:
                if REQUIRE_PLAN_XLSX:
                    raise RuntimeError(
                        f"Plan Excel requerido pero no se pudo cargar: {plan_err}"
                    ) from plan_err
                logger.warning(
                    "No se pudo cargar el plan Excel (REQUIRE_PLAN_XLSX=false, "
                    "continuando sin plan): %s",
                    plan_err,
                )
                plan_data = None

            if plan_data is not None:
                plan_loaded = True
                plan_source = plan_data.get("source_path", INPUT_PLAN_XLSX)
                plan_activities_count = len(plan_data.get("actividades", []))
                logger.info(
                    "Plan Excel cargado: familia=%s, actividades=%d, fuente=%s",
                    plan_data.get("familia_equipo", "?"),
                    plan_activities_count,
                    plan_source,
                )

            # --- Initial draft ---
            current_stage = "generate_draft_v1"
            logger.info("Generando borrador inicial con Claude")
            draft_input = (
                f"{prompt_generate}\n\n"
                f"=== PLANTILLA ===\n{plantilla}\n\n"
                f"=== PLAN MAESTRO ===\n{plan_maestro}"
            )
            current_doc = self.claude.generate(draft_input)
            write_file(str(run_dir / "draft_v1.txt"), current_doc)

            # --- Iterative review loop ---
            while iteration <= self.max_iterations:
                current_stage = f"review_v{iteration}"
                logger.info("Auditoría iteración %d con GPT", iteration)
                review = self.gpt.review(prompt_review, current_doc)
                write_file(str(run_dir / f"review_v{iteration}.txt"), review)

                review_data = parse_review(review)

                # Build history entry; may be augmented with validator info below.
                history_entry = {
                    "iteration": iteration,
                    "score": review_data["score"],
                    "status": review_data["status"],
                    "major_findings": review_data["major_findings"],
                    "medium_findings": review_data["medium_findings"],
                    "minor_findings": review_data["minor_findings"],
                    "timestamp": datetime.now().isoformat(),
                }

                logger.info(
                    "Iteración %d — STATUS: %s | SCORE: %d | MAYOR: %d | MEDIO: %d | MENOR: %d",
                    iteration,
                    review_data["status"],
                    review_data["score"],
                    review_data["major_findings"],
                    review_data["medium_findings"],
                    review_data["minor_findings"],
                )

                stop, reason = should_stop(review_data, iteration, self.max_iterations)

                # Sprint 2A: dual-gate — validator only triggers on GPT PASS.
                validator_rejection: dict | None = None

                if stop and reason == "PASS":
                    # -----------------------------------------------------------
                    # Dual-gate: GPT said PASS → run structural validator.
                    # -----------------------------------------------------------
                    current_stage = f"validate_v{iteration}"
                    logger.info(
                        "GPT PASS en iteración %d — ejecutando validación estructural",
                        iteration,
                    )
                    val_result = validate_document(current_doc, plan_data=plan_data)
                    doc_structure = extract_document_structure(current_doc)

                    # Persist validator artifacts for full traceability
                    write_file(
                        str(run_dir / f"document_v{iteration}.json"),
                        json.dumps(doc_structure, indent=2, ensure_ascii=False),
                    )
                    write_file(
                        str(run_dir / f"validator_v{iteration}.json"),
                        json.dumps(val_result, indent=2, ensure_ascii=False),
                    )

                    # Update validator tracking state
                    validator_runs += 1
                    last_validator_status = "VALID" if val_result["valid"] else "INVALID"
                    last_validator_blocking_count = len(val_result["blocking_findings"])
                    last_validator_obs_count = len(val_result["observations"])
                    validator_history.append({
                        "iteration": iteration,
                        "valid": val_result["valid"],
                        "blocking_findings_count": last_validator_blocking_count,
                        "observation_count": last_validator_obs_count,
                    })

                    # Augment history entry with validator outcome
                    history_entry["validator_ran"] = True
                    history_entry["validator_valid"] = val_result["valid"]
                    history_entry["validator_blocking_count"] = last_validator_blocking_count

                    if val_result["valid"]:
                        # Real PASS: both GPT and structural validator approved.
                        stop_reason = "PASS_VALIDATED"
                        logger.info(
                            "PASS REAL confirmado: GPT PASS + validación estructural aprobada "
                            "(iteración %d, %d observaciones)",
                            iteration,
                            last_validator_obs_count,
                        )
                        iteration_history.append(history_entry)
                        break
                    else:
                        # GPT said PASS but validator rejected.
                        logger.warning(
                            "GPT dijo PASS en iteración %d pero validator rechazó — "
                            "%d hallazgo(s) bloqueante(s): %s",
                            iteration,
                            last_validator_blocking_count,
                            [f["rule_id"] for f in val_result["blocking_findings"]],
                        )
                        last_pass_rejected = True
                        if iteration >= self.max_iterations:
                            # No more rewrites available; stop with max-iterations reason.
                            stop_reason = "MAX_ITERATIONS_REACHED"
                            logger.warning(
                                "Límite de iteraciones alcanzado con PASS sin validar "
                                "estructuralmente"
                            )
                            iteration_history.append(history_entry)
                            break
                        # Continue — pass blocking findings to next rewrite.
                        validator_rejection = val_result

                elif stop:
                    # Non-PASS stop condition — existing behaviour fully preserved.
                    stop_reason = reason
                    logger.info("Criterio de parada alcanzado: %s", reason)
                    iteration_history.append(history_entry)
                    break

                # Append history for the "continue" paths (PASS-rejected-continue
                # and non-stop).  Paths that break above already appended.
                iteration_history.append(history_entry)

                # --- Claude rewrite ---
                current_stage = f"rewrite_v{iteration + 1}"
                logger.info("Corrección iteración %d con Claude", iteration)
                rewrite_input = self._build_rewrite_input(
                    prompt_rewrite, current_doc, review, validator_rejection
                )
                current_doc = self.claude.generate(rewrite_input)
                write_file(str(run_dir / f"draft_v{iteration + 1}.txt"), current_doc)

                iteration += 1

            # --- Finalizar artefactos ---
            write_file(str(run_dir / "final.txt"), current_doc)

            # Always write document.json for trazabilidad regardless of stop_reason.
            # metadata.json stop_reason indicates whether validation was approved.
            final_doc_structure = extract_document_structure(current_doc)
            write_file(
                str(run_dir / "document.json"),
                json.dumps(final_doc_structure, indent=2, ensure_ascii=False),
            )

            # Sprint 3: DOCX generation — terminal step, non-fatal on failure.
            # Runs after document.json so build_docx_from_template receives the
            # already-extracted structure; result collected before metadata is written.
            current_stage = "docx_build"
            if OUTPUT_DOCX_ENABLED:
                docx_out = str(run_dir / OUTPUT_DOCX_FILENAME)
                try:
                    docx_result = build_docx_from_template(
                        INPUT_TEMPLATE_DOCX,
                        docx_out,
                        final_doc_structure,
                        current_doc,
                    )
                    docx_generated = True
                    docx_output_path = docx_result["output_path"]
                    docx_warnings = docx_result["warnings"]
                    if docx_warnings:
                        logger.warning(
                            "DOCX generado con %d advertencia(s): %s",
                            len(docx_warnings), docx_warnings,
                        )
                    else:
                        logger.info("DOCX generado: %s", docx_output_path)
                    # Persist full build result for debugging
                    write_file(
                        str(run_dir / "docx_build.json"),
                        json.dumps(docx_result, indent=2, ensure_ascii=False),
                    )
                except DocxBuildError as exc:
                    docx_error_message = str(exc)
                    logger.warning("DOCX no generado (non-fatal): %s", exc)
                except Exception as exc:
                    docx_error_message = f"Error inesperado en DOCX builder: {exc}"
                    logger.warning("Error inesperado en DOCX builder (non-fatal): %s", exc)

            metadata = self._build_metadata(
                run_timestamp=timestamp,
                iterations_completed=iteration,
                stop_reason=stop_reason,
                review_data=review_data,
                iteration_history=iteration_history,
                validator_runs=validator_runs,
                last_validator_status=last_validator_status,
                last_validator_blocking_findings_count=last_validator_blocking_count,
                last_validator_observation_count=last_validator_obs_count,
                last_pass_rejected_by_validator=last_pass_rejected,
                validator_history=validator_history,
                plan_loaded=plan_loaded,
                plan_source=plan_source,
                plan_activities_count=plan_activities_count,
                require_plan_xlsx=REQUIRE_PLAN_XLSX,
                docx_enabled=OUTPUT_DOCX_ENABLED,
                docx_generated=docx_generated,
                docx_output_path=docx_output_path,
                docx_template_path=INPUT_TEMPLATE_DOCX if OUTPUT_DOCX_ENABLED else "",
                docx_warnings=docx_warnings,
                docx_error_message=docx_error_message,
            )
            write_file(
                str(run_dir / "metadata.json"),
                json.dumps(metadata, indent=2, ensure_ascii=False),
            )

            # Preserve compatibility with external consumers of poe_output.txt
            write_file(OUTPUT_FINAL, current_doc)

            logger.info("Pipeline finalizado exitosamente. Run: %s", run_dir)

        except Exception as e:
            logger.error("Pipeline falló en etapa '%s': %s", current_stage, e)

            # Always attempt to preserve partial evidence in run_dir.
            try:
                error_traceback = tb.format_exc()
                write_file(str(run_dir / "error.txt"), error_traceback)

                error_metadata = self._build_metadata(
                    run_timestamp=timestamp,
                    iterations_completed=iteration,
                    stop_reason="PIPELINE_ERROR",
                    review_data=review_data,
                    iteration_history=iteration_history,
                    final_status="ERROR",
                    error_message=str(e),
                    error_iteration=iteration,
                    error_stage=current_stage,
                    validator_runs=validator_runs,
                    last_validator_status=last_validator_status,
                    last_validator_blocking_findings_count=last_validator_blocking_count,
                    last_validator_observation_count=last_validator_obs_count,
                    last_pass_rejected_by_validator=last_pass_rejected,
                    validator_history=validator_history,
                    plan_loaded=plan_loaded,
                    plan_source=plan_source,
                    plan_activities_count=plan_activities_count,
                    require_plan_xlsx=REQUIRE_PLAN_XLSX,
                    docx_enabled=OUTPUT_DOCX_ENABLED,
                    docx_generated=docx_generated,
                    docx_output_path=docx_output_path,
                    docx_template_path=INPUT_TEMPLATE_DOCX if OUTPUT_DOCX_ENABLED else "",
                    docx_warnings=docx_warnings,
                    docx_error_message=docx_error_message,
                )
                write_file(
                    str(run_dir / "metadata.json"),
                    json.dumps(error_metadata, indent=2, ensure_ascii=False),
                )
                logger.info("Evidencia parcial preservada en: %s", run_dir)
            except Exception as write_err:
                logger.error(
                    "No se pudo escribir evidencia de error en %s: %s",
                    run_dir,
                    write_err,
                )

            raise
