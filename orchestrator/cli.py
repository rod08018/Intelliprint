"""`intelliprint`: línea de comandos (entregable de la Fase 1).

    intelliprint new "lo que quieres diseñar"
    intelliprint resume <proyecto>

`resume` existe porque el estado se persiste tras cada etapa: si algo se
cae a mitad, se retoma sin repetir la admisión ni lo ya construido.
"""

import argparse
import json
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
from orchestrator.impresion import perfil_activo
from orchestrator.llm.providers.deepseek import DeepSeekClient
from orchestrator.llm.router import Router
from orchestrator.slicing import elegir_laminador
from orchestrator.tasks import nombre_corto, spec_to_task


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


CONSTRUCCIONES_KIT = 5


def _disenar_con_kit(raiz: Path, env: dict, cliente):
    """Las piezas sueltas se dibujan con el kit (F5.18 (kit)): el catálogo
    de generadores no sabía hacer una cartela, un hexágono ni un chaflán. Los
    mecanismos siguen con recetas hasta que el kit los cubra."""
    from orchestrator.agents.disenador_kit import DisenadorKitAgent
    from orchestrator.componentes import mencionados
    from orchestrator.medida import defectos_de_la_pieza

    freecad = _freecadcmd(env)
    router = Router.from_config_file(raiz / "config" / "models.yaml", env=env)
    # Con el razonador y cinco construcciones: en el banco (2026-11-04)
    # deepseek-chat recibía el motivo exacto —«los lados 2 y 7 se cruzan»,
    # «el rebaje del servo no toca la pieza»— y no lo corregía en tres.
    disenador = DisenadorKitAgent(_cliente(router, env, "reason"), _perfil(raiz, env),
                                  reserva=cliente)
    material = _perfil(raiz, env).datos["resistencia"]
    pared_min = (_perfil(raiz, env).datos.get("walls") or {}).get("min_mm")
    agujeros = _perfil(raiz, env).datos.get("holes") or {}

    def disenar(spec, carpeta, part, concepto=None, partida=None):
        # F6.7 (lazo): lo que la pieza construida no cumple de los requisitos
        # vuelve al diseñador como cualquier fallo; F6.8 (mejor): si nunca
        # lo cumple todo, se entrega la que menos falla, con la lista.
        # F6.11 (biblioteca): cada componente que aloja la pieza tiene que
        # estar colocado con `kit.componente`, o no se puede ver si cabe.
        componentes = ([c.id for c in concepto.concepto.componentes] if concepto
                       else mencionados(spec.request))

        def requisitos_medidos(resultado):
            return "\n".join(defectos_de_la_pieza(
                spec.requisitos, resultado, Path(carpeta) / f"{part}.step", freecad,
                material, componentes, pared_min, agujeros)) or None

        return design_and_build(
            disenador, spec_to_task(spec, concepto).brief, None, carpeta,
            freecadcmd=freecad, part=part, request=spec.request, perfil=disenador.perfil,
            max_construcciones=CONSTRUCCIONES_KIT, check=requisitos_medidos,
            entregar_mejor=True, partida=partida,
        )
    return disenar


def _grafo(raiz: Path, env: dict):
    from orchestrator.agents.requirements import RequirementsAgent

    router = Router.from_config_file(raiz / "config" / "models.yaml", env=env)
    cliente = _cliente(router, env)
    deps = Dependencias(
        requirements=RequirementsAgent(cliente, activo=_perfil(raiz, env)),
        disenar=_disenar_con_kit(raiz, env, cliente),
        laminar=elegir_laminador(raiz, env),
        port=CliAdapter(),
        workspace=_workspace(raiz, env) / "projects",
        ingeniero=_ingeniero(raiz, router, env, cliente),
    )
    return crear_grafo(deps, _workspace(raiz, env) / "state.sqlite")


def _ingeniero(raiz: Path, router: Router, env: dict, reserva):
    """F3.18 (ingeniero), con el razonador: decidir cómo se resuelve una
    pieza es el paso que más pensar pide. `reserva` es el modelo sin
    pensamiento, por si el razonador se corta (ver `structured`)."""
    from orchestrator.agents.ingeniero import IngenieroAgent
    return IngenieroAgent(_cliente(router, env, "reason"), _perfil(raiz, env), reserva=reserva)


def _perfil(raiz: Path, env: dict):
    """El perfil activo con lo que el usuario midió en su impresora
    (F2.21 (impresora)). Todo lo que diseña pasa por aquí: un camino que
    leyera solo `config/` diseñaría con 3.3 aunque se hubiera medido 3.4."""
    return perfil_activo(raiz, _workspace(raiz, env))


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
    for d in r.get("defectos", []):
        print(f"  ⚠️ no cumple: {d}")
    if r.get("untraced_mm"):
        cotas = ", ".join(f"{c:g} mm" for c in r["untraced_mm"])
        print(f"  ⚠️ cotas de tu petición que NO aparecen en la pieza: {cotas}. Revísala antes de imprimir.")
    print("  ⚠️ el G-code de inicio del perfil de la M5 no está verificado: revísalo antes de imprimir.")


