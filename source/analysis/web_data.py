"""Helpers for writing Astro dashboard JSON payloads into web/src/data/."""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np

from source.config.logger import setup_logging

logger = setup_logging(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_DATA_DIR = REPO_ROOT / "web" / "src" / "data"


def sanitize(obj: Any) -> Any:
    """Convert numpy/Decimal/datetime values and replace non-finite floats with None."""
    if obj is None:
        return None
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        value = float(obj)
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(obj, Decimal):
        value = float(obj)
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return sanitize(obj.tolist())
    return obj


def dump_json(path: Path, payload: Any) -> None:
    """Write UTF-8 JSON with NaNs/Infs already sanitized (strict JSON)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = sanitize(payload)
    with path.open("w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, allow_nan=False)
    logger.info("Wrote %s", path)
