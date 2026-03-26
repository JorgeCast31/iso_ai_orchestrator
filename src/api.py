"""
ISO Orchestrator — FastAPI service layer.

Wraps Pipeline.run() behind a minimal REST API + server-rendered UI.
No auth, no database.  Filesystem is the only persistence layer.

Endpoints (JSON):
  POST /jobs                            create + queue a job
  GET  /api/jobs                        list all jobs
  GET  /api/jobs/{job_id}               job status + file list
  GET  /api/jobs/{job_id}/files/{name}  download / serve a file

Endpoints (HTML):
  GET  /                                upload form
  GET  /jobs                            jobs list
  GET  /jobs/{job_id}                   job detail with preview
"""
import json
import logging
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from src.pipeline import Pipeline
from src.plan_loader import load_plan_xlsx, PlanLoadError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RUNS_DIR = Path("runs")
RUNS_DIR.mkdir(exist_ok=True)

_TEXT_EXTENSIONS = {".txt", ".json", ".md", ".log"}
_PREVIEW_MAX_BYTES = 32_768  # 32 KB — enough for any POE section

# Upload validation
_ACCEPTED_TEMPLATE_SUFFIXES = {".pdf"}
_ACCEPTED_PLAN_SUFFIXES     = {".xlsx"}
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="ISO Orchestrator", docs_url="/api/docs")
templates = Jinja2Templates(directory="templates")

# Background worker — max 2 concurrent pipelines (local tool, not a server farm)
_executor = ThreadPoolExecutor(max_workers=2)

# In-memory job registry; mirrored to disk so a server restart recovers state
_jobs: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Disk persistence helpers
# ---------------------------------------------------------------------------


def _job_path(job_id: str) -> Path:
    return RUNS_DIR / job_id / "job.json"


