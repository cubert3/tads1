from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.config import get_settings
from core.processor import AccidentDetectionProcessor, ProcessingResult
from media.alerter import Alerter
from media.video_reader import VideoSource
from storage.incident_store import IncidentStore
from storage.runtime_settings import human_confirm_enabled, load_runtime, set_human_confirm_enabled

settings = get_settings()
app = FastAPI(title="Road SOS — Traffic Accident Detection", version="2.0.0")
alerter = Alerter(settings.alerts)
store = IncidentStore(settings.resolve_path(settings.paths.database_path))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = settings.resolve_path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

jobs: dict[str, dict] = {}


class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: float = 0.0
    fps: float = 0.0
    incidents: int = 0
    annotated_path: str | None = None
    error: str | None = None


class RoadSosSettingsUpdate(BaseModel):
    human_confirm_enabled: bool | None = None


def _make_processor(on_progress=None) -> AccidentDetectionProcessor:
    return AccidentDetectionProcessor(settings=settings, alerter=alerter, on_progress=on_progress)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "road-sos", "human_confirm": human_confirm_enabled()}


@app.get("/api/road-sos/settings")
async def get_road_sos_settings():
    road = settings.road_sos
    return {
        "human_confirm_enabled": human_confirm_enabled(road.human_confirm_enabled),
        "plate_detection_enabled": road.plate_detection_enabled,
        "location": road.location.model_dump(),
        "dispatch": road.dispatch.model_dump(),
        "severity_routing": road.severity_routing.model_dump(),
        "runtime": load_runtime(),
    }


@app.patch("/api/road-sos/settings")
async def patch_road_sos_settings(body: RoadSosSettingsUpdate):
    if body.human_confirm_enabled is not None:
        set_human_confirm_enabled(body.human_confirm_enabled)
    return await get_road_sos_settings()


@app.post("/api/videos/upload")
async def upload_video(file: UploadFile = File(...)):
    video_id = str(uuid.uuid4())
    dest = UPLOAD_DIR / f"{video_id}_{file.filename}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"video_id": video_id, "path": str(dest), "filename": file.filename}


def _run_job(job_id: str, video_path: Path) -> None:
    jobs[job_id]["status"] = "processing"

    def on_progress(current: int, total: int, fps: float) -> None:
        jobs[job_id]["progress"] = current / max(total, 1)
        jobs[job_id]["fps"] = fps

    try:
        processor = _make_processor(on_progress=on_progress)
        result = processor.process_source(VideoSource.from_file(video_path), output_name=f"{job_id}_annotated.mp4")

        async def persist():
            for inc in result.incidents:
                inc.source_video = str(video_path)
                await store.save(inc)

        asyncio.run(persist())

        jobs[job_id].update({
            "status": "completed",
            "progress": 1.0,
            "fps": result.fps_avg,
            "incidents": len(result.incidents),
            "annotated_path": str(result.annotated_path) if result.annotated_path else None,
            "result": {
                "source": result.source,
                "frames_processed": result.frames_processed,
                "incidents": [
                    {
                        "id": i.id,
                        "severity": i.severity,
                        "score": i.score,
                        "timestamp_sec": i.timestamp_sec,
                        "state": i.state.value,
                        "dispatch_status": i.dispatch_status,
                    }
                    for i in result.incidents
                ],
            },
        })
    except Exception as exc:
        jobs[job_id].update({"status": "failed", "error": str(exc)})


@app.post("/api/videos/{video_id}/process")
async def process_video(video_id: str, background_tasks: BackgroundTasks):
    matches = list(UPLOAD_DIR.glob(f"{video_id}_*"))
    if not matches:
        raise HTTPException(404, "Video not found")
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"job_id": job_id, "status": "queued", "progress": 0.0, "fps": 0.0, "incidents": 0}
    background_tasks.add_task(_run_job, job_id, matches[0])
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}/status", response_model=JobStatus)
async def job_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    return JobStatus(job_id=job_id, **{k: v for k, v in jobs[job_id].items() if k != "result"})


@app.get("/api/incidents")
async def list_incidents(severity: str | None = None, state: str | None = None):
    return await store.list_all(severity=severity, state=state)


@app.get("/api/incidents/{incident_id}")
async def get_incident(incident_id: str):
    item = await store.get(incident_id)
    if not item:
        raise HTTPException(404, "Incident not found")
    return item


@app.post("/api/incidents/{incident_id}/confirm")
async def confirm_incident(incident_id: str):
    processor = _make_processor()
    record = await processor.approve_and_dispatch(incident_id)
    if not record:
        raise HTTPException(404, "Incident not pending review")
    return {"status": "confirmed", "incident": record.id, "dispatch_status": record.dispatch_status}


@app.post("/api/incidents/{incident_id}/dismiss")
async def dismiss_incident(incident_id: str):
    processor = _make_processor()
    ok = await processor.dismiss_incident(incident_id)
    if not ok:
        raise HTTPException(404, "Incident not found")
    return {"status": "dismissed", "incident_id": incident_id}


@app.get("/api/incidents/{incident_id}/clip")
async def get_incident_clip(incident_id: str):
    clip = settings.resolve_path(settings.paths.incidents_dir) / f"{incident_id}.mp4"
    if not clip.exists():
        raise HTTPException(404, "Clip not found")
    return FileResponse(clip, media_type="video/mp4")


@app.get("/api/dispatch/log")
async def dispatch_log(limit: int = 100):
    return await store.list_dispatch_log(limit=limit)


@app.get("/api/cooldown/map")
async def cooldown_map():
    zones = await store.list_cooldown_zones()
    active = _make_processor().cooldown_tracker.active_zones()
    for zone in active:
        zones.append({
            "x": zone.x,
            "y": zone.y,
            "radius_px": zone.radius_px,
            "reason": zone.reason,
            "incident_id": zone.incident_id,
            "created_at": zone.created_at,
            "expires_at": zone.expires_at,
        })
    return {"zones": zones, "cooldown_seconds": settings.collision.cooldown_seconds}


@app.get("/api/analytics/summary")
async def analytics_summary():
    return await store.analytics_summary()


@app.get("/api/output/{job_id}/annotated")
async def get_annotated(job_id: str):
    job = jobs.get(job_id)
    if not job or not job.get("annotated_path"):
        raise HTTPException(404, "Annotated video not found")
    path = Path(job["annotated_path"])
    if not path.exists():
        raise HTTPException(404, "File missing")
    return FileResponse(path, media_type="video/mp4")


@app.get("/api/stream/alerts")
async def stream_alerts():
    queue = alerter.subscribe()

    async def event_generator():
        while True:
            payload = await queue.get()
            yield f"data: {json.dumps(payload)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


static_dir = settings.resolve_path("web/static")
templates_dir = settings.resolve_path("web/templates")
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = templates_dir / "index.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<h1>Road SOS API running</h1><p>See /docs</p>"
