# TADS — Traffic Accident Detection System

AI-based road accident detection using **integration over invention**: pretrained YOLOv8, BoT-SORT tracking, multi-signal rule engine, near-miss detection, optional CLIP false-positive filter, evidence capture, FastAPI + Streamlit dashboard.

## Features

- Vehicle detection (YOLOv8 COCO pretrained)
- Multi-object tracking (BoT-SORT / ByteTrack / StrongSORT)
- Motion analysis (trajectory, velocity, Farneback optical flow)
- Collision + **near-miss** detection via composite scoring
- Incident state machine (`CANDIDATE → CONFIRMED → ARCHIVED`)
- Optional CLIP zero-shot false-positive filter
- Evidence clips (rolling pre/post buffer)
- Annotated demo video output
- SQLite incident persistence
- FastAPI REST + SSE alerts
- Streamlit review dashboard
- **Road SOS**: human confirm toggle, severity routing (police/ambulance), cooldown map, dispatch log, optional plate OCR

## Road SOS dashboard

```bash
streamlit run dashboard/app.py
```

Mission-critical UI (IBM Plex typography, restrained palette): **Live operations** · **Upload & test lab** · **Incidents** · **Dispatch log** · **Cameras & health** · **Analytics**. Styles live in `dashboard/theme.py`.

Configure demo phones and routing in [`config/settings.yaml`](config/settings.yaml) under `road_sos`.

Optional plate OCR: install [Tesseract](https://github.com/tesseract-ocr/tesseract) and `pip install pytesseract`.

## Setup & training (read this first)

**You do not train a custom accident model for the MVP.** See [docs/SETUP_AND_TRAINING.md](docs/SETUP_AND_TRAINING.md) for the one-time setup phase, what YOLO was trained on, and what data you actually need to provide.

## Quick start

```powershell
cd C:\Users\Pranav\Desktop\Pranav\tads
.\scripts\install_deps.ps1
```

This installs **all** Python deps (tracking, API, dashboard, torch, CLIP, plate OCR wrapper), verifies imports, and downloads `yolov8n.pt` if missing.

Manual check: `.venv\Scripts\python.exe scripts\verify_deps.py`

**Windows:** If `pip` fails with `SSLKEYLOGFILE` / `nllMonFltProxy`, run `Remove-Item Env:SSLKEYLOGFILE` first (the install script does this).

**Plates:** `pytesseract` is installed; also install the [Tesseract binary](https://github.com/UB-Mannheim/tesseract/wiki) for OCR to work.

### Process a video (CLI)

```bash
python scripts/run_video.py --input path/to/traffic.mp4
```

Outputs:
- `output/annotated/annotated_traffic.mp4` — full annotated demo video
- `data/incidents/{uuid}.mp4` — evidence clips per incident
- `data/incidents.db` — SQLite incident log

### Start API server

```bash
uvicorn api.server:app --reload --host 0.0.0.0 --port 8000
```

Endpoints:
- `POST /api/videos/upload` — upload video
- `POST /api/videos/{id}/process` — run pipeline
- `GET /api/jobs/{id}/status` — job progress
- `GET /api/incidents` — list incidents
- `GET /api/incidents/{id}/clip` — stream evidence
- `GET /api/stream/alerts` — SSE live alerts

### Dashboard

```bash
streamlit run dashboard/app.py
```

### Live webcam / RTSP

```bash
python scripts/run_live.py --camera 0
python scripts/run_live.py --rtsp rtsp://user:pass@camera/stream
```

## Configuration

Edit [`config/settings.yaml`](config/settings.yaml):

| Section | Key settings |
|---------|-------------|
| `detection` | model, conf, device |
| `tracking` | backend: `botsort`, `bytetrack`, `strongsort` |
| `near_miss` | proximity_px, approach_rate_min |
| `collision` | iou_threshold, decel_threshold, confirm_frames |
| `clip_filter` | enabled (requires torch + transformers) |
| `calibration` | meters_per_pixel, reference_points |
| `evidence` | pre_seconds, post_seconds |
| `alerts` | webhook_url |
| `road_sos` | human_confirm, plate_detection, location, dispatch numbers, severity_routing |

### API (Road SOS)

- `GET/PATCH /api/road-sos/settings` — human confirm toggle
- `POST /api/incidents/{id}/confirm` — approve pending incident and dispatch
- `POST /api/incidents/{id}/dismiss` — false positive
- `GET /api/dispatch/log` — dispatch history
- `GET /api/cooldown/map` — active cooldown zones

## Evaluation

Create a labels JSON and run:

```bash
python scripts/evaluate.py --dir data/samples --labels data/sample_labels.json
```

Example `sample_labels.json`:
```json
{
  "crash_clip.mp4": true,
  "normal_traffic.mp4": false
}
```

## Project structure

```
tads/
├── core/           # detector, tracker, motion, collision, near_miss, performance, processor
├── media/          # Video reader, evidence writer, alerter
├── storage/        # SQLite incident store
├── api/            # FastAPI server
├── dashboard/      # Streamlit UI
├── config/         # settings.yaml
├── scripts/        # CLI tools
├── tests/          # Unit tests
├── data/           # samples + incidents (gitignored content)
└── output/         # Annotated videos
```

## Architecture

```
Video → YOLOv8 → BoT-SORT → Motion/Flow → Collision Scorer → State Machine → CLIP (optional) → Alert + Evidence
```

## Optional: enable CLIP filter

```bash
pip install torch transformers
```

Set `clip_filter.enabled: true` in `config/settings.yaml`.

### Performance estimate

```bash
python scripts/estimate_performance.py
python scripts/estimate_performance.py --width 1920 --height 1080 --fps 30
```

### Sample video setup

```bash
python scripts/download_samples.py
```

Then add `.mp4` files to `data/samples/` per the printed manifest.

## Tests

```bash
pytest tests/ -v
pytest tests/ -v -m "not slow"   # skip YOLO inference test if no weights
```

## Limitations

- Best on fixed CCTV angles; use BoT-SORT for PTZ cameras
- Rule engine may false-positive on merges / traffic stops — tune thresholds + enable CLIP
- Night/rain reduces YOLO recall
- Demo system — not certified for emergency dispatch

## License

MIT
