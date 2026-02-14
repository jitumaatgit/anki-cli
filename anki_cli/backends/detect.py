from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

import httpx

BackendName = Literal["ankiconnect", "direct", "standalone"]
DEFAULT_ANKICONNECT_URL: Final[str] = "http://localhost:8765"
DEFAULT_ANKICONNECT_TIMEOUT_S: Final[float] = 0.35

class DetectionError(RuntimeError):
    def __init__(self, message: str, *, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code

@dataclass(frozen=True, slots=True)
class DetectionResult:
    backend: BackendName
    collection_path: Path | None
    reason: str

def detect_backend(
    *,
    forced_backend: str = "auto",
    col_override: Path | None = None,
    ankiconnect_url: str = DEFAULT_ANKICONNECT_URL,
) -> DetectionResult:
    forced = forced_backend.strip().lower()

    if forced not in {"auto", "ankiconnect", "direct", "standalone"}:
        raise DetectionError(
            f"Unsupported backend '{forced_backend}'. Expected auto|ankiconnect|direct|standalone.",
            exit_code=2
        )

    if forced == "ankiconnect":
        if not _ankiconnect_reachable(ankiconnect_url):
            raise DetectionError(
                "AnkiConnect backend forced, but it is not reachable at localhost:8765.",
                exit_code=7
            )
        return DetectionResult(
            "ankiconnect", 
            _resolve_direct_collection(col_override),
            "forced"
        )

    if forced == "direct":
        path = _resolve_direct_collection(col_override)
        if path is None:
            raise DetectionError(
                "Direct backend forced, but no Anki collection.anki21b was found.",
                exit_code=3
            )
        if _anki_process_running() or _sqlite_write_locked(path):
            raise DetectionError(
                "Anki appears to be running while AnkiConnect is unavailable. "
                "Install AnkiConnect or close Anki Desktop before direct writes.",
                exit_code=7,
            )
        return DetectionResult("direct", path, "forced")

    if forced == "standalone":
        return DetectionResult(
            "standalone",
            _resolve_standalone_collection(col_override),
            "forced"
        )

    if _ankiconnect_reachable(ankiconnect_url):
        return DetectionResult(
            "ankiconnect",
            _resolve_direct_collection(col_override),
            "ankiconnect reachable"
        )

    direct_path = _resolve_direct_collection(col_override)
    if direct_path is not None:
        if _anki_process_running() or _sqlite_write_locked(direct_path):
            raise DetectionError(
                "Anki is running but AnkiConnect is unavailable. "
                "Install AnkiConnect or close Anki Desktop.",
                exit_code=7,
            )
        return DetectionResult(
            "direct",
            direct_path,
            "ankiconnect unavailable, direct collection found"
        )

    return DetectionResult(
        "standalone",
        _resolve_standalone_collection(col_override),
        "no ankiconnect and no direct collection found",
    )

def _ankiconnect_reachable(url: str) -> bool:
    payload = {"action": "version", "version": 6}
    try:
        with httpx.Client(timeout=DEFAULT_ANKICONNECT_TIMEOUT_S) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError):
        return False
    return isinstance(data, dict) and data.get("error") is None and "result" in data

def _resolve_direct_collection(col_override: Path | None) -> Path | None:
    if col_override is not None:
        resolved = col_override.expanduser().resolve()
        return resolved if resolved.exists() else None

    anki_home = Path.home() / ".local" / "share" / "Anki2"
    if not anki_home.exists():
        return None

    candidates: list[Path] = []
    for profile_dir in sorted(anki_home.iterdir()):
        if not profile_dir.is_dir():
            continue
        db_path = profile_dir / "collection.anki21b"
        if db_path.exists():
            candidates.append(db_path)

    return candidates[0] if candidates else None


def _resolve_standalone_collection(col_override: Path | None) -> Path:
    if col_override is not None:
        return col_override.expanduser().resolve()

    cwd = Path.cwd().resolve()
    for base in (cwd, *cwd.parents):
        candidate = base / ".anki-cli" / "collection.db"
        if candidate.exists():
            return candidate

    return (Path.home() / ".local" / "share" / "anki-cli" / "collection.db").resolve()


def _anki_process_running() -> bool:
    proc_root = Path("/proc")
    if not proc_root.exists():
        return False

    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue

        comm = entry / "comm"
        cmdline = entry / "cmdline"

        try:
            if comm.exists():
                name = comm.read_text(encoding="utf-8", errors="ignore").strip().lower()
                if "anki" in name:
                    return True

            if cmdline.exists():
                raw = cmdline.read_bytes()
                text = raw.replace(b"\x00", b" ").decode("utf-8", errors="ignore").lower()
                if "anki" in text:
                    return True
        except OSError:
            continue

    return False


def _sqlite_write_locked(db_path: Path) -> bool:
    if not db_path.exists():
        return False

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=rw", uri=True, timeout=0.05)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("ROLLBACK")
        return False
    except sqlite3.OperationalError as exc:
        return "locked" in str(exc).lower() or "busy" in str(exc).lower()
    finally:
        if conn is not None:
            conn.close()