"""Input tools — helpers for parsing and enriching user requests."""

from cnc.schemas.job_spec import JobSpec, MachineType


def extract_job_spec_from_text(text: str) -> dict:
    """Lightly parse natural language into a partial JobSpec dict.

    This is a heuristic pre-filter only — the DeepAgent does the real parsing.
    Returns a dict matching JobSpec fields where detectable.
    """
    lower = text.lower()
    machine_type: MachineType | None = None

    if any(w in lower for w in ("mill", "milling", "pocket", "contour", "face mill")):
        machine_type = "mill"
    elif any(w in lower for w in ("lathe", "turning", "turn")):
        machine_type = "lathe"
    elif any(w in lower for w in ("laser", "engrave", "cut laser")):
        machine_type = "laser"
    elif any(w in lower for w in ("drill", "drilling", "hole")):
        machine_type = "drill"
    elif any(w in lower for w in ("3d print", "fdm", "filament", "extrud")):
        machine_type = "3d_printer"
    elif any(w in lower for w in ("grind", "grinding")):
        machine_type = "grinder"

    units = "inch" if any(w in lower for w in ("inch", "inches", '"', "imperial")) else "mm"

    return {
        "machine_type": machine_type,
        "units": units,
        "description": text,
    }