def _mecanismo(args, raiz: Path, env: dict, nombre: str) -> None:

    from mech_toolkit.generators import CATALOGO
    from orchestrator.agents.part_designer import PartDesignerAgent
    from orchestrator.mechanisms.run import build_mechanism, llm_designer
    from orchestrator.mechanisms.slider_crank import SliderCrankLayout

    perfil = _perfil(raiz, env).impresora
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
    from orchestrator.llm.cost import Presupuesto
    from orchestrator.agents.part_designer import PartDesignerAgent
    from orchestrator.mechanisms.flow import design_mechanism
    from orchestrator.tasks import slug

    peticion = " ".join(args.peticion)
    if args.archivo:
        peticion = Path(peticion).read_text(encoding="utf-8")
    impresora = _perfil(raiz, env).datos
    cama = tuple(impresora["bed_mm"][k] for k in "xyz")
    hueco = perfil.fit_mm("slide") / 2
    router = Router.from_config_file(raiz / "config" / "models.yaml", env=env)
    cliente = _cliente(router, env)
    mecanico = _cliente(router, env, "reason")
    presupuesto = Presupuesto.from_config(
        yaml.safe_load((raiz / "config" / "models.yaml").read_text(encoding="utf-8")))
    presupuesto.vigila(cliente, "Part Designer / Design Reviewer")
    presupuesto.vigila(mecanico, "Mechanism Designer")
    carpeta = Path(args.carpeta) if args.carpeta else (
        _workspace(raiz, env) / "projects"
        / f"{dt.datetime.now():%Y-%m-%d-%H%M}-{slug(peticion.split(chr(10))[0])[:40]}")
    from orchestrator.mechanisms.referencias import ReferenciaInvalida, desde_el_entorno
    try:
        referencias = desde_el_entorno(args.adjunto, _workspace(raiz, env), env)
    except ReferenciaInvalida as e:
        sys.exit(f"referencia no válida: {e}")
    # Una versión nueva de un proyecto parte de su base y solo cambia lo
    # pedido: rediseñar entero un sargento para agrandarle el mango eran
    # 4-7 rondas del razonador (2026-10-26).
    from orchestrator.web.versiones import edicion_de
    edicion = (edicion_de(carpeta, _workspace(raiz, env))
               if args.carpeta and not args.continuar else None)
    base, cambio, pieza = edicion or (None, "", "")
    print(f"[{nombre}] Mecanismo desde tu texto → {carpeta}")
    if base is not None:
        print(f"  versión nueva: parte de {base.name} y cambia "
              + (f"solo «{pieza}»" if pieza else "lo pedido"))
    print(f"  Mechanism Designer: {router.for_role('reason').model} · "
          f"Part Designer: {router.for_role('design').model}")
    # Crafty lanza esto en el contenedor del MCP y la web lo mira desde el
    # suyo: sin latido, el pid de job.json no le dice nada (2026-10-26).
    from orchestrator.registry import latir
    with latir(carpeta):
        informe = design_mechanism(
            peticion,
            MechanismDesignerAgent(mecanico, CATALOGO, perfil, cama, hueco,
                                   wall_mm=impresora["walls"]["structural_mm"],
                                   reserva=cliente),
            PartDesignerAgent(cliente, CATALOGO),
            carpeta, _freecadcmd(env), min_gap_mm=hueco,
            reviewer=DesignReviewerAgent(cliente), continuar=args.continuar,
            presupuesto=presupuesto, referencias=referencias,
            base=base, cambio=cambio, pieza=pieza,
        )
    f = informe.final
    print()
    motivo_parada = {
        "resuelto": "", "atascado": " — se atascó repitiendo el mismo fallo",
        "presupuesto": f" — se acabó el presupuesto ({informe.spent_usd:.2f} USD)",
        "rondas": " — se alcanzó el límite de rondas",
        "con_defectos": " — CON DEFECTOS: el revisor ve requisitos sin cumplir",
    }[informe.stopped_because]
    print(f"[{nombre}] {informe.rounds[-1].title}: {len(informe.rounds)} ronda(s)"
          f"{motivo_parada}. Gasto: {informe.spent_usd:.2f} USD "
          f"(desglose en design_cost.md)")
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


