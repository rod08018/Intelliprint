"""`intelliprint`: línea de comandos.

    intelliprint pieza "lo que quieres diseñar"
    intelliprint obra "un robot o un conjunto: varias piezas, una a una"

Las dos dan un paso y paran donde hace falta la persona (el concepto, el
desglose, el visto bueno de cada pieza). El estado está en la carpeta del
proyecto: volver a lanzar la orden con `--carpeta` sigue donde se quedó.
"""

import argparse
import json
import datetime as dt
import os
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path

from orchestrator.build import design_and_build
from orchestrator.config import load_env
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


_CLIENTES: list[tuple] = []
"""Cada cliente que se crea, con su papel: `_apuntar_gasto` mira las
llamadas de los que se crearon dentro de su bloque."""

_AGENTES = {"design": "diseño (requisitos, investigación)",
            "reason": "razonador (desglose, ingeniero, kit)"}


def _cliente(router: Router, env: dict, role: str = "design"):
    ref = router.for_role(role)
    if ref.provider == "deepseek":
        cliente = DeepSeekClient(api_key=env["DEEPSEEK_API_KEY"], model=ref.model)
        _CLIENTES.append((cliente, role))
        return cliente
    sys.exit(
        f"el perfil {router.profile_name!r} usa {ref.provider}/{ref.model}, y el "
        "cliente de Ollama todavía no existe: llega con la migración (F0.11 (migrar))."
    )


@contextmanager
def _apuntar_gasto(raiz: Path, carpeta: Path, etapa: str, backlog: bool = False):
    """Suma al coste de `carpeta` las llamadas de los clientes creados dentro
    del bloque, salga como salga: un paso que se para a medias también gastó.
    Las piezas y los backlogs no dejaban `design_cost.md`; la ronda del
    pan-tilt del banco (1110-0313) no pudo decir cuánto costó (2026-11-10).

    `backlog`: `carpeta` es la de un backlog entero, y su tope es el suyo
    (50 USD, decidido por el usuario el 2026-11-11), no el de una pieza. Cada
    pieza del backlog sigue teniendo además el de una pieza, en su nodo."""
    import yaml

    from orchestrator.llm.cost import (TOPE_DE_BACKLOG, TOPE_DE_PIEZA, Presupuesto,
                                       PresupuestoAgotado)

    def presupuesto_de_hoy():
        return Presupuesto.from_config(yaml.safe_load(
            (raiz / "config" / "models.yaml").read_text(encoding="utf-8")),
            backlog=backlog).continuar(carpeta)

    # F5.12 (tope): antes de gastar más se mira lo que el proyecto ya lleva.
    # El tope lo pone el usuario y solo lo comprobaba el flujo de
    # mecanismos: una pieza o un backlog podían pasarse sin que nada los
    # parara, con la web diciendo «hasta 5 USD». Se mira al empezar cada paso
    # —el plan, cada pieza—, así que un proyecto se pasa como mucho en lo que
    # cuesta un paso.
    try:
        presupuesto_de_hoy().comprobar()
    except PresupuestoAgotado as tope:
        clave = TOPE_DE_BACKLOG if backlog else TOPE_DE_PIEZA
        sys.exit(f"✗ {tope} El tope está en `escalation.{clave}` de config/models.yaml.")

    desde = len(_CLIENTES)
    try:
        yield
    finally:
        nuevos = _CLIENTES[desde:]
        if any(c.llamadas for c, _ in nuevos):
            presupuesto = presupuesto_de_hoy()
            presupuesto.etapa(etapa)
            for c, rol in nuevos:
                presupuesto.vigila(c, _AGENTES.get(rol, rol))
            presupuesto.escribir(carpeta)


CONSTRUCCIONES_KIT = 5


def _disenar_con_kit(raiz: Path, env: dict, cliente):
    """Las piezas se dibujan con el kit (F5.18 (kit)): el catálogo de
    generadores no sabía hacer una cartela, un hexágono ni un chaflán."""
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
            # F9.5 (parcial): la pieza de un backlog que gira se mueve contra
            # lo ya construido con la misma holgura que su conjunto.
            return "\n".join(defectos_de_la_pieza(
                spec.requisitos, resultado, Path(carpeta) / f"{part}.step", freecad,
                material, componentes, pared_min, agujeros,
                holgura_al_moverse_mm=_perfil(raiz, env).impresora.fit_mm("slide") / 2)) or None

        # F9.4 (canal): en un backlog, las uniones del plan están en la
        # carpeta del nodo (`carpeta` es `<nodo>/parts/<pieza>`).
        from orchestrator.obra import uniones_para_el_prompt
        uniones = uniones_para_el_prompt(Path(carpeta).parent.parent)
        return design_and_build(
            disenador, spec_to_task(spec, concepto, uniones).brief, None, carpeta,
            freecadcmd=freecad, part=part, request=spec.request, perfil=disenador.perfil,
            max_construcciones=CONSTRUCCIONES_KIT, check=requisitos_medidos,
            entregar_mejor=True, partida=partida,
        )
    return disenar


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


