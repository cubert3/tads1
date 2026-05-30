# Setup phase & how detection works

## What you must do once (initial phase)

This is **not** training a custom accident model from scratch. One-time setup:

| Step | Command | Purpose |
|------|---------|---------|
| 1 | `python -m venv .venv` | Virtual environment |
| 2 | `Remove-Item Env:SSLKEYLOGFILE` then `pip install -r requirements.txt` | Dependencies (see Windows note below) |
| 3 | `python scripts/download_weights.py` or manual `yolov8n.pt` | YOLO weights (~6 MB) |
| 4 | `pip install lap` | Required for BoT-SORT tracking |
| 5 | Place test video in `data/samples/` | Your footage for demos |
| 6 | `streamlit run dashboard/app.py` or `python scripts/run_video.py --input "..."` | Run pipeline |

**Optional:** CLIP filter (`pip install torch transformers`, enable in `config/settings.yaml`), Tesseract for plates, GPU via `detection.device: cuda`.

On Windows, if `pip` fails with `PermissionError` on `nllMonFltProxy`, run:

```powershell
Remove-Item Env:SSLKEYLOGFILE -ErrorAction SilentlyContinue
```

---

## What is the system “trained on”?

### 1. Vehicle detection — YOLOv8 (pretrained)

- Model: `yolov8n.pt` from Ultralytics
- Trained on **COCO** (general objects: cars, buses, trucks, motorcycles, etc.)
- **Not** trained specifically on Indian accidents or your CCTV footage
- You do **not** need to train this unless you want a custom detector later

### 2. Accident / near-miss — rule engine (not ML classification)

The pipeline does **not** use a neural network that says “this is an accident.” It uses:

- Multi-object **tracking** (BoT-SORT)
- **Motion** (speed drop, trajectory, optical flow)
- **Geometry** (overlap, proximity, approach rate)
- **Confirmation** over several frames + optional **CLIP** image-text filter

So “feeding data” for the core system means: **give it traffic videos** (live or files). It does not require a labeled accident dataset to run.

### 3. Optional CLIP filter

- Pretrained OpenAI CLIP (`clip-vit-base-patch32`)
- Compares frames to text prompts like “car accident on road” vs “normal traffic”
- Still **not** training on your data unless you fine-tune (not in this repo)

### 4. Evaluation script (if you have labels)

If you want to measure precision/recall:

```bash
python scripts/evaluate.py --dir data/samples --labels data/sample_labels.json
```

Example labels:

```json
{
  "your_clip.mp4": true,
  "normal_traffic.mp4": false
}
```

That is the only place you “feed” ground-truth labels — for **metrics**, not for training the detector.

---

## What data should you provide for the hackathon?

| Data | Required? | Use |
|------|-------------|-----|
| Sample crash / near-miss CCTV clips | **Yes (demo)** | Prove detection + dashboard |
| Normal traffic clip | Recommended | Show false-positive control |
| GPS / junction name | Optional | Map pin (config `road_sos.location`) |
| Demo phone numbers | Yes (demo) | `road_sos.dispatch` in settings |
| Custom trained model | **No** for MVP | Rule engine + YOLO is enough |

---

## Has this setup been done in the project?

In the repo:

- `requirements.txt` lists dependencies
- `scripts/download_weights.py` fetches YOLO weights
- `scripts/run_video.py` processes files
- `config/settings.yaml` tunes thresholds
- Dashboard can seed **demo DB rows** (not real video training)

You still need to run steps 1–4 on **your machine** (venv, weights, `lap`, sample video).

---

## Quick test without browser upload

```powershell
.venv\Scripts\python.exe scripts/run_video.py --input "C:\Users\Pranav\Desktop\Pranav\tads\data\samples\YOUR_VIDEO.mp4"
```

Then refresh the dashboard — incidents appear in **Incident registry**.