def _persist(job: dict) -> None:
    path = _job_path(job["job_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(job, fh, indent=2, ensure_ascii=False, default=str)


def _update(job_id: str, status: str, **extra) -> None:
    job = _jobs.get(job_id, {})
    job["status"] = status
    job.update(extra)
    _jobs[job_id] = job
    _persist(job)


# ---------------------------------------------------------------------------
# Startup — reload jobs written by previous server sessions
# ---------------------------------------------------------------------------


@app.on_event("startup")
def _startup() -> None:
    if not RUNS_DIR.exists():
        return
    for job_dir in sorted(RUNS_DIR.iterdir()):
        jf = job_dir / "job.json"
        if not jf.is_file():
            continue
        try:
            with open(jf, encoding="utf-8") as fh:
                job = json.load(fh)
            # Jobs that were "running" when the server died are now stuck —
            # mark them failed so the UI doesn't spin forever.
            if job.get("status") in ("queued", "running"):
                job["status"] = "failed"
                job["error_message"] = "El servidor se reinició mientras el job estaba activo."
                _persist(job)
            _jobs[job["job_id"]] = job
        except Exception:
            pass
    logger.info("ISO Orchestrator: %d job(s) cargados desde disco.", len(_jobs))


# ---------------------------------------------------------------------------
# Background worker — called in a ThreadPoolExecutor thread
# ---------------------------------------------------------------------------


def _execute_job(job_id: str) -> None:
    job = _jobs[job_id]
    outputs_dir = Path(job["outputs_dir"])
    outputs_dir.mkdir(parents=True, exist_ok=True)

    _update(job_id, "running", started_at=datetime.now().isoformat())
    try:
        pipeline = Pipeline(
            run_dir=outputs_dir,
            input_plantilla=job["input_plantilla"],
            input_plan=job["input_plan"],
            input_plan_xlsx=job.get("input_plan_xlsx") or "",
        )
        pipeline.run()

        output_files = sorted(f.name for f in outputs_dir.iterdir() if f.is_file())
        _update(
            job_id,
            "completed",
            completed_at=datetime.now().isoformat(),
            output_files=output_files,
        )
    except Exception as exc:
        logger.exception("Job %s falló", job_id)
        _update(
            job_id,
            "failed",
            completed_at=datetime.now().isoformat(),
            error_message=str(exc),
        )


# ---------------------------------------------------------------------------
# Upload helpers
# ---------------------------------------------------------------------------


def _save_upload(upload: UploadFile, dest_dir: Path, stem: str) -> Path:
    """Write an uploaded file to dest_dir/{stem}{original_suffix} and return its path."""
    suffix = Path(upload.filename or "").suffix.lower() or ".txt"
    dest = dest_dir / f"{stem}{suffix}"
    upload.file.seek(0)
    with open(dest, "wb") as fh:
        shutil.copyfileobj(upload.file, fh)
    return dest


def _to_text(path: Path) -> str:
    """Return plain text from a .pdf, .docx, or .txt file."""
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n\n".join(p.strip() for p in pages if p.strip())
        except Exception as exc:
            raise ValueError(f"No se pudo leer el PDF '{path.name}': {exc}") from exc
        if not text.strip():
            raise ValueError(
                f"No se extrajo texto del PDF '{path.name}'. "
                "El archivo puede ser un PDF escaneado sin capa de texto."
            )
        return text

    if suffix == ".docx":
        try:
            from docx import Document
            doc = Document(str(path))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception as exc:
            raise ValueError(f"No se pudo leer el archivo .docx '{path.name}': {exc}") from exc

    # .txt and any other accepted text format
    return path.read_text(encoding="utf-8", errors="replace")


def _plan_data_to_text(plan_data: dict) -> str:
    """
    Serialize plan_data (from load_plan_xlsx) into structured plain text
    for Claude's generation input.  Uses original field values (not normalized)
    so Claude sees the real names, roles, and codes from the Excel file.
    """
    lines: list[str] = [
        f"PLAN DE MANTENIMIENTO — {plan_data['familia_equipo']}",
        "",
        "ACTIVIDADES:",
    ]
    for act in plan_data["actividades"]:
        lines.append(
            f"  [{act['actividad_id']}] {act['nombre']}"
            f" | Frecuencia: {act['frecuencia']}"
            f" | Responsable: {act['responsable']}"
            f" | Registro: {act['registro_codigo']}"
        )

    # Unique original responsable values (preserves casing / accents for Claude)
    orig_responsables = sorted({a["responsable"] for a in plan_data["actividades"]})
    lines += ["", "RESPONSABLES:"] + [f"  - {r}" for r in orig_responsables]
    lines += ["", "REGISTROS:"]    + [f"  - {r}" for r in plan_data["registros"]]
    lines += ["", "FRECUENCIAS:"]  + [f"  - {f}" for f in plan_data["frecuencias"]]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# POST /jobs
# ---------------------------------------------------------------------------


@app.post("/jobs", status_code=202)
async def create_job(
    template_file: UploadFile = File(..., description="Plantilla POE (.pdf, .txt o .docx)"),
    plan_file: UploadFile = File(..., description="Plan maestro (.xlsx, .txt o .docx)"),
    context: Optional[str] = Form(None, description="Contexto adicional (equipo, norma, etc.)"),
):
    """
    Create a new pipeline job.  Immediately returns { job_id, status: "queued" }.
    The pipeline runs in the background; poll GET /api/jobs/{job_id} for progress.
    """
    # ------------------------------------------------------------------
    # C — Validate extension and size BEFORE any disk I/O
    # ------------------------------------------------------------------
    template_suffix = Path(template_file.filename or "").suffix.lower()
    if template_suffix not in _ACCEPTED_TEMPLATE_SUFFIXES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Tipo de plantilla no soportado: '{template_suffix or 'sin extensión'}'. "
                f"Formatos aceptados: {', '.join(sorted(_ACCEPTED_TEMPLATE_SUFFIXES))}"
            ),
        )

    plan_suffix = Path(plan_file.filename or "").suffix.lower()
    if plan_suffix not in _ACCEPTED_PLAN_SUFFIXES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Tipo de plan no soportado: '{plan_suffix or 'sin extensión'}'. "
                f"Formatos aceptados: {', '.join(sorted(_ACCEPTED_PLAN_SUFFIXES))}"
            ),
        )

    # Size check via seek — avoids reading the full file into memory
    for upload, label in [(template_file, "plantilla"), (plan_file, "plan")]:
        upload.file.seek(0, 2)
        size = upload.file.tell()
        upload.file.seek(0)
        if size > _MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Archivo de {label} demasiado grande "
                    f"({size // (1024 * 1024)} MB). "
                    f"Máximo permitido: {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
                ),
            )

    # ------------------------------------------------------------------
    # Create job directories (only after validation passes)
    # ------------------------------------------------------------------
    job_id = uuid.uuid4().hex
    job_dir = RUNS_DIR / job_id
    inputs_dir = job_dir / "inputs"
    outputs_dir = job_dir / "outputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    # --- Persist original uploads for reference / debugging ---
    template_path = _save_upload(template_file, inputs_dir, "template_original")
    plan_path = _save_upload(plan_file, inputs_dir, "plan_original")

    # ------------------------------------------------------------------
    # A — Prepare pipeline input: plantilla (text)
    # ------------------------------------------------------------------
    try:
        template_text = _to_text(template_path)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    plantilla_txt = inputs_dir / "plantilla_poe.txt"
    plantilla_txt.write_text(template_text, encoding="utf-8")

    # ------------------------------------------------------------------
    # B — Prepare pipeline input: plan maestro (text) + optional xlsx
    # ------------------------------------------------------------------
    input_plan_xlsx = ""

    if plan_path.suffix.lower() == ".xlsx":
        # Load the xlsx now so Claude receives real activity data, not a
        # placeholder.  The same file is also passed to the pipeline so
        # plan_loader can run cross-validation without a second load.
        try:
            plan_data = load_plan_xlsx(str(plan_path))
        except PlanLoadError as exc:
            raise HTTPException(status_code=422, detail=f"Plan Excel inválido: {exc}")
        if plan_data is None:
            raise HTTPException(
                status_code=422,
                detail="El archivo Excel de plan está vacío o no pudo ser analizado.",
            )
        input_plan_xlsx = str(plan_path)
        plan_text_body = _plan_data_to_text(plan_data)
    else:
        try:
            plan_text_body = _to_text(plan_path)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    # Prepend free-text context for both xlsx and text plans
    if context:
        plan_text_body = f"CONTEXTO ADICIONAL:\n{context}\n\n{plan_text_body}"

    plan_txt = inputs_dir / "plan_maestro.txt"
    plan_txt.write_text(plan_text_body, encoding="utf-8")

    # --- Build job record ---
    job: dict = {
        "job_id": job_id,
        "status": "queued",
        "created_at": datetime.now().isoformat(),
        "started_at": None,
        "completed_at": None,
        "context": context or "",
        "template_filename": template_file.filename or "template",
        "plan_filename": plan_file.filename or "plan",
        "inputs_dir": str(inputs_dir),
        "outputs_dir": str(outputs_dir),
        "input_plantilla": str(plantilla_txt),
        "input_plan": str(plan_txt),
        "input_plan_xlsx": input_plan_xlsx,
        "output_files": [],
        "error_message": None,
    }
    _jobs[job_id] = job
    _persist(job)

    _executor.submit(_execute_job, job_id)

    return {"job_id": job_id, "status": "queued"}


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------