def _diseñar_mecanismo(peticion: str, raiz: Path, env: dict, nombre: str, log):
    """El trabajo que hace el bot: el mismo flujo del comando `mecanismo`."""

    from mech_toolkit.generators import CATALOGO
    from orchestrator.agents.design_reviewer import DesignReviewerAgent
    from orchestrator.agents.mechanism_designer import MechanismDesignerAgent
    from orchestrator.agents.part_designer import PartDesignerAgent
    from orchestrator.mechanisms.flow import design_mechanism
    from orchestrator.tasks import slug

    impresora = _perfil(raiz, env).datos
    perfil = _perfil(raiz, env).impresora
    cama = tuple(impresora["bed_mm"][k] for k in "xyz")
    hueco = perfil.fit_mm("slide") / 2
    router = Router.from_config_file(raiz / "config" / "models.yaml", env=env)
    cliente = _cliente(router, env)
    carpeta = (_workspace(raiz, env) / "projects"
               / f"{dt.datetime.now():%Y-%m-%d-%H%M}-{slug(peticion.splitlines()[0])[:40]}")
    from orchestrator.registry import latir
    with latir(carpeta):
        informe = design_mechanism(
            peticion,
            MechanismDesignerAgent(_cliente(router, env, "reason"), CATALOGO, perfil, cama, hueco,
                                   wall_mm=impresora["walls"]["structural_mm"]),
            PartDesignerAgent(cliente, CATALOGO),
            carpeta, _freecadcmd(env), min_gap_mm=hueco,
            reviewer=DesignReviewerAgent(cliente), log=log,
        )
    f = informe.final
    lineas = [f"[{nombre}] {informe.rounds[-1].title}: {len(informe.rounds)} ronda(s)"]
    if f is not None:
        lineas += [f"· {n}" for n in f.notes]
        lineas.append("✓ sin choques en el ciclo completo" if informe.ok
                      else "✗ quedaron problemas:\n" + informe.rounds[-1].feedback)
    if informe.review is not None:
        r = informe.review
        lineas.append(f"\nRevisión: {len(r.por_veredicto('cumple'))} cumplen, "
                      f"{len(r.por_veredicto('no_cumple'))} no, "
                      f"{len(r.por_veredicto('no_verificable'))} sin verificar")
        lineas += [f"· {i.verdict}: {i.requirement} — {i.comment}"
                   for i in r.items if i.verdict != "cumple"]
        lineas.append(r.summary)
    lineas.append(f"\nProyecto: {carpeta}")
    archivos = [Path(f.animation) for f in [f] if f and f.animation]
    archivos += [Path(f.assembly) for f in [f] if f and f.assembly]
    return {"texto": "\n".join(lineas), "archivos": archivos}


def _animar(args, raiz: Path, env: dict, nombre: str) -> None:
    """Rehace ensamble y animación desde el mecanismo y las piezas ya
    construidas: no vuelve a diseñar ni a gastar modelo."""

    from orchestrator.mechanisms.run import build_mechanism
    from orchestrator.mechanisms.spec_layout import SpecLayout
    from orchestrator.schemas.mechanism import MechanismSpec

    carpeta = Path(args.carpeta)
    spec = MechanismSpec.model_validate_json((carpeta / "mechanism.json").read_text(encoding="utf-8"))
    perfil = _perfil(raiz, env).impresora
    informe = build_mechanism(
        SpecLayout(spec), carpeta, _freecadcmd(env),
        min_gap_mm=perfil.fit_mm("slide") / 2, disenar=lambda n, c: None, animar=True)
    print(f"[{nombre}] {spec.title}")
    print(f"  ensamble:  {informe.assembly}")
    print(f"  animación: {informe.animation}")


def _proyectos(args, raiz: Path, env: dict, nombre: str) -> None:
    from orchestrator.registry import archivar, escribir_indice, indice

    proyectos = _workspace(raiz, env) / "projects"
    if args.archivar:
        movidos = archivar(proyectos, _workspace(raiz, env) / "archivo")
        print(f"[{nombre}] Movidos a archivo/ (no se borró nada): {len(movidos)}")
        for m in movidos:
            print(f"  · {m}")
    indice_path = escribir_indice(proyectos)
    filas = indice(proyectos)
    print(f"[{nombre}] {len(filas)} proyectos en projects/ · índice en {indice_path}")
    for f in filas:
        marca = {"aprobado": "✓", "con reparos": "~", "antiguo": "·", "fallido": "✗",
                 "en marcha": "…", "incompleto": "?"}.get(f["estado"], "?")
        print(f"  {marca} {f['id']}  {f['rondas']} rondas  {f['usd']:.2f} USD  {f['titulo'][:40]}")


def _bot(raiz: Path, env: dict, nombre: str) -> None:
    from orchestrator.human.adapters.telegram import (
        ListaBlancaInvalida, TelegramBot, TelegramClient, leer_lista_blanca)

    token = env.get("TELEGRAM_BOT_TOKEN")
    if not token:
        sys.exit("falta TELEGRAM_BOT_TOKEN en .env (plantilla en .env.example)")
    # La lista es opcional (F5.10 (lista)): sin ella el canal está abierto,
    # por decisión del usuario.
    try:
        permitidos = leer_lista_blanca(env.get("TELEGRAM_ALLOWED_USERS"))
    except ListaBlancaInvalida as e:
        sys.exit(str(e))
    print(f"[{nombre}] Escuchando en Telegram. Ctrl+C para parar.")
    if permitidos:
        print(f"  Solo atiendo a {len(permitidos)} usuario(s) de TELEGRAM_ALLOWED_USERS.")
    else:
        print("  Canal abierto: atiendo a cualquiera que escriba al bot.")
    bot = TelegramBot(
        TelegramClient(token),
        lambda peticion, avisar: _diseñar_mecanismo(peticion, raiz, env, nombre, log=avisar),
        nombre=nombre,
        permitidos=permitidos,
    )
    bot.run()


