"""Resultado de construir una pieza.

Lo produce `build.py` al final de su ejecución en `freecadcmd` (§ 9.3) y
lo lee el orquestador desde stdout.
"""

import pytest

from orchestrator.recipes.compose import RESULT_PREFIX
from orchestrator.schemas.part_result import BuildOutputError, PartResult

_SALIDA_FREECAD = f"""\
FreeCAD 1.1.3, Libs: 1.1.3R
(C) 2001-2026 FreeCAD contributors
Recompute......
\t\t\t\t\t\t(100 %)
{RESULT_PREFIX}{{"part": "cubo", "volume_mm3": 7999.999999999998, \
"bbox_mm": [20.0, 20.0, 20.0], "solids": 1}}
"""


def test_extrae_el_resultado_de_entre_el_ruido_de_freecad():
    """FreeCAD escribe banner y barras de progreso en el mismo stdout.

    Por eso la línea de resultado va marcada con un prefijo: buscarla por
    posición o parsear todo el stdout como JSON sería frágil.
    """
    resultado = PartResult.from_build_output("cubo", _SALIDA_FREECAD)

    assert resultado.volume_mm3 == pytest.approx(8000.0, rel=1e-6)
    assert resultado.bbox_mm == [20.0, 20.0, 20.0]
    assert resultado.solids == 1


def test_sin_linea_de_resultado_falla_ruidosamente():
    """Un build que revienta a mitad no puede pasar por pieza construida.

    `freecadcmd` puede terminar con código 0 habiendo fallado antes del
    final del script. Si no exigimos la línea de resultado, una pieza rota
    entraría al QA como si se hubiera construido bien.
    """
    salida_truncada = "FreeCAD 1.1.3\nRecompute......\n"

    with pytest.raises(BuildOutputError, match="no emitió línea de resultado"):
        PartResult.from_build_output("cubo", salida_truncada)
