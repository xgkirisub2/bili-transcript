"""Shared paths, HTTP headers and credential persistence."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# All mutable state (cookies, QR artifacts, transcripts) lives outside the
# repository so the tool can be installed globally with `uv tool install`.
HOME = Path(
    os.environ.get("BILI_TRANSCRIPT_HOME", str(Path.home() / ".bili-transcript"))
).expanduser()
CONFIG_DIR = HOME / "config"
DATA_DIR = HOME / "data"
CREDENTIALS_PATH = CONFIG_DIR / "credentials.json"
QR_PNG_PATH = CONFIG_DIR / "login_qr.png"
QR_PENDING_PATH = CONFIG_DIR / "qr_pending.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36"
)
BASE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Referer": "https://www.bilibili.com/",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

CREDENTIAL_FIELDS = ("sessdata", "bili_jct", "buvid3", "buvid4", "dedeuserid", "ac_time_value")

# Locked-in defaults from the 2026-10-21 benchmark:
# - large-v3-turbo on CUDA is ~36x realtime on the RTX 4070 Ti;
# - stream 30216 (~66 kbps) downloaded in ~1.1s while 30232 was slow/unstable;
# - audio is deleted after ASR to keep per-video storage at ~0.2 MB.
DEFAULT_MODEL = "large-v3-turbo"
DEFAULT_DEVICE = "auto"
DEFAULT_LANGUAGE = "zh"
DEFAULT_KEEP_AUDIO = False
AUDIO_STREAM_PRIORITY = (30216, 30232, 30280, 30250, 30251)


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def setup_stdio() -> None:
    """Force UTF-8 console output on Windows."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def load_credentials() -> dict[str, Any] | None:
    if not CREDENTIALS_PATH.exists():
        return None
    try:
        data = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not data.get("sessdata"):
        return None
    return data


def save_credentials(data: dict[str, Any]) -> None:
    ensure_dirs()
    payload = {field: str(data.get(field) or "") for field in CREDENTIAL_FIELDS}
    payload["saved_at"] = datetime.now().isoformat(timespec="seconds")
    CREDENTIALS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def to_credential(data: dict[str, Any]):
    from bilibili_api.utils.network import Credential

    return Credential(
        sessdata=data.get("sessdata") or None,
        bili_jct=data.get("bili_jct") or None,
        buvid3=data.get("buvid3") or None,
        buvid4=data.get("buvid4") or None,
        dedeuserid=data.get("dedeuserid") or None,
        ac_time_value=data.get("ac_time_value") or None,
    )


def get_credential():
    data = load_credentials()
    return to_credential(data) if data else None