def _calibrar(args, raiz: Path, env: dict, nombre: str) -> None:
    """F2.18 (calibración) y F2.21 (impresora): construir las piezas de
    prueba, o apuntar lo que encajó."""
    from orchestrator.calibracion import cuadro, cuadro_barra, recetas, recetas_barra
    from orchestrator.medidas_impresora import MedidaInvalida, registrar

    activo = _perfil(raiz, env)
    if args.accion in ("pieza", "barra"):
        from mech_toolkit.generators import CATALOGO
        from orchestrator.build import build_part

        holguras = args.accion == "pieza"
        sufijo, titulo, piezas, texto = (
            ("calibracion_holguras", "Pieza de calibración de holguras", recetas(), cuadro())
            if holguras else
            ("calibracion_barras", "Barras de flexión", recetas_barra(), cuadro_barra()))
        carpeta = (_workspace(raiz, env) / "projects"
                   / f"{dt.datetime.now():%Y-%m-%d-%H%M}-{sufijo}")
        carpeta.mkdir(parents=True)
        # Quién la construye: sin job.json, una carpeta recién hecha y sin
        # rondas se toma por un diseño en marcha y bloquea «Diseñar».
        (carpeta / "job.json").write_text(json.dumps(
            {"pid": os.getpid(), "inicio": dt.datetime.now().isoformat()}), encoding="utf-8")
        (carpeta / "request.md").write_text(
            # La primera línea es el título en la web: corta, o sale cortada.
            f"{titulo}\n\nPara {activo.impresora.id} ({activo.material}).\n",
            encoding="utf-8")
        (carpeta / "calibracion.md").write_text(texto, encoding="utf-8")
        from orchestrator.registry import latir
        with latir(carpeta):
            for receta in piezas:
                print(f"[{nombre}] construyendo {receta.part}…")
                build_part(receta, CATALOGO, carpeta / "parts" / receta.part, _freecadcmd(env))
        print(f"[{nombre}] Listo: {carpeta}\n  Cómo probarla y qué apuntar: {carpeta / 'calibracion.md'}")
        return

    # Al workspace y no a config/printers/, que dentro del contenedor es de
    # solo lectura: apuntar las holguras solo se podía desde el PC.
    try:
        registrar(_workspace(raiz, env), activo.impresora.id, "tolerancias", {
            "press_mm": args.press, "slide_mm": args.slide, "clearance_mm": args.clearance,
            "m3_through_mm": args.m3_through, "m3_selftap_mm": args.m3_selftap,
            "m3_insert_mm": args.m3_insert}, fotos=[])
    except MedidaInvalida as e:
        sys.exit(f"no se ha cambiado nada: {e}")
    print(f"[{nombre}] {activo.impresora.id}: apuntado. Desde ahora se diseña con lo que mediste.")


def _pieza(args, raiz: Path, env: dict, nombre: str) -> None:
    """Una pieza suelta sin confirmación por consola (F5.17 (pieza)): quien la
    lanza desde la web o Telegram ya confirmó al pedirla. Para probar a mano
    con confirmación sigue estando `intelliprint new`."""
    from orchestrator.agents.requirements import RequirementsAgent
    from orchestrator.pieza import APROBADO, concebir_pieza, disenar_pieza

    texto = " ".join(args.peticion)
    peticion = Path(texto).read_text(encoding="utf-8") if args.archivo else texto
    carpeta = (Path(args.carpeta) if args.carpeta else _workspace(raiz, env) / "projects"
               / f"{dt.datetime.now():%Y-%m-%d-%H%M%S}-{nombre_corto(peticion.splitlines()[0], 40)}")
    router = Router.from_config_file(raiz / "config" / "models.yaml", env=env)
    cliente = _cliente(router, env)
    requisitos = RequirementsAgent(cliente, activo=_perfil(raiz, env))
    print(f"[{nombre}] Pieza → {carpeta}", flush=True)

    # F3.20 (concepto): sin visto bueno no se modela. La primera vez (y tras
    # contestar al ingeniero) se propone el concepto y se para; la web o
    # Crafty dejan la marca y reanudan, y entonces se modela ESE concepto.
    if not (carpeta / APROBADO).exists():
        from orchestrator.investigar import BuscadorDeepSeek, Investigador
        from orchestrator.juez import juzgar_concepto

        # La búsqueda de DeepSeek, con la misma clave: DuckDuckGo bloquea las
        # búsquedas del contenedor y no se quiere pagar otro servicio.
        concepto = concebir_pieza(peticion, carpeta, requisitos=requisitos,
                                  ingeniero=_ingeniero(raiz, router, env, cliente),
                                  investigador=Investigador(
                                      cliente, BuscadorDeepSeek(env["DEEPSEEK_API_KEY"])),
                                  juez=lambda texto: juzgar_concepto(texto,
                                                                     env.get("JEV_API_KEY")))
        if concepto is None:
            sys.exit(f"[{nombre}] ✗ el concepto no salió: mira {carpeta / 'blocked.md'}")
        if not args.aprobar_concepto:
            print(f"[{nombre}] ✋ concepto listo: espera tu visto bueno ({carpeta / 'concepto.md'})")
            return
        # Solo el banco: no hay nadie para dar el visto bueno, y lo que se
        # mide es lo que sale del concepto tal como lo propuso el ingeniero.
        from orchestrator.pieza import aprobar_concepto
        aprobar_concepto(carpeta, por="banco")

    # Sin laminar: al diseñar no se sabe en qué impresora se va a imprimir,
    # así que el G-code y los gramos de un perfil cualquiera eran tiempo
    # perdido (decidido por el usuario, 2026-11-09). Se lamina cuando la
    # persona abre PrusaSlicer desde la web; el banco lamina para juzgar.
    informe = disenar_pieza(peticion, carpeta, requisitos=requisitos,
                            disenar=_disenar_con_kit(raiz, env, cliente), laminar=None)
    if informe.resuelto:
        gramos = f", {informe.gramos:.1f} g" if informe.gramos is not None else ""
        print(f"[{nombre}] ✓ {informe.titulo}: "
              f"{' x '.join(f'{v:g}' for v in informe.bbox_mm)} mm{gramos}")
    else:
        print(f"[{nombre}] ✗ {informe.titulo}: {informe.motivo}")
        sys.exit(1)


