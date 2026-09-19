"""Demo del pipeline que existe hoy: petición → spec → receta → pieza real.

    .venv/bin/python scripts/demo.py "lo que quieres diseñar"

Recorre la arquitectura de verdad: el Requirements Agent clasifica, la
barrera de admisión te pide confirmación por el `HumanPort`, el Part
Designer emite una receta validada contra el catálogo, el orquestador
compone `build.py` y FreeCAD lo ejecuta sin interfaz.

Lo que AÚN NO hace, y por qué:
  - No lamina: falta el perfil de PrusaSlicer (F1.12) y su agente (F1.13).
  - No pasa QA: falta el puente aserción↔medición (F2.13).
  - No usa Telegram: el adaptador es F5.6, semana 16.
  - No es el grafo de LangGraph (F1.14): aquí los pasos van en línea.
"""

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "mcp" / "mech-toolkit"))

from mech_toolkit.generators import CATALOGO  # noqa: E402
from orchestrator.agents.part_designer import PartDesignerAgent  # noqa: E402
from orchestrator.agents.requirements import RequirementsAgent  # noqa: E402
from orchestrator.human.adapters.cli import CliAdapter  # noqa: E402
from orchestrator.human.port import Question  # noqa: E402
from orchestrator.llm.providers.deepseek import DeepSeekClient  # noqa: E402
from orchestrator.recipes.compose import RESULT_PREFIX, compose_build_script  # noqa: E402
from orchestrator.schemas.part_result import PartResult  # noqa: E402
from orchestrator.state_machine import AprobacionRequerida, advance  # noqa: E402
from orchestrator.tasks import slug, spec_to_task  # noqa: E402


def _clave() -> str:
    for linea in (RAIZ / ".env").read_text(encoding="utf-8").splitlines():
        if linea.startswith("DEEPSEEK_API_KEY="):
            valor = linea.split("=", 1)[1].strip()
            if valor:
                return valor
    raise SystemExit("DEEPSEEK_API_KEY vacía en .env")


def _freecadcmd() -> str:
    ruta = (
        os.environ.get("FREECADCMD")
        or shutil.which("freecadcmd")
        or "/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd"
    )
    if not Path(ruta).exists():
        raise SystemExit(f"freecadcmd no encontrado en {ruta}")
    return ruta


def _nombre() -> str:
    for linea in (RAIZ / ".env").read_text(encoding="utf-8").splitlines():
        if linea.startswith("AGENT_NAME="):
            return linea.split("=", 1)[1].strip() or "Crafty"
    return "Crafty"


def main(peticion: str) -> None:
    port = CliAdapter()
    cliente = DeepSeekClient(api_key=_clave())
    yo = _nombre()

    # --- FASE 0 · Admisión ---------------------------------------------------
    port.notify(f"[{yo}] Leyendo la petición…")
    spec = RequirementsAgent(cliente).draft(peticion)

    resumen = (
        f"\n  título:     {spec.title}"
        f"\n  clase:      {spec.product_class}"
        f"\n  material:   {spec.material} en {spec.printer}"
        f"\n  descripción: {spec.description}"
    )
    if spec.payload_g is not None:
        resumen += f"\n  carga:      {spec.payload_g:g} g"
    if spec.reach_mm is not None:
        resumen += f"\n  alcance:    {spec.reach_mm:g} mm"

    estado = "INTAKE"
    try:
        estado = advance(estado, "SPEC_READY", port=port, resumen=resumen)
    except AprobacionRequerida:
        port.notify("\nNo confirmado. El proyecto se queda en INTAKE, sin gastar GPU.")
        return

    # --- Proyecto en disco ---------------------------------------------------
    hoy = dt.date.today().isoformat()
    proyecto = RAIZ / "workspace" / "projects" / f"{hoy}-{slug(spec.title)}"
    partes = proyecto / "parts"
    partes.mkdir(parents=True, exist_ok=True)
    (proyecto / "spec.yaml").write_text(
        json.dumps(spec.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # --- FASE 3 · Diseño de la pieza ----------------------------------------
    tarea = spec_to_task(spec)
    carpeta = partes / tarea.part
    carpeta.mkdir(parents=True, exist_ok=True)

    port.notify(f"\nDiseñando `{tarea.part}`…")
    receta = PartDesignerAgent(cliente, CATALOGO).design(tarea.brief)
    (carpeta / "recipe.json").write_text(
        receta.model_dump_json(indent=2), encoding="utf-8"
    )

    port.notify("  receta:")
    for paso in receta.steps:
        port.notify(f"    {paso.generator}({json.dumps(paso.params, ensure_ascii=False)})")

    # --- Construcción headless ----------------------------------------------
    build = carpeta / "build.py"
    build.write_text(
        compose_build_script(receta, CATALOGO, output_dir=carpeta), encoding="utf-8"
    )
    proceso = subprocess.run(
        [_freecadcmd(), str(build)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    # El intérprete embebido de FreeCAD deja un __pycache__ entre los
    # artefactos e ignora PYTHONDONTWRITEBYTECODE, así que se limpia aquí.
    shutil.rmtree(carpeta / "__pycache__", ignore_errors=True)
    try:
        resultado = PartResult.from_build_output(tarea.part, proceso.stdout)
    except Exception as e:
        port.notify(f"\nLa construcción falló: {e}")
        port.notify(proceso.stderr[-800:])
        return

    port.notify(
        f"\n  volumen: {resultado.volume_mm3:.2f} mm³"
        f"\n  envolvente: {' x '.join(f'{v:g}' for v in resultado.bbox_mm)} mm"
    )
    port.notify(f"\nArtefactos en {carpeta.relative_to(RAIZ)}:")
    for archivo in sorted(carpeta.iterdir()):
        port.notify(f"  {archivo.name}  ({archivo.stat().st_size:,} bytes)")
    port.notify(f"\nEstado del proyecto: {estado} → pieza construida.")
    port.notify("Pendiente: laminado (F1.13) y QA (F2.13).")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit('uso: demo.py "lo que quieres diseñar"')
    main(" ".join(sys.argv[1:]))