def _animar(args, raiz: Path, env: dict, nombre: str) -> None:
    """Vuelve a mover los conjuntos ya verificados de un backlog y deja su
    animación: no vuelve a diseñar ni a gastar modelo."""
    from orchestrator import obra

    carpeta = Path(args.carpeta)
    if not obra.es_obra(carpeta):
        # Los mecanismos que ya hay conservan la animación que se les hizo;
        # lo que la rehacía se fue con su flujo (F9.13 (limpieza)).
        sys.exit(f"{carpeta.name} no es un backlog: solo se animan los conjuntos de un backlog")
    _animar_obra(carpeta, raiz, env, nombre)


def _animar_obra(carpeta: Path, raiz: Path, env: dict, nombre: str) -> None:
    """Vuelve a mover cada conjunto ya verificado, ahora con su animación
    (F7.6 (animacion)). Las obras verificadas antes no tenían ninguna."""
    from orchestrator import conjunto, obra
    from orchestrator.build import carpeta_libre
    holgura = _perfil(raiz, env).impresora.fit_mm("slide") / 2
    for i, estado in obra.estados(carpeta).items():
        if estado not in ("verificado", "con choques"):
            continue
        anterior = carpeta / obra.NODOS / i / conjunto.VERIFICACION
        # Copia y no mueve: si se corta a medias, el conjunto sigue verificado
        # (pasó con el pan-tilt del banco, 2026-11-10).
        shutil.copy2(anterior, carpeta_libre(anterior.with_name("verificacion-anterior.json")))
        v = conjunto.verificar_conjunto(carpeta, i, _freecadcmd(env), min_gap_mm=holgura)
        print(f"[{nombre}] «{i}»: {'se mueve sin chocar' if v['ok'] else 'choca al moverse'}")
        print(f"  animación: {carpeta / obra.NODOS / i / 'animation.gif'}")


