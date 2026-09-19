"""`intelliprint`: línea de comandos (entregable de la Fase 1).

    intelliprint new "lo que quieres diseñar"
    intelliprint resume <proyecto>

`resume` existe porque el estado se persiste tras cada etapa: si algo se
cae a mitad, se retoma sin repetir la admisión ni lo ya construido.
"""

import argparse
import datetime as dt
import os
import shutil
import sys
import uuid
from pathlib import Path

from orchestrator.build import design_and_build
from orchestrator.config import load_env
from orchestrator.graph import Dependencias, crear_grafo
from orchestrator.human.adapters.cli import CliAdapter
from orchestrator.llm.providers.deepseek import DeepSeekClient
from orchestrator.llm.router import Router
from orchestrator.slicing import PERFIL_M5, slice_stl
from orchestrator.tasks import spec_to_task


def _raiz() -> Path:
    """Los prompts y perfiles viven en config/ con rutas relativas: el
    comando tiene que ejecutarse desde la raíz del repo, esté donde esté."""
    for carpeta in [Path.cwd(), *Path.cwd().parents]:
        if (carpeta / "config" / "models.yaml").exists():
            return carpeta
    sys.exit("no encuentro config/models.yaml: ejecuta dentro del repo de Intelliprint")


def _freecadcmd(env: dict) -> str:
    ruta = (
        env.get("FREECADCMD")
        or shutil.which("freecadcmd")
        or "/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd"
    )
    if not Path(ruta).exists():
        sys.exit(f"freecadcmd no encontrado en {ruta} (define FREECADCMD)")
    return ruta


def _cliente(router: Router, env: dict):
    ref = router.for_role("design")
    if ref.provider == "deepseek":
        return DeepSeekClient(api_key=env["DEEPSEEK_API_KEY"], model=ref.model)
    sys.exit(
        f"el perfil {router.profile_name!r} usa {ref.provider}/{ref.model}, y el "
        "cliente de Ollama todavía no existe: llega con la migración (F0.11)."
    )


def _grafo(raiz: Path, env: dict):
    from mech_toolkit.generators import CATALOGO
    from orchestrator.agents.part_designer import PartDesignerAgent
    from orchestrator.agents.requirements import RequirementsAgent

    router = Router.from_config_file(raiz / "config" / "models.yaml", env=env)
    cliente = _cliente(router, env)
    freecad = _freecadcmd(env)
    disenador = PartDesignerAgent(cliente, CATALOGO)

    def disenar(spec, carpeta, part):
        return design_and_build(
            disenador, spec_to_task(spec).brief, CATALOGO, carpeta,
            freecadcmd=freecad, part=part,
        )

    deps = Dependencias(
        requirements=RequirementsAgent(cliente),
        disenar=disenar,
        laminar=lambda stl, salida: slice_stl(stl, raiz / PERFIL_M5, salida),
        port=CliAdapter(),
        workspace=_workspace(raiz, env) / "projects",
    )
    return crear_grafo(deps, _workspace(raiz, env) / "state.sqlite")


def _workspace(raiz: Path, env: dict) -> Path:
    """`INTELLIPRINT_WORKSPACE` permite ejecutar pruebas en otra carpeta:
    así una prueba nunca pisa los proyectos reales de `workspace/`."""
    return Path(env["INTELLIPRINT_WORKSPACE"]) if env.get("INTELLIPRINT_WORKSPACE") else raiz / "workspace"


def _informar(final: dict, nombre: str) -> None:
    print()
    if final.get("estado") == "INTAKE":
        print(f"[{nombre}] No confirmado: el proyecto se queda en admisión, sin gastar nada.")
        return
    r, s = final["result"], final["slicing"]
    h, m = divmod(s["time_s"] // 60, 60)
    print(f"[{nombre}] Listo: {final['part']}")
    print(f"  pieza:    {r['volume_mm3']:.1f} mm³, envolvente {' x '.join(f'{v:g}' for v in r['bbox_mm'])} mm")
    print(f"  laminado: {s['grams']:.1f} g, {s['filament_mm'] / 1000:.2f} m, {h} h {m} min")
    print(f"  proyecto: {final['proyecto']}")
    print("  ⚠️ el G-code de inicio del perfil de la M5 no está verificado: revísalo antes de imprimir.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="intelliprint")
    sub = parser.add_subparsers(dest="comando", required=True)
    nuevo = sub.add_parser("new", help="empezar un proyecto")
    nuevo.add_argument("peticion", nargs="+")
    reanudar = sub.add_parser("resume", help="reanudar un proyecto interrumpido")
    reanudar.add_argument("proyecto")
    args = parser.parse_args(argv)

    raiz = _raiz()
    os.chdir(raiz)
    env = load_env(raiz / ".env")
    nombre = env.get("AGENT_NAME") or "Crafty"
    grafo = _grafo(raiz, env)

    if args.comando == "new":
        hilo = f"{dt.datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
        print(f"[{nombre}] Proyecto {hilo}. Si algo se interrumpe: intelliprint resume {hilo}")
        final = grafo.invoke({"peticion": " ".join(args.peticion)},
                             {"configurable": {"thread_id": hilo}})
    else:
        final = grafo.invoke(None, {"configurable": {"thread_id": args.proyecto}})
    _informar(final, nombre)


if __name__ == "__main__":
    main()
