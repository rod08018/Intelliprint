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


def _cliente(router: Router, env: dict, role: str = "design"):
    ref = router.for_role(role)
    if ref.provider == "deepseek":
        return DeepSeekClient(api_key=env["DEEPSEEK_API_KEY"], model=ref.model)
    sys.exit(
        f"el perfil {router.profile_name!r} usa {ref.provider}/{ref.model}, y el "
        "cliente de Ollama todavía no existe: llega con la migración (F0.11 (migrar))."
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
            freecadcmd=freecad, part=part, request=spec.request,
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
    if r.get("untraced_mm"):
        cotas = ", ".join(f"{c:g} mm" for c in r["untraced_mm"])
        print(f"  ⚠️ cotas de tu petición que NO aparecen en la pieza: {cotas}. Revísala antes de imprimir.")
    print("  ⚠️ el G-code de inicio del perfil de la M5 no está verificado: revísalo antes de imprimir.")


def _mecanismo(args, raiz: Path, env: dict, nombre: str) -> None:
    import yaml

    from mech_toolkit.generators import CATALOGO
    from mech_toolkit.profile import PrinterProfile
    from orchestrator.agents.part_designer import PartDesignerAgent
    from orchestrator.mechanisms.run import build_mechanism, llm_designer
    from orchestrator.mechanisms.slider_crank import SliderCrankLayout

    perfil = PrinterProfile(**yaml.safe_load(
        (raiz / "config/printers/ankermake_m5_petg.yaml").read_text()))
    if args.peticion != ["biela-manivela"]:
        _mecanismo_desde_texto(args, raiz, env, nombre, perfil)
        return
    if args.carrera is None:
        sys.exit("biela-manivela necesita --carrera")
    layout = SliderCrankLayout(stroke_mm=args.carrera, profile=perfil)
    origen = "referencia" if args.referencia else "modelo"
    carpeta = (_workspace(raiz, env) / "projects"
               / f"{dt.date.today():%Y-%m-%d}-biela_manivela_{args.carrera:g}mm_{origen}")
    print(f"[{nombre}] Biela-manivela-corredera, carrera {args.carrera:g} mm → {carpeta}")
    freecad = _freecadcmd(env)
    disenar = None
    if not args.referencia:
        router = Router.from_config_file(raiz / "config" / "models.yaml", env=env)
        agente = PartDesignerAgent(_cliente(router, env), CATALOGO)
        disenar = llm_designer(agente, layout.briefs(), freecad, check=layout.check_bounds)
        print(f"  las piezas las diseña el modelo ({router.profile_name})")
    informe = build_mechanism(layout, carpeta, freecad,
                              min_gap_mm=perfil.fit_mm("slide") / 2, disenar=disenar)
    print(f"  ensamble:  {informe.assembly}  (ábrelo en FreeCAD)")
    print(f"  animación: {informe.animation}")
    if informe.ok:
        print(f"  ✓ sin choques en {len(informe.angles)} posiciones de la vuelta "
              f"(holgura mínima {informe.min_gap_mm:g} mm)")
    else:
        print(f"  ✗ choques en {len({c.angle for c in informe.collisions})} de "
              f"{len(informe.angles)} posiciones:")
        for linea in informe.collision_summary():
            print(f"    - {linea}")


def _mecanismo_desde_texto(args, raiz: Path, env: dict, nombre: str, perfil) -> None:
    """F3.15 (mecanismos): todo lo decide Intelliprint a partir del texto."""
    import yaml

    from mech_toolkit.generators import CATALOGO
    from orchestrator.agents.design_reviewer import DesignReviewerAgent
    from orchestrator.agents.mechanism_designer import MechanismDesignerAgent
    from orchestrator.agents.part_designer import PartDesignerAgent
    from orchestrator.mechanisms.flow import design_mechanism
    from orchestrator.tasks import slug

    peticion = " ".join(args.peticion)
    if args.archivo:
        peticion = Path(peticion).read_text(encoding="utf-8")
    impresora = yaml.safe_load((raiz / "config/printers/ankermake_m5_petg.yaml").read_text())
    cama = tuple(impresora["bed_mm"][k] for k in "xyz")
    hueco = perfil.fit_mm("slide") / 2
    router = Router.from_config_file(raiz / "config" / "models.yaml", env=env)
    cliente = _cliente(router, env)
    carpeta = (_workspace(raiz, env) / "projects"
               / f"{dt.datetime.now():%Y-%m-%d-%H%M}-{slug(peticion.split(chr(10))[0])[:40]}")
    print(f"[{nombre}] Mecanismo desde tu texto → {carpeta}")
    print(f"  Mechanism Designer: {router.for_role('reason').model} · "
          f"Part Designer: {router.for_role('design').model}")
    informe = design_mechanism(
        peticion,
        MechanismDesignerAgent(_cliente(router, env, "reason"), CATALOGO, perfil, cama, hueco,
                               wall_mm=impresora["walls"]["structural_mm"]),
        PartDesignerAgent(cliente, CATALOGO),
        carpeta, _freecadcmd(env), min_gap_mm=hueco,
        reviewer=DesignReviewerAgent(cliente),
    )
    f = informe.final
    print()
    print(f"[{nombre}] {informe.rounds[-1].title}: {len(informe.rounds)} ronda(s)")
    if f is not None:
        print(f"  ensamble:  {f.assembly}  (ábrelo en FreeCAD)")
        print(f"  animación: {f.animation}")
        for nota in f.notes:
            print(f"  · {nota}")
    if informe.ok:
        print(f"  ✓ sin choques en {len(f.angles)} posiciones; contactos y requisitos cumplidos")
    else:
        print("  ✗ no quedó resuelto. Lo último que falló:")
        print(informe.rounds[-1].feedback)
    if informe.review is not None:
        r = informe.review
        print(f"\n  Revisión frente a tu petición ({len(r.por_veredicto('cumple'))} cumplen, "
              f"{len(r.por_veredicto('no_cumple'))} no, "
              f"{len(r.por_veredicto('no_verificable'))} sin verificar):")
        for i in r.items:
            if i.verdict != "cumple":
                print(f"    · {i.verdict}: {i.requirement} — {i.comment}")
        print(f"    {r.summary}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="intelliprint")
    sub = parser.add_subparsers(dest="comando", required=True)
    nuevo = sub.add_parser("new", help="empezar un proyecto")
    nuevo.add_argument("peticion", nargs="+")
    reanudar = sub.add_parser("resume", help="reanudar un proyecto interrumpido")
    reanudar.add_argument("proyecto")
    meca = sub.add_parser("mecanismo", help="diseñar un mecanismo y ver su ensamble animado")
    meca.add_argument("peticion", nargs="+",
                      help='el mecanismo en texto, o "biela-manivela" con --carrera')
    meca.add_argument("--archivo", action="store_true",
                      help="la petición es la ruta de un archivo de texto")
    meca.add_argument("--carrera", type=float, help="solo biela-manivela: carrera, mm")
    meca.add_argument("--referencia", action="store_true",
                      help="usar las recetas fijas de la disposición en vez del modelo")
    args = parser.parse_args(argv)

    raiz = _raiz()
    os.chdir(raiz)
    env = load_env(raiz / ".env")
    nombre = env.get("AGENT_NAME") or "Crafty"
    if args.comando == "mecanismo":
        _mecanismo(args, raiz, env, nombre)
        return
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