def _obra(args, raiz: Path, env: dict, nombre: str) -> None:
    """Un proyecto por partes (F7.2 (desglose)). Cada vez que se lanza da UN
    paso y para donde haga falta la persona: el desglose, el concepto de un
    nodo o su «está bien, la siguiente». La web o Crafty dejan la marca y
    vuelven a lanzarlo. Con `--banco`, la obra entera de una vez."""
    from orchestrator import obra

    texto = " ".join(args.peticion)
    peticion = Path(texto).read_text(encoding="utf-8") if args.archivo else texto
    carpeta = (Path(args.carpeta) if args.carpeta else _workspace(raiz, env) / "projects"
               / f"{dt.datetime.now():%Y-%m-%d-%H%M%S}-{nombre_corto(peticion.splitlines()[0], 40)}")
    carpeta.mkdir(parents=True, exist_ok=True)
    if not (carpeta / "request.md").exists():
        (carpeta / "request.md").write_text(peticion.strip() + "\n", encoding="utf-8")
    # «Backlog» y no «obra»: así lo llama el usuario (2026-11-09). Las
    # estadísticas de la web reconocen la línea por «palabra →».
    print(f"[{nombre}] Backlog → {carpeta}", flush=True)
    if not getattr(args, "banco", False):
        _paso_de_obra(carpeta, peticion, raiz, env, nombre)
        return

    # F7.5 (obras): en el banco no hay nadie para el visto bueno. Lo da el
    # banco, como `pieza --aprobar-concepto`, y lo que se mide es lo que sale
    # tal como lo propuso el sistema. Cada vuelta da un paso o una marca; el
    # tope solo evita girar sin fin si un estado no se reconoce.
    for _ in range(4 * 20):
        try:
            _paso_de_obra(carpeta, peticion, raiz, env, nombre)
        except SystemExit:
            # Una pieza con fallos se entrega igual (F6.8 (mejor)) y se juzga.
            i = obra.siguiente(carpeta) if obra.es_obra(carpeta) else None
            if i is None or obra.estados(carpeta)[i] != "con fallos":
                raise
        if not obra.es_obra(carpeta):
            return
        if not obra.aprobada(carpeta):
            obra.aprobar(carpeta, por="banco")
            continue
        i = obra.siguiente(carpeta)
        estado = obra.estados(carpeta).get(i)
        if i is None or estado == "con choques":
            return
        if estado == "concepto por aprobar":
            obra.aprobar(carpeta, por="banco")
        elif estado in ("diseñada", "con fallos"):
            try:
                obra.dar_por_lista(carpeta, i, por="banco")
            except ValueError as e:   # no llegó a construirse: no hay qué fichar
                print(f"[{nombre}] ✗ {e}", flush=True)
                return
        elif estado not in obra.SE_LANZAN:
            print(f"[{nombre}] ✗ «{i}» se quedó «{estado}»", flush=True)
            return


