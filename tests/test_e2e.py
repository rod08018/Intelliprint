"""`intelliprint new` de extremo a extremo (F1.17 (verificación), marcador `llm`).

Llama a un modelo real y cuesta unos céntimos. Aislado con
INTELLIPRINT_WORKSPACE: nunca toca el workspace/ de verdad.

Los volúmenes esperados están calculados A MANO a partir de la petición:
son un oráculo independiente del sistema, no una salida suya.
"""

import math
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from orchestrator.config import load_env
from tests.test_fcstd_output import _visibilidad_gui
from tests.test_generators import _freecadcmd

INTELLIPRINT = str(Path(sys.executable).parent / "intelliprint")
_env = load_env(Path(".env"))

CASOS = [
    (
        "soporte para NEMA17: placa de 60x60x6 mm con taladro central de 22.4 mm "
        "y cuatro agujeros de 3.3 mm en cuadro de 31 mm",
        60 * 60 * 6 - math.pi * 11.2**2 * 6 - 4 * math.pi * 1.65**2 * 6,
    ),
    (
        "placa de 40x40x5 mm con taladro central de 25 mm",
        40 * 40 * 5 - math.pi * 12.5**2 * 5,
    ),
    (
        "placa de 80x50x4 mm con cuatro agujeros de 4.3 mm en cuadro de 40 mm",
        80 * 50 * 4 - 4 * math.pi * 2.15**2 * 4,
    ),
]


@pytest.mark.llm
@pytest.mark.skipif(not _env.get("DEEPSEEK_API_KEY"), reason="sin DEEPSEEK_API_KEY")
@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
@pytest.mark.parametrize("peticion,volumen", CASOS)
def test_de_la_frase_a_la_pieza(tmp_path, peticion, volumen):
    salida = subprocess.run(
        [INTELLIPRINT, "new", peticion],
        input="sí\n", capture_output=True, text=True, timeout=900,
        env={**os.environ, "INTELLIPRINT_WORKSPACE": str(tmp_path)},
    ).stdout

    medido = float(re.search(r"pieza:\s+([\d.]+) mm³", salida).group(1))
    assert medido == pytest.approx(volumen, abs=1.0), salida

    assert "NO aparecen en la pieza" not in salida  # trazabilidad (F1.16 (trazabilidad))

    proyecto = next((tmp_path / "projects").iterdir())
    fcstd = next(proyecto.glob("parts/*/*.FCStd"))
    assert sum(_visibilidad_gui(fcstd).values()) == 1  # se verá al abrirlo
    assert re.search(r"laminado:\s+([\d.]+) g", salida)
