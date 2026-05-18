"""File tools — safe local file read/write for G-code programs."""

from pathlib import Path


_ALLOWED_EXTENSIONS = {".nc", ".gcode", ".ngc", ".tap", ".cnc", ".txt"}


def save_gcode(gcode: str, output_path: str) -> dict:
    """Save G-code to a local file.

    Only writes to paths with approved extensions. No absolute paths outside CWD.
    """
    path = Path(output_path)
    if path.is_absolute():
        return {"ok": False, "error": "Absolute paths are not allowed. Use relative paths."}
    if path.suffix.lower() not in _ALLOWED_EXTENSIONS:
        return {
            "ok": False,
            "error": f"Extension '{path.suffix}' not allowed. Use: {sorted(_ALLOWED_EXTENSIONS)}",
        }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(gcode, encoding="utf-8")
        return {"ok": True, "path": str(path)}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}


def load_gcode(input_path: str) -> dict:
    """Load G-code from a local file."""
    path = Path(input_path)
    if path.is_absolute():
        return {"ok": False, "error": "Absolute paths are not allowed."}
    try:
        content = path.read_text(encoding="utf-8")
        return {"ok": True, "gcode": content, "path": str(path)}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