def _paso_de_obra(carpeta: Path, peticion: str, raiz: Path, env: dict, nombre: str) -> None:
    from types import SimpleNamespace

    from orchestrator import obra
    from orchestrator.agents.desglosador import DesglosadorAgent
    from orchestrator.registry import latir

    if not obra.es_obra(carpeta):
        router = Router.from_config_file(raiz / "config" / "models.yaml", env=env)
        cliente = _cliente(router, env)
        with latir(carpeta):
            try:
                desglose = DesglosadorAgent(_cliente(router, env, "reason"),
                                            reserva=cliente).desglosar(peticion)
            except ValueError as e:
                (carpeta / "rounds.json").write_text(json.dumps(
                    [{"number": 1, "title": "desglose", "feedback": f"el desglose no salió: {e}",
                      "plan": None}], ensure_ascii=False), encoding="utf-8")
                sys.exit(f"[{nombre}] ✗ el desglose no salió: {e}")
            obra.guardar(carpeta, desglose, por="desglosador")
        print(obra.presentar(desglose), flush=True)
    if not obra.aprobada(carpeta):
        print(f"[{nombre}] ✋ desglose listo: espera tu visto bueno ({carpeta / 'obra.md'})")
        return

    nodo = obra.siguiente(carpeta)
    if nodo is None:
        print(f"[{nombre}] ✓ backlog terminado: {', '.join(obra.estados(carpeta))}")
        return
    estado = obra.estados(carpeta)[nodo]
    nombre_nodo = obra.cargar_obra(carpeta).nodo(nodo).nombre
    if estado in ("diseñada", "con fallos"):
        print(f"[{nombre}] ✋ «{nombre_nodo}» está {estado}: revísala y da el visto bueno "
              "para seguir con la siguiente, o pide rehacerla")
        return
    if estado == "concepto por aprobar":
        print(f"[{nombre}] ✋ «{nombre_nodo}»: el concepto espera tu visto bueno")
        return
    if estado == "con choques":
        print(f"[{nombre}] ✋ «{nombre_nodo}» choca al moverse: corrige la pieza que choca")
        return
    if estado == "por verificar":
        # F7.4 (conjunto): con sus piezas listas, se mueve entero en FreeCAD.
        from orchestrator.conjunto import verificar_conjunto
        dir_nodo = carpeta / obra.NODOS / nodo
        dir_nodo.mkdir(parents=True, exist_ok=True)
        print(f"[{nombre}] «{nombre_nodo}»: se mueve por todo su recorrido…", flush=True)
        with latir(carpeta), latir(dir_nodo):
            v = verificar_conjunto(carpeta, nodo, _freecadcmd(env),
                                   min_gap_mm=_perfil(raiz, env).impresora.fit_mm("slide") / 2)
        for a in v["articulaciones"]:
            print(f"  «{a['pieza']}» gira con el {a['de']} de «{a['padre']}», "
                  f"de {a['recorrido'][0]:g}° a {a['recorrido'][1]:g}°", flush=True)
        if v["ok"]:
            print(f"[{nombre}] ✓ «{nombre_nodo}» se mueve sin chocar")
        else:
            print("\n".join(f"  - {r}" for r in v["resumen"]))
            print(f"[{nombre}] ✋ «{nombre_nodo}» choca al moverse: corrige la pieza que choca")
        return
    # Las piezas ya terminadas, como fichas: el nodo se diseña contra ellas
    # con `kit.componente`, igual que contra un 608ZZ comprado.
    fichas = str(obra.carpeta_de_fichas(carpeta))
    os.environ["INTELLIPRINT_FICHAS"] = os.pathsep.join(
        filter(None, [fichas, os.environ.get("INTELLIPRINT_FICHAS", "")]))
    # Y lo comprado que ya monta otra pieza: el kit no deja colocarlo otra vez.
    os.environ["INTELLIPRINT_AJENOS"] = json.dumps(obra.ajenos(carpeta, nodo),
                                                   ensure_ascii=False)
    dir_nodo = carpeta / obra.NODOS / nodo
    dir_nodo.mkdir(parents=True, exist_ok=True)
    (dir_nodo / "request.md").write_text(obra.peticion_del_nodo(carpeta, nodo), encoding="utf-8")
    print(f"[{nombre}] nodo «{nombre_nodo}» ({nodo})", flush=True)
    with latir(carpeta):
        try:
            _pieza(SimpleNamespace(peticion=[str(dir_nodo / "request.md")], archivo=True,
                                   carpeta=str(dir_nodo), aprobar_concepto=False),
                   raiz, env, nombre)
        except SystemExit as e:   # el nodo cerró con fallos: queda en su carpeta
            if e.code not in (None, 0):
                print(e.code if isinstance(e.code, str) else "", flush=True)
                sys.exit(1)
    if obra.estados(carpeta)[nodo] == "diseñada":
        print(f"[{nombre}] ✋ «{nombre_nodo}» diseñada: revísala y da el visto bueno "
              "para seguir con la siguiente")


def orden_del_banco(obra: bool = False) -> list[str]:
    """El banco pide como la web: por el flujo de pieza (investigador,
    ingeniero, kit), con el concepto aprobado tal cual. Hasta el 2026-11-05
    pedía con `new`, el grafo viejo, y su nota no medía lo que se usa. Una
    obra (F7.5 (obras)), entera y con el visto bueno dado por el banco."""
    if obra:
        return [sys.executable, "-m", "orchestrator.cli", "obra", "--banco"]
    return [sys.executable, "-m", "orchestrator.cli", "pieza", "--aprobar-concepto"]