def _estudio(args, raiz: Path, env: dict, nombre: str) -> None:
    """El estudio de movimientos (F7.10 (estudio)) de cada conjunto que ya
    se mueve: lo que pesa, si aguantan los servos, si vuelca, el alcance y
    los tiempos. La resistencia del material la mide FreeCAD."""
    from orchestrator import estudio, obra
    carpeta = Path(args.carpeta)
    for i, estado in obra.estados(carpeta).items():
        if estado not in ("verificado", "con choques"):
            continue
        e = estudio.escribir_estudio(carpeta, i, _freecadcmd(env), raiz)
        c = e["carga_max"]
        print(f"[{nombre}] «{i}»: carga máxima "
              + (f"{c['g']:.1f} g (la limita el {c['limita']})" if c["g"] is not None else "sin calcular"))
        for s in e["servos"]:
            ok = {True: "aguanta", False: "NO aguanta"}.get(s.get("aguanta"), "sin datos de par")
            print(f"  {s['nombre']}: {s['servo']} {ok}")
        print(f"  {carpeta / obra.NODOS / i / 'estudio.md'}")


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
    lanza desde la web o Telegram ya confirmó al pedirla."""
    texto = " ".join(args.peticion)
    peticion = Path(texto).read_text(encoding="utf-8") if args.archivo else texto
    carpeta = (Path(args.carpeta) if args.carpeta else _workspace(raiz, env) / "projects"
               / f"{dt.datetime.now():%Y-%m-%d-%H%M%S}-{nombre_corto(peticion.splitlines()[0], 40)}")
    with _apuntar_gasto(raiz, carpeta, "pieza"):
        _hacer_pieza(args, peticion, carpeta, raiz, env, nombre)


def _hacer_pieza(args, peticion: str, carpeta: Path, raiz: Path, env: dict, nombre: str) -> None:
    from orchestrator.agents.requirements import RequirementsAgent
    from orchestrator.pieza import APROBADO, concebir_pieza, disenar_pieza

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
                            disenar=_disenar_con_kit(raiz, env, cliente))
    if informe.resuelto:
        print(f"[{nombre}] ✓ {informe.titulo}: "
              f"{' x '.join(f'{v:g}' for v in informe.bbox_mm)} mm")
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
        from orchestrator.plan import validar_plan
        # F9.3 (planificador): el plan se hace con lo que la impresora sabe
        # taladrar, y lo que no tabule se le enseña a la persona como aviso.
        agujeros = _perfil(raiz, env).datos.get("holes", {})
        with latir(carpeta), _apuntar_gasto(raiz, carpeta, "desglose", backlog=True):
            try:
                desglose = DesglosadorAgent(_cliente(router, env, "reason"),
                                            reserva=cliente).desglosar(
                    peticion, agujeros=agujeros, anterior=obra.plan_anterior(carpeta))
            except ValueError as e:
                (carpeta / "rounds.json").write_text(json.dumps(
                    [{"number": 1, "title": "desglose", "feedback": f"el desglose no salió: {e}",
                      "plan": None}], ensure_ascii=False), encoding="utf-8")
                sys.exit(f"[{nombre}] ✗ el desglose no salió: {e}")
            avisos = validar_plan(desglose, agujeros)[1]
            obra.guardar(carpeta, desglose, por="desglosador", avisos=avisos)
        print(obra.presentar(desglose, avisos), flush=True)
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
    if estado == "por revalidar":
        # F9.9 (revalidar): se corrigió algo de lo que esta pieza tiene
        # debajo. Se comprueba contra la ficha nueva, sin modelo, y solo si
        # deja de valer se corrige. Antes se archivaba sin mirar.
        from orchestrator import revalidar
        print(f"[{nombre}] «{nombre_nodo}»: se comprueba contra lo que se corrigió…",
              flush=True)
        try:
            with latir(carpeta):
                motivos = revalidar.resolver(carpeta, nodo, _freecadcmd(env),
                                             _perfil(raiz, env).datos["resistencia"])
        except (RuntimeError, ValueError) as fallo:
            # Sin medir no se da por buena ni se tira: se queda como está.
            sys.exit(f"[{nombre}] ✗ «{nombre_nodo}» no se pudo revalidar: {fallo}")
        if motivos:
            print("\n".join(f"  - {m}" for m in motivos), flush=True)
            print(f"[{nombre}] «{nombre_nodo}» ya no vale tal cual: se corrige partiendo "
                  "de ella", flush=True)
        else:
            print(f"[{nombre}] ✓ «{nombre_nodo}» sigue valiendo: no se toca", flush=True)
        # No hay nada que decidir: se sigue con lo que toque, en esta misma
        # orden. Parar aquí dejaría a la persona delante de un «Empezar».
        return _paso_de_obra(carpeta, peticion, raiz, env, nombre)
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
        # F7.10 (estudio): con las piezas en su sitio, lo que aguanta y lo
        # que vuelca. Que falle no deshace la verificación: se dice y sigue.
        try:
            from orchestrator.estudio import escribir_estudio
            c = escribir_estudio(carpeta, nodo, _freecadcmd(env), raiz)["carga_max"]
            if c["g"] is not None:
                print(f"  carga máxima {c['g']:.0f} g (la limita el {c['limita']})", flush=True)
        except Exception as fallo:  # noqa: BLE001
            print(f"  sin estudio de movimientos: {fallo}", flush=True)
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
    # F9.4 (canal): lo que el plan decidió de este nodo, aparte de su
    # petición. Lo leen el ingeniero, el diseñador y las medidas.
    os.environ["INTELLIPRINT_UNIONES"] = str(obra.escribir_uniones(carpeta, nodo))
    print(f"[{nombre}] nodo «{nombre_nodo}» ({nodo})", flush=True)
    # El gasto de la pieza queda en su nodo y, sumado, en la obra entera.
    with latir(carpeta), _apuntar_gasto(raiz, carpeta, f"pieza «{nombre_nodo}»",
                                         backlog=True):
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
        # Al lado del informe original y de los rejuicios anteriores, sin pisar
        # ninguno: cada uno es la evidencia de lo que medía el juez de ese día.
        destino = carpeta_libre(corrida / "banco_rejuzgado.md")
        destino.write_text(texto, encoding="utf-8")
        print(texto)
        print(f"[{nombre}] informe en {destino}")
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
    anim = sub.add_parser("animar", help="volver a mover los conjuntos ya verificados de un "
                                         "backlog, con su animación")
    anim.add_argument("carpeta")
    estu = sub.add_parser("estudio", help="estudio de movimientos: carga, servos, vuelco, alcance y tiempos")
    estu.add_argument("carpeta")
    proy = sub.add_parser("proyectos", help="listar proyectos y ordenar el workspace")
    proy.add_argument("--archivar", action="store_true",
                      help="mover lo no aprobado a workspace/archivo (no borra nada)")
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
    # Lo pasa JobStore al relanzar. Reanudar una pieza es volver a hacerla en
    # su carpeta, así que no cambia nada.
    pieza.add_argument("--continuar", action="store_true", help=argparse.SUPPRESS)
    pieza.add_argument("--aprobar-concepto", action="store_true",
                       help="dar por bueno el concepto y modelar sin parar (el banco)")
    ob = sub.add_parser("obra", help="un proyecto por partes (F7.2 (desglose)): lo desglosa y "
                                     "diseña una pieza cada vez, parando a por tu visto bueno")
    ob.add_argument("peticion", nargs="+")
    ob.add_argument("--archivo", action="store_true",
                    help="la petición es la ruta de un archivo de texto")
    ob.add_argument("--carpeta", help="carpeta del proyecto (por defecto, una nueva)")
    ob.add_argument("--continuar", action="store_true", help=argparse.SUPPRESS)
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
    if args.comando == "animar":
        _animar(args, raiz, env, nombre)
        return
    if args.comando == "estudio":
        _estudio(args, raiz, env, nombre)
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


if __name__ == "__main__":
    main()
