"""Filename / path safety helpers."""

import mimetypes
import re
import uuid
from pathlib import Path

MAX_NAME_LEN = 180

# Extensions that would be dangerous to serve back or that we simply refuse.
BLOCKED_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".com", ".scr", ".msi", ".dll",
    ".sh", ".ps1", ".vbs", ".jar", ".app",
}

_UNSAFE = re.compile(r"[^A-Za-z0-9._ ()\-]")


def sanitize_display_name(name: str) -> str:
    """Clean a user supplied name so it is safe to store and echo back.

    Only the basename is kept, so `../../etc/passwd` becomes `passwd`.
    """
    name = (name or "").replace("\\", "/").split("/")[-1].strip()
    name = name.replace("\x00", "")
    name = _UNSAFE.sub("_", name)
    name = name.lstrip(".") or "untitled"
    if len(name) > MAX_NAME_LEN:
        stem, dot, ext = name.rpartition(".")
        name = (stem[: MAX_NAME_LEN - len(ext) - 1] + dot + ext) if dot else name[:MAX_NAME_LEN]
    return name


def extension_of(name: str) -> str:
    ext = Path(name).suffix.lower()
    return ext if len(ext) <= 12 else ""


def is_blocked(name: str) -> bool:
    return extension_of(name) in BLOCKED_EXTENSIONS


def generate_stored_name(original_name: str) -> str:
    """Never trust the original name on disk: use a UUID plus the extension."""
    return f"{uuid.uuid4().hex}{extension_of(original_name)}"


def guess_mime(name: str, fallback: str | None = None) -> str:
    guessed, _ = mimetypes.guess_type(name)
    return guessed or fallback or "application/octet-stream"


def ensure_within(base: Path, target: Path) -> Path:
    """Raise if `target` escapes `base` (path traversal guard)."""
    base = base.resolve()
    resolved = (base / target).resolve() if not target.is_absolute() else target.resolve()
    if base != resolved and base not in resolved.parents:
        raise ValueError("Resolved path escapes the storage root")
    return resolved


def bytes_to_mb(value: int | float) -> float:
    return round(float(value) / (1024 * 1024), 6)


def mb_to_bytes(value: int | float) -> int:
    return int(float(value) * 1024 * 1024)


def human_size(num_bytes: int | float) -> str:
    num = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"