def _banco(args, raiz: Path, env: dict, nombre: str) -> None:
    """Cada encargo se pide como lo pediría una persona, en una carpeta
    propia dentro de workspace/banco/: así queda la evidencia de cada
    corrida y nunca se pisan los proyectos de verdad."""
    from orchestrator import banco
    from orchestrator.banco import cargar_encargos, correr, informe, rejuzgar
    from orchestrator.build import carpeta_libre

    encargos = [e for e in cargar_encargos(raiz / "tests" / "banco" / "encargos")
                if not args.solo or e.nombre in args.solo]
    if not encargos:
        sys.exit(f"ningún encargo se llama {', '.join(args.solo)}")
    material = _perfil(raiz, env).datos["resistencia"]
    if args.reanudar:
        corrida = Path(args.reanudar)
        resultados, fallos = banco.reanudar(encargos, corrida, orden_del_banco(obra=True),
                                            _freecadcmd(env), dict(os.environ), material,
                                            elegir_laminador(raiz, env))
        texto = informe(resultados, modelo=f"{env.get('DEEPSEEK_MODEL', 'deepseek')}, "
                                           "reanudada desde la pieza que falló", fallos=fallos)
        # Al lado del original y de las vueltas anteriores, sin pisar ninguno.
        destino = carpeta_libre(corrida / "banco_reanudado.md")
        destino.write_text(texto, encoding="utf-8")
        print(texto)
        print(f"[{nombre}] informe en {destino}")
        return
    if args.rejuzgar:
        corrida = Path(args.rejuzgar)
        resultados, fallos = rejuzgar(encargos, corrida, _freecadcmd(env), material,
                                      elegir_laminador(raiz, env))
        texto = informe(resultados, modelo="rejuzgada con el juez de hoy", fallos=fallos)
        # Al lado del informe original, sin pisarlo: es la evidencia de esa corrida.
        (corrida / "banco_rejuzgado.md").write_text(texto, encoding="utf-8")
        print(texto)
        return
    # Carpetas cortas: dentro van projects/<fecha-título>/parts/<pieza>/<pieza>.step
    # y FreeCAD en Windows no abre rutas de más de 260 caracteres. Con el
    # nombre del encargo, dos piezas de la primera corrida no se construyeron.
    salida = _workspace(raiz, env) / "banco" / f"{dt.datetime.now():%m%d-%H%M}"
    resultados, fallos = {}, {}
    for i, e in enumerate(encargos, 1):
        print(f"[{nombre}] banco: {e.nombre} (carpeta {i:02d})…", flush=True)
        resultados[e.nombre], fallo = correr(e, salida / f"{i:02d}", orden_del_banco(e.obra),
                                             _freecadcmd(env),
                                             dict(os.environ), material,
                                             elegir_laminador(raiz, env))
        if fallo:
            fallos[e.nombre] = fallo
    modelo = env.get("DEEPSEEK_MODEL", "deepseek")
    texto = informe(resultados, modelo=modelo, fallos=fallos)
    (salida / "banco.md").write_text(texto, encoding="utf-8")
    print(texto)
    print(f"[{nombre}] informe en {salida / 'banco.md'}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="intelliprint")
    sub = parser.add_subparsers(dest="comando", required=True)
    nuevo = sub.add_parser("new", help="empezar un proyecto")
    nuevo.add_argument("peticion", nargs="+")
    reanudar = sub.add_parser("resume", help="reanudar un proyecto interrumpido")
    reanudar.add_argument("proyecto")
    sub.add_parser("bot", help="atender peticiones por Telegram (F5.6 (telegram))")
    anim = sub.add_parser("animar", help="rehacer el ensamble y la animación de un proyecto ya diseñado")
    anim.add_argument("carpeta")
    proy = sub.add_parser("proyectos", help="listar proyectos y ordenar el workspace")
    proy.add_argument("--archivar", action="store_true",
                      help="mover lo no aprobado a workspace/archivo (no borra nada)")
    meca = sub.add_parser("mecanismo", help="diseñar un mecanismo y ver su ensamble animado")
    meca.add_argument("peticion", nargs="+",
                      help='el mecanismo en texto, o "biela-manivela" con --carrera')
    meca.add_argument("--archivo", action="store_true",
                      help="la petición es la ruta de un archivo de texto")
    meca.add_argument("--carrera", type=float, help="solo biela-manivela: carrera, mm")
    meca.add_argument("--carpeta", help="carpeta del proyecto (por defecto, una nueva en workspace)")
    meca.add_argument("--continuar", action="store_true",
                      help="seguir un proyecto fallido: parte de su último diseño y del motivo")
    meca.add_argument("--referencia", action="store_true",
                      help="usar las recetas fijas de la disposición en vez del modelo")
    # F5.2 (adjuntos). No se llama --referencia porque ese nombre ya era de la
    # disposición fija de la biela-manivela.
    meca.add_argument("--adjunto", action="append", default=[], metavar="IMAGEN|TEXTO|PROYECTO",
                      help="una referencia para el diseñador: una imagen, un texto o el id de "
                           "un proyecto que ya salió. Se puede repetir.")
    cal = sub.add_parser("calibrar", help="pieza de calibración de holguras (F2.18 (calibración))")
    acciones = cal.add_subparsers(dest="accion", required=True)
    acciones.add_parser("pieza", help="construir las piezas para imprimirlas")
    acciones.add_parser("barra", help="construir las dos barras de flexión (F2.21 (impresora))")
    res = acciones.add_parser(
        "resultados", help="apuntar qué encajó: manda sobre las holguras del perfil activo")
    for opcion, ayuda in (("--press", "holgura del primer agujero a presión"),
                          ("--slide", "holgura del primero deslizante"),
                          ("--clearance", "holgura del primero que gira libre"),
                          ("--m3-through", "agujero pasante M3, mm"),
                          ("--m3-selftap", "agujero de rosca directa M3, mm"),
                          ("--m3-insert", "agujero del inserto M3, mm")):
        res.add_argument(opcion, type=float, required=True, help=ayuda)
    pieza = sub.add_parser("pieza", help="diseñar una pieza suelta: propone el concepto y para; "
                                         "con el visto bueno de la web o Crafty, la modela")
    pieza.add_argument("peticion", nargs="+")
    pieza.add_argument("--archivo", action="store_true",
                       help="la petición es la ruta de un archivo de texto")
    pieza.add_argument("--carpeta", help="carpeta del proyecto (por defecto, una nueva)")
    # Lo que pasa JobStore a cualquier orden. Reanudar una pieza es volver a
    # hacerla en su carpeta; los adjuntos aún no los usa el flujo de piezas.
    pieza.add_argument("--continuar", action="store_true", help=argparse.SUPPRESS)
    pieza.add_argument("--aprobar-concepto", action="store_true",
                       help="dar por bueno el concepto y modelar sin parar (el banco)")
    pieza.add_argument("--adjunto", action="append", default=[], help=argparse.SUPPRESS)
    ob = sub.add_parser("obra", help="un proyecto por partes (F7.2 (desglose)): lo desglosa y "
                                     "diseña una pieza cada vez, parando a por tu visto bueno")
    ob.add_argument("peticion", nargs="+")
    ob.add_argument("--archivo", action="store_true",
                    help="la petición es la ruta de un archivo de texto")
    ob.add_argument("--carpeta", help="carpeta del proyecto (por defecto, una nueva)")
    ob.add_argument("--continuar", action="store_true", help=argparse.SUPPRESS)
    ob.add_argument("--adjunto", action="append", default=[], help=argparse.SUPPRESS)
    ob.add_argument("--banco", action="store_true",
                    help="solo el banco: la obra entera, con el visto bueno dado por él")
    banco = sub.add_parser("banco", help="pedir las piezas del banco y medir si salen usables "
                                         "(F6.1 (evaluación)); cuesta dinero")
    banco.add_argument("--solo", action="append", default=[], metavar="ENCARGO",
                       help="correr solo este encargo (se puede repetir)")
    banco.add_argument("--rejuzgar", metavar="CORRIDA",
                       help="volver a juzgar las piezas de una corrida ya hecha "
                            "(workspace/banco/<fecha>), sin pedirlas otra vez ni gastar modelo")
    banco.add_argument("--reanudar", metavar="CORRIDA",
                       help="seguir los backlogs de una corrida desde la pieza que falló "
                            "(con los mismos --solo que entonces) y juzgarla otra vez")
    perf = sub.add_parser("perfil", help="importar una calibración de laminado de eufyMake Studio")
    perf.add_argument("accion", choices=["importar"])
    perf.add_argument("resto", nargs=argparse.REMAINDER,
                      help="lo de python -m orchestrator.perfiles_laminado --help")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _parser()
    args = parser.parse_args(argv)

    raiz = _raiz()
    os.chdir(raiz)
    env = load_env(raiz / ".env")
    nombre = env.get("AGENT_NAME") or "Crafty"
    if args.comando == "mecanismo":
        _mecanismo(args, raiz, env, nombre)
        return
    if args.comando == "bot":
        _bot(raiz, env, nombre)
        return
    if args.comando == "animar":
        _animar(args, raiz, env, nombre)
        return
    if args.comando == "proyectos":
        _proyectos(args, raiz, env, nombre)
        return
    if args.comando == "calibrar":
        _calibrar(args, raiz, env, nombre)
        return
    if args.comando == "perfil":
        from orchestrator.perfiles_laminado import main as importar
        importar(args.resto)
        return
    if args.comando == "banco":
        _banco(args, raiz, env, nombre)
        return
    if args.comando == "pieza":
        _pieza(args, raiz, env, nombre)
        return
    if args.comando == "obra":
        _obra(args, raiz, env, nombre)
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
