"""Laminado con PrusaSlicer (F1.12 (laminado) + F1.13 (slicing)).

El laminado de una pieza no necesita un LLM: es una llamada determinista
a PrusaSlicer y leer las estadísticas que deja en el G-code. El "Slicing
Agent" solo tendrá trabajo de verdad cuando haya que agrupar varias piezas
en placas (F3.13 (placas)).
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

from orchestrator.schemas.slicing_report import SlicingReport

PERFIL_M5 = Path("config/slicing/ankermake_m5_petg.ini")

_MACOS = "/Applications/PrusaSlicer.app/Contents/MacOS/PrusaSlicer"


class LaminadoFallido(RuntimeError):
    """PrusaSlicer no produjo un G-code utilizable."""


def prusaslicer() -> str | None:
    ruta = (
        os.environ.get("PRUSASLICER")
        or shutil.which("prusa-slicer")
        or (_MACOS if Path(_MACOS).exists() else None)
    )
    return ruta


def parse_tiempo(texto: str) -> int:
    """'1d 2h 3m 4s' → segundos. PrusaSlicer omite las unidades que valen 0."""
    unidades = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    return sum(int(n) * unidades[u] for n, u in re.findall(r"(\d+)([dhms])", texto))


def _dato(gcode: str, patron: str) -> str | None:
    m = re.search(patron, gcode, re.MULTILINE)
    return m.group(1).strip() if m else None


def slice_stl(stl: Path, perfil: Path, salida: Path) -> SlicingReport:
    ejecutable = prusaslicer()
    if ejecutable is None:
        raise LaminadoFallido("PrusaSlicer no encontrado (define PRUSASLICER)")
    if not Path(perfil).exists():
        raise LaminadoFallido(f"perfil de laminado inexistente: {perfil}")

    proceso = subprocess.run(
        [ejecutable, "--load", str(perfil), "--export-gcode",
         "--output", str(salida), str(stl)],
        capture_output=True, text=True, timeout=600,
    )
    if proceso.returncode != 0 or not Path(salida).exists():
        raise LaminadoFallido(
            f"PrusaSlicer falló (código {proceso.returncode}):\n{proceso.stderr[-800:]}"
        )

    gcode = Path(salida).read_text(encoding="utf-8", errors="ignore")
    filamento = _dato(gcode, r"^; filament used \[mm\] = ([\d.]+)")
    gramos = _dato(gcode, r"^; total filament used \[g\] = ([\d.]+)") or _dato(
        gcode, r"^; filament used \[g\] = ([\d.]+)"
    )
    tiempo = _dato(gcode, r"^; estimated printing time \(normal mode\) = (.+)$")
    soportes = _dato(gcode, r"^; support_material = (\d)")

    if filamento is None or gramos is None or tiempo is None:
        raise LaminadoFallido("el G-code no trae las estadísticas esperadas")

    # SlicingReport rechaza 0 g con filamento gastado: si el perfil no
    # tuviera densidad, el fallo saltaría aquí y no en el resumen del gate.
    return SlicingReport(
        plate=1,
        filament_mm=float(filamento),
        grams=float(gramos),
        time_s=parse_tiempo(tiempo),
        needs_supports=soportes == "1",
        parts=[Path(stl).stem],
    )
