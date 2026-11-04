"""El bucle de diseño mide los requisitos y entrega el mejor intento
(F6.7 (lazo), F6.8 (mejor)), construyendo de verdad en FreeCAD.

Caja de 20 × 10 × 5. Requisitos: R1, dos agujeros de Ø3 a 10 mm; R2, uno de
Ø5. Volumen de la pieza con solo los dos Ø3, hecho a mano:
1000 − 2·π·1.5²·5 = 929.31 mm³.
"""

import math
from pathlib import Path

import pytest
import yaml

from orchestrator.build import design_and_build
from orchestrator.medida import defectos
from orchestrator.schemas.programa import Programa
from orchestrator.schemas.spec import Requisito
from tests.test_generators import _freecadcmd

pytestmark = pytest.mark.skipif(_freecadcmd() is None, reason="sin freecadcmd")

PERFIL = yaml.safe_load(Path("config/printers/ankermake_m5_plamas.yaml").read_text(encoding="utf-8"))
REQUISITOS = [
    Requisito(id="R1", tipo="agujero", texto="dos agujeros de 3 mm a 10 mm", valor=3,
              origen="usuario", cantidad=2, separaciones_mm=[10]),
    Requisito(id="R2", tipo="agujero", texto="uno de 5 mm", valor=5, origen="usuario"),
]
SIN_AGUJEROS = "def construir(kit):\n    return kit.caja(20, 10, 5)\n"
SOLO_R1 = """
def construir(kit):
    p = kit.caja(20, 10, 5)
    p = p.taladrar("a", 3, en=(5, 5, 5))
    return p.taladrar("b", 3, en=(15, 5, 5))
"""
TODO = SOLO_R1.replace('    return p.taladrar("b", 3, en=(15, 5, 5))',
                       '    p = p.taladrar("b", 3, en=(15, 5, 5))\n'
                       '    return p.taladrar("c", 5, en=(10, 5, 5))')


class Guion:
    def __init__(self, programas):
        self._programas = list(programas)
        self.rechazos = []

    def design(self, brief, rechazo=None):
        self.rechazos.append(rechazo)
        return Programa(part="p", codigo=self._programas.pop(0))


def _disenar(guion, tmp_path):
    return design_and_build(
        guion, "t", None, tmp_path, freecadcmd=_freecadcmd(), part="p", perfil=PERFIL,
        max_construcciones=3, entregar_mejor=True,
        check=lambda r: "\n".join(defectos(REQUISITOS, r.rasgos)) or None)


def test_un_requisito_que_falta_vuelve_al_disenador_y_lo_corrige(tmp_path):
    guion = Guion([SOLO_R1, TODO])
    _, resultado = _disenar(guion, tmp_path)
    assert resultado.defectos == []
    assert "R2" in guion.rechazos[1][1]     # el motivo que recibió


def test_si_nunca_cumple_todo_se_entrega_el_que_menos_falla(tmp_path):
    """El último intento (sin agujeros) es peor que el segundo: lo que queda
    en disco tiene que ser el segundo, no el último."""
    guion = Guion([SIN_AGUJEROS, SOLO_R1, SIN_AGUJEROS])
    receta, resultado = _disenar(guion, tmp_path)
    assert [d[:2] for d in resultado.defectos] == ["R2"]
    assert receta.codigo == SOLO_R1
    assert resultado.volume_mm3 == pytest.approx(1000 - 2 * math.pi * 1.5 ** 2 * 5, abs=0.01)
