"""Debug session logging (NDJSON). Session 73fc72."""

from __future__ import annotations

import json
import time
import traceback
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_LOG_PATHS = [_ROOT / "debug-73fc72.log", _ROOT / "data" / "debug-73fc72.log"]
_SESSION = "73fc72"


def dbg(
    location: str,
    message: str,
    data: dict[str, Any] | None = None,
    hypothesis_id: str = "",
    run_id: str = "pre-fix",
) -> None:
    # #region agent log
    try:
        payload = {
            "sessionId": _SESSION,
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(time.time() * 1000),
        }
        line = json.dumps(payload, default=str) + "\n"
        for path in _LOG_PATHS:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as f:
                    f.write(line)
                    f.flush()
            except Exception:
                pass
    except Exception:
        pass
    # #endregion


def dbg_exc(location: str, exc: BaseException, hypothesis_id: str = "", run_id: str = "pre-fix") -> None:
    dbg(
        location,
        "exception",
        {"type": type(exc).__name__, "msg": str(exc), "tb": traceback.format_exc()[-2000:]},
        hypothesis_id=hypothesis_id,
        run_id=run_id,
    )
