from .fanuc import generate_gcode_from_operations as fanuc_postprocess
from .grbl import generate_gcode_from_operations as grbl_postprocess
from .marlin import generate_gcode_from_operations as marlin_postprocess
from .linuxcnc import generate_gcode_from_operations as linuxcnc_postprocess

POSTPROCESSORS = {
    "fanuc": fanuc_postprocess,
    "grbl": grbl_postprocess,
    "marlin": marlin_postprocess,
    "linuxcnc": linuxcnc_postprocess,
}

__all__ = [
    "fanuc_postprocess",
    "grbl_postprocess",
    "marlin_postprocess",
    "linuxcnc_postprocess",
    "POSTPROCESSORS",
]