@app.get("/api/jobs")
def api_list_jobs():
    return sorted(_jobs.values(), key=lambda j: j.get("created_at", ""), reverse=True)


@app.get("/api/jobs/{job_id}")
def api_get_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    # Refresh output file list if completed
    if job["status"] == "completed":
        outputs_dir = Path(job["outputs_dir"])
        if outputs_dir.is_dir():
            job["output_files"] = sorted(f.name for f in outputs_dir.iterdir() if f.is_file())
    return job


@app.get("/api/jobs/{job_id}/files/{filename}")
def api_get_file(job_id: str, filename: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")

    outputs_dir = Path(job["outputs_dir"]).resolve()
    file_path = (outputs_dir / filename).resolve()

    # Path traversal guard — is_relative_to avoids the startswith prefix-collision flaw
    if not file_path.is_relative_to(outputs_dir):
        raise HTTPException(status_code=400, detail="Nombre de archivo inválido")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    media_type = "application/octet-stream"
    if file_path.suffix.lower() == ".json":
        media_type = "application/json"
    elif file_path.suffix.lower() == ".txt":
        media_type = "text/plain; charset=utf-8"
    elif file_path.suffix.lower() == ".docx":
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    return FileResponse(
        str(file_path),
        media_type=media_type,
        filename=filename,
    )


# ---------------------------------------------------------------------------
# HTML UI
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def ui_upload(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/jobs", response_class=HTMLResponse)
def ui_jobs_list(request: Request):
    jobs_sorted = sorted(
        _jobs.values(), key=lambda j: j.get("created_at", ""), reverse=True
    )
    return templates.TemplateResponse("jobs.html", {"request": request, "jobs": jobs_sorted})


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def ui_job_detail(request: Request, job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")

    outputs_dir = Path(job["outputs_dir"])
    files = []
    if outputs_dir.is_dir():
        for fp in sorted(outputs_dir.iterdir()):
            if not fp.is_file():
                continue
            is_text = fp.suffix.lower() in _TEXT_EXTENSIONS
            preview = None
            if is_text:
                raw = fp.read_bytes()[:_PREVIEW_MAX_BYTES]
                preview = raw.decode("utf-8", errors="replace")
                if fp.suffix.lower() == ".json":
                    try:
                        preview = json.dumps(json.loads(preview), indent=2, ensure_ascii=False)
                    except Exception:
                        pass
            files.append({
                "name": fp.name,
                "size_kb": round(fp.stat().st_size / 1024, 1),
                "is_text": is_text,
                "preview": preview,
            })

    return templates.TemplateResponse(
        "job_detail.html",
        {"request": request, "job": job, "files": files},
    )
