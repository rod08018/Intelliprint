"""Mide el criterio de F1.10 (designer): soporte NEMA17 correcto en ≥ 4 de 5 intentos.

Ciclo completo y real: el agente emite la receta, el orquestador compone
`build.py`, FreeCAD lo ejecuta sin GUI, y se comprueba el VOLUMEN del
sólido contra el calculado a mano. No vale con que la receta "parezca
bien": si se equivoca de radio o no perfora, el volumen no cuadra.

    .venv/bin/python scripts/eval_part_designer.py [n]

Con el perfil `dev` esto mide DeepSeek, no `qwen3.8` (ADR-007b).
"""

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp" / "mech-toolkit"))

from mech_toolkit.generators import CATALOGO  # noqa: E402
from orchestrator.agents.part_designer import PartDesignerAgent  # noqa: E402
from orchestrator.llm.providers.deepseek import DeepSeekClient  # noqa: E402
from orchestrator.recipes.compose import RESULT_PREFIX, compose_build_script  # noqa: E402

TAREA = """\
Pieza: `soporte_nema17`.

Placa de 60 x 60 mm y 6 mm de espesor. Lleva un taladro central de 22 mm
de diámetro para el saliente del motor, y cuatro agujeros de 3.3 mm de
diámetro dispuestos en un cuadrado de 31 mm de lado para los tornillos M3
de la brida del NEMA17.
"""

VOLUMEN_ESPERADO = 60 * 60 * 6 - math.pi * 11**2 * 6 - 4 * math.pi * 1.65**2 * 6
BBOX_ESPERADA = [60.0, 60.0, 6.0]


def _freecadcmd() -> str:
    ruta = (
        os.environ.get("FREECADCMD")
        or shutil.which("freecadcmd")
        or "/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd"
    )
    if not Path(ruta).exists():
        raise SystemExit(f"freecadcmd no encontrado en {ruta}")
    return ruta


def _clave() -> str:
    for linea in Path(".env").read_text(encoding="utf-8").splitlines():
        if linea.startswith("DEEPSEEK_API_KEY="):
            return linea.split("=", 1)[1].strip()
    raise SystemExit("DEEPSEEK_API_KEY vacía en .env")


class ClienteVariado:
    def __init__(self, base: DeepSeekClient) -> None:
        self._base = base

    def complete(self, prompt: str) -> str:
        return self._base.complete(prompt, temperature=0.7)


def _construir(receta, freecad: str) -> dict | None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        (out / "build.py").write_text(
            compose_build_script(receta, CATALOGO, output_dir=out), encoding="utf-8"
        )
        proceso = subprocess.run(
            [freecad, str(out / "build.py")],
            capture_output=True,
            text=True,
            timeout=180,
        )
        for linea in proceso.stdout.splitlines():
            if linea.startswith(RESULT_PREFIX):
                return json.loads(linea[len(RESULT_PREFIX) :])
        return None


def main(n: int = 5) -> None:
    freecad = _freecadcmd()
    agente = PartDesignerAgent(ClienteVariado(DeepSeekClient(api_key=_clave())), CATALOGO)
    correctos = 0

    for i in range(1, n + 1):
        try:
            receta = agente.design(TAREA)
        except Exception as e:
            print(f"{i}. RECETA INVÁLIDA  {type(e).__name__}: {str(e)[:80]}")
            continue

        resultado = _construir(receta, freecad)
        if resultado is None:
            print(f"{i}. NO CONSTRUYE     ({len(receta.steps)} pasos)")
            continue

        vol_ok = abs(resultado["volume_mm3"] - VOLUMEN_ESPERADO) < 1.0
        bbox_ok = all(
            abs(a - b) < 0.01 for a, b in zip(resultado["bbox_mm"], BBOX_ESPERADA)
        )
        correctos += vol_ok and bbox_ok
        estado = "OK " if (vol_ok and bbox_ok) else "MAL"
        print(
            f"{i}. {estado}  vol={resultado['volume_mm3']:9.2f} "
            f"(esperado {VOLUMEN_ESPERADO:.2f})  bbox={resultado['bbox_mm']}  "
            f"pasos={[p.generator.replace('generate_', '') for p in receta.steps]}"
        )

    print(f"\nCorrectos: {correctos}/{n}   (criterio F1.10 (designer): ≥ 4/5)")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
