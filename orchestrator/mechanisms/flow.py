"""Flujo completo de un mecanismo desde la petición en texto (F3.15 (mecanismos)).

1. El Mechanism Designer propone el mecanismo (`MechanismSpec`). Fórmulas y
   requisitos medibles se comprueban ya en su bucle de reintento.
2. El Part Designer dibuja cada pieza desde su enunciado; cada pieza se
   compara con la caja que declaró el Mechanism Designer.
3. Barrido de choques y contactos en todo el recorrido.
4. Si algo falla, vuelve al Mechanism Designer con el motivo concreto
   (hasta `max_rounds`). Las piezas que no cambian no se vuelven a pedir.

El ensamble se guarda SIEMPRE que haya piezas para montarlo: cuando falla
es cuando más falta hace abrirlo.
"""

import json
import re
from pathlib import Path

from pydantic import BaseModel

from mech_toolkit.generators import CATALOGO
from orchestrator.build import ConstruccionFallida, design_and_build
from orchestrator.llm.cost import PresupuestoAgotado
from orchestrator.llm.structured import SalidaInvalida
from orchestrator.mechanisms.checks import (
    joint_axis_problems, mechanism_problems, stop_problems)
from orchestrator.mechanisms.contact import SinApoyo, block_problems, solve_contacts
from orchestrator.mechanisms.run import MechanismReport, build_mechanism
from orchestrator.mechanisms.spec_layout import SpecLayout
from orchestrator.schemas.review import ReviewReport

def _guardar_rechazados(destino: Path, intentos: list[dict]) -> None:
    """Cada propuesta que el validador rechazó, tal como la escribió el
    modelo, y por qué. Archivar no es borrar: sin esto, un proyecto parado
    por especificaciones inválidas no deja ni rastro de qué se propuso
    (pasó con el trinquete del 2026-09-20)."""
    if not intentos:
        return
    destino.mkdir(parents=True, exist_ok=True)
    motivos = ["# Propuestas rechazadas", ""]
    for i in intentos:
        n, respuesta = i["intento"], i["respuesta"]
        if respuesta is not None:
            try:
                json.loads(respuesta)
                nombre = f"intento_{n}.json"
            except ValueError:
                nombre = f"intento_{n}.txt"
            (destino / nombre).write_text(respuesta, encoding="utf-8")
        else:
            nombre = "(cortado: no llegó a responder)"
        quien = " · respondió el modelo de reserva, sin pensamiento" if i.get("reserva") else ""
        motivos += [f"## Intento {n} — {nombre}{quien}", "", "```", i["error"].strip(), "```", ""]
    (destino / "motivos.md").write_text("\n".join(motivos), encoding="utf-8")


def huella_de_fallo(feedback: str) -> str:
    """El fallo sin sus números: "se queda a 9.38 mm" y "se queda a 0.32 mm"
    son el mismo muro. Sin esto el sistema quema rondas creyendo que avanza."""
    return re.sub(r"[-+]?\d+(?:[.,]\d+)?", "#", feedback).strip()


def huella_de_plan(plan: dict | None, nombres=()) -> str:
    """La IDEA del plan: QUÉ PIEZAS toca. Los nombres de las piezas son
    identificadores estables; la redacción no. Comparar el texto literal no
    servía —"subo el brazo" y "elevo el brazo" nunca coinciden— y el atasco
    no saltaba nunca.

    Sin lista de nombres se cae a las palabras del plan, que es mejor que nada.
    """
    if not plan:
        return ""
    import unicodedata

    texto = " ".join(str(plan.get(c, "")) for c in ("causa", "cambio"))
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    tocadas = {n for n in nombres if n.lower() in texto}
    if tocadas:
        return " ".join(sorted(tocadas))
    return " ".join(sorted({w for w in re.findall(r"[a-z_]{4,}", texto)}))


MAX_RONDAS = 40
"""Red de seguridad, no el criterio: el sistema itera HASTA QUE el mecanismo
funciona. Lo que lo detiene es el presupuesto (F5.12 (tope)) o atascarse
repitiendo el mismo fallo; en ambos casos se pregunta al usuario en vez de
rendirse en silencio."""

REPETICIONES_PARA_ATASCO = 3
"""Veces que puede repetirse el MISMO fallo antes de darlo por atasco. La
segunda vez se le avisa al agente de que se está repitiendo."""

MAX_RONDAS_DE_REVISION = 2
"""Cuántas veces se le devuelven al diseñador los incumplimientos que ve el
revisor. Su juicio no es aritmético (ADR-003): insistir sin límite puede no
converger nunca."""


class Round(BaseModel):
    number: int
    title: str
    feedback: str = ""
    plan: dict | None = None
    """Lo que el agente dijo que iba a cambiar en esta ronda y por qué."""
    """Lo que falló en esta ronda y se le devolvió al agente ("" si nada)."""


class FlowReport(BaseModel):
    rounds: list[Round]
    stopped_because: str = "resuelto"
    """resuelto | atascado | presupuesto | rondas. Lo que detuvo el bucle."""
    spent_usd: float = 0.0
    final: MechanismReport | None
    spec_path: str
    review: ReviewReport | None = None
    """Informe del Design Reviewer: requisito por requisito. No aprueba
    nada (ADR-003); marca lo que nadie ha verificado."""

    @property
    def ok(self) -> bool:
        return (self.final is not None and self.final.ok
                and bool(self.rounds) and not self.rounds[-1].feedback)


def _retomar(carpeta: Path) -> tuple[str, str] | None:
    """El diseño anterior y lo último que falló, para no empezar de cero.

    Reintentar sin esto tira a la basura lo aprendido: el modelo vuelve a
    proponer desde la nada y repite los mismos fallos."""
    spec = carpeta / "mechanism.json"
    rondas = carpeta / "rounds.json"
    if not spec.exists() or not rondas.exists():
        return None
    previas = json.loads(rondas.read_text(encoding="utf-8"))
    motivo = next((r["feedback"] for r in reversed(previas) if r.get("feedback")), "")
    if not motivo:
        return None
    return (spec.read_text(encoding="utf-8"), motivo)


def measurements(spec, layout, final: MechanismReport) -> list[str]:
    """Lo que el CÓDIGO comprobó sobre la geometría ya construida. Es lo
    único que el revisor puede tomar como dato."""
    lineas = [
        (f"se generaron la animación del ciclo ({Path(final.animation).name}) y el ensamble "
         f"({Path(final.assembly).name}), que el usuario puede abrir en FreeCAD"
         if final.animation else f"se generó el ensamble ({Path(final.assembly).name})"),
        f"barrido de {len(final.angles)} posiciones del ciclo con hueco mínimo "
        f"{final.min_gap_mm:g} mm: " + ("ninguna pieza toca a otra indebidamente"
                                        if final.ok else f"{len(final.collisions)} incumplimientos"),
        *(f"choque o separación: {linea}" for linea in final.collision_summary()),
        *(f"requisito medido con la cinemática — {n}" for n in layout.notes()
          if n.startswith("requisito")),
        *(f"contacto verificado en todo el ciclo entre «{r.a}» y «{r.b}» (≤ {r.max_gap_mm:g} mm)"
          for r in spec.rules if r.kind == "contact"),
        *(f"tope verificado: «{t.a}» y «{t.b}» se tocan en {spec.driver.name} = {t.at:g} "
          "y más allá se atravesarían" for t in spec.stops),
        *(f"bloqueo verificado: «{b.against}» impide que «{b.body}» se mueva {b.delta:g}"
          for b in spec.blocks),
        *(f"apoyo resuelto con la geometría real, no con una fórmula: «{b.name}» sobre "
          f"«{b.joint.rest_on.target}»" for b in spec.bodies if b.joint and b.joint.rest_on),
    ]
    # Sin el filtro por `parent`: desde la ronda 12 del trinquete el agente
    # colgó la rueda de la base y este aviso dejó de salir, justo cuando más
    # falta hacía.
    sin_verificar = [b.name for b in spec.bodies
                     if b.joint and b.joint.value is not None]
    if sin_verificar:
        lineas.append(
            "movimiento IMPUESTO por fórmula (nadie comprueba que lo cause el mecanismo): "
            + ", ".join(f"«{n}»" for n in sin_verificar))
    return lineas


def _evidencias(carpeta, spec, rondas, parada, final, layout, peticion, gasto,
                freecadcmd, log) -> None:
    """Deja el parte con evidencias para que la persona decida con datos."""
    from orchestrator.mechanisms.evidence import escribir_bloqueo, render_frame

    imagenes = []
    try:
        if final is not None and final.collisions:
            from orchestrator.animation import tessellate

            peor = min(final.collisions, key=lambda c: c.gap_mm)
            mallas = tessellate({n: Path(p) for n, p in final.parts.items()},
                                layout.pins(), freecadcmd)
            nombre = f"fallo_t{peor.angle:g}.png"
            render_frame(mallas, layout.poses(peor.angle), carpeta / nombre,
                         title=f"{peor.a} / {peor.b} · {spec.driver.name} = {peor.angle:g}",
                         resaltar={peor.a, peor.b})
            imagenes.append(nombre)
    except Exception as e:  # una imagen que falla no puede tapar el parte
        log(f"    (no se pudo dibujar la evidencia: {e})")
    planes = [{"ronda": r.number, **(r.plan or {})} for r in rondas if r.plan]
    escribir_bloqueo(carpeta, titulo=spec.title, parada=parada, gasto_usd=gasto,
                     rondas=[r.model_dump() for r in rondas], imagenes=imagenes,
                     peticion=peticion, planes=planes)


def design_mechanism(
    peticion: str,
    mechanism_agent,
    part_agent,
    carpeta: Path,
    freecadcmd: str,
    *,
    min_gap_mm: float,
    reviewer=None,
    max_rounds: int = MAX_RONDAS,
    continuar: bool = False,
    presupuesto=None,
    animar: bool = True,
    log=print,
) -> FlowReport:
    carpeta = Path(carpeta)
    (carpeta / "request.md").parent.mkdir(parents=True, exist_ok=True)
    (carpeta / "request.md").write_text(peticion + "\n", encoding="utf-8")
    hechas: dict[str, tuple] = {}
    rondas: list[Round] = []
    rechazo = _retomar(carpeta) if continuar else None
    spec = None
    final = None
    spec_path = carpeta / "mechanism.json"

    motivos_vistos: dict[str, int] = {}
    parada = "rondas"
    review = None
    revisiones = 0

    for n in range(1, max_rounds + 1):
        if presupuesto is not None:
            try:
                presupuesto.comprobar()
            except PresupuestoAgotado as e:
                log(f"    ✋ {e}")
                parada = "presupuesto"
                break
        if presupuesto is not None:
            presupuesto.etapa(f"ronda {n} · diseño del mecanismo")
            # El coste se escribe por el camino: en un proyecto de 40 minutos
            # hay que poder mirar cuánto llevas gastado sin esperar al final.
            presupuesto.escribir(carpeta)
        log(f"  ronda {n}: el Mechanism Designer propone el mecanismo…")
        try:
            spec = mechanism_agent.design(peticion, rechazo=rechazo)
        except SalidaInvalida as e:
            # Tres propuestas seguidas sin salida válida: se para y se dice,
            # en vez de tumbar el proyecto con un traceback.
            log(f"    ✋ el diseñador no consiguió una propuesta válida: {e}")
            _guardar_rechazados(carpeta / "rondas" / str(n) / "rechazados", e.intentos)
            rondas.append(Round(number=n, title="sin propuesta válida", feedback=str(e)))
            parada = "atascado"
            break
        texto_spec = spec.model_dump_json(indent=2)
        (carpeta / "rondas" / str(n)).mkdir(parents=True, exist_ok=True)
        (carpeta / "rondas" / str(n) / "mechanism.json").write_text(texto_spec, encoding="utf-8")
        spec_path.write_text(texto_spec, encoding="utf-8")
        layout = SpecLayout(spec)
        log(f"    «{spec.title}»: {len(spec.parts)} piezas, {len(spec.pins)} pasadores/ejes")

        # Antes de gastar FreeCAD: lo que el agente no puede dejar sin
        # verificar se ve en su propia declaración.
        fallos = [f"- {x}" for x in mechanism_problems(spec, min_gap_mm)]
        for p in [] if fallos else spec.parts:
            clave = (p.brief, tuple(p.bbox_min), tuple(p.bbox_max))
            destino = carpeta / "parts" / p.name
            if hechas.get(p.name) == clave and (destino / f"{p.name}.step").exists():
                continue
            if presupuesto is not None:
                presupuesto.etapa(f"ronda {n} · pieza «{p.name}»")
            log(f"    el Part Designer dibuja «{p.name}»…")
            try:
                receta, _ = design_and_build(
                    part_agent, p.brief, CATALOGO, destino, freecadcmd=freecadcmd,
                    # Sin trazabilidad (F1.16 (trazabilidad)): el enunciado trae cotas
                    # DERIVADAS ("la punta queda a 45 mm" de un enlace de 39) y la
                    # guardia obligaba a meterlas como parámetro (fallo real en el
                    # trinquete). Aquí manda la caja envolvente, que es más fuerte.
                    part=p.name,
                    check=lambda r, nombre=p.name: layout.check_bounds(nombre, r),
                    check_es_de_la_caja=True,
                )
                (destino / "recipe.json").write_text(receta.model_dump_json(indent=2), encoding="utf-8")
                (destino / "brief.md").write_text(p.brief + "\n", encoding="utf-8")
                hechas[p.name] = clave
            except (ConstruccionFallida, SalidaInvalida) as e:
                hechas.pop(p.name, None)
                motivo = getattr(e, "motivo", str(e))
                fallos.append(f"- la pieza «{p.name}» no se pudo dibujar como la describes: {motivo}")

        if not fallos:
            steps = {p.name: carpeta / "parts" / p.name / f"{p.name}.step" for p in spec.parts}
            fallos = [f"- {x}" for x in joint_axis_problems(spec, steps, freecadcmd)]

        if not fallos and any(b.joint and b.joint.rest_on for b in spec.bodies):
            # Las piezas que se apoyan encuentran su sitio en la geometría real
            # ANTES de barrer: su movimiento no lo decide una fórmula.
            log("    resolviendo apoyos por contacto…")
            try:
                solve_contacts(spec, layout.kin, steps, layout.pins(), freecadcmd, layout.frames())
            except SinApoyo as e:
                fallos = [f"- {e}"]
            else:
                # Ahora que los apoyos están resueltos, los requisitos que
                # dependían de ellos ya se pueden medir.
                try:
                    layout.kin.validate()
                except ValueError as e:
                    fallos = [f"- {e}"]

        if fallos:
            feedback = "\n".join(fallos)
        else:
            log("    ensamble y barrido del recorrido completo…")
            final = build_mechanism(
                layout, carpeta, freecadcmd, min_gap_mm=min_gap_mm,
                disenar=lambda nombre, c: None,  # ya dibujadas arriba
                animar=False,
            )
            feedback = "\n".join(f"- {linea}" for linea in (
                final.collision_summary()
                + stop_problems(spec, layout, steps, freecadcmd)
                + block_problems(spec, layout.kin, steps, layout.pins(), freecadcmd)))
            ejes = {x.name for x in spec.pins}
            atravesados = sorted({(c.a if c.b in ejes else c.b, c.b if c.b in ejes else c.a)
                                  for c in final.collisions
                                  if c.gap_mm < 0 and ({c.a, c.b} & ejes)})
            for pieza, eje in atravesados:
                feedback += (f"\n- «{eje}» atraviesa material de «{pieza}»: falta el agujero, "
                             "no está en el eje del pasador, o el pasador es demasiado largo "
                             "y se mete en otra pieza")

            # El juicio del revisor también es retroalimentación: un requisito
            # incumplido que solo se cuenta al final no lo corrige nadie.
            if not feedback and reviewer is not None and revisiones < MAX_RONDAS_DE_REVISION:
                if presupuesto is not None:
                    presupuesto.etapa(f"ronda {n} · revisión")
                log("    revisión del diseño frente a tu petición…")
                review = reviewer.review(peticion, spec, measurements(spec, layout, final))
                incumplidos = review.por_veredicto("no_cumple")
                if incumplidos:
                    revisiones += 1
                    feedback = "\n".join(
                        f"- requisito del usuario sin cumplir — {i.requirement}: {i.comment}"
                        for i in incumplidos)

        plan = spec.fix_plan.model_dump() if spec.fix_plan else None
        rondas.append(Round(number=n, title=spec.title, feedback=feedback, plan=plan))
        if not feedback:
            parada = "resuelto"
            break

        # ¿Se está repitiendo? Volver a proponer lo mismo no arregla nada.
        # El muro y la idea con la que se intenta tirarlo: repetir la misma
        # idea contra el mismo muro es atasco, aunque cambien los números.
        huella = huella_de_fallo(feedback) + "||" + huella_de_plan(
            plan, [b.name for b in spec.bodies])
        motivos_vistos[huella] = motivos_vistos.get(huella, 0) + 1
        repetido = motivos_vistos[huella]
        if repetido >= REPETICIONES_PARA_ATASCO:
            log("    ✋ atascado: el mismo fallo se repite y el diseño no avanza")
            parada = "atascado"
            break
        aviso = ("\n\nEste fallo YA te lo devolví antes y volviste a proponer lo mismo. "
                 "Cambia de enfoque: mueve piezas, cambia medidas o replantea el mecanismo."
                 if repetido > 1 else "")
        log(f"    ✗ vuelve al Mechanism Designer:\n{feedback}")
        rechazo = (texto_spec, feedback + aviso)

    if final is not None and animar and final.animation is None:
        # La animación, una vez y del último diseño montado. Al reescribir el
        # bucle este paso se perdió y los proyectos salían sin GIF: es lo
        # primero que mira el usuario, así que se hace pase lo que pase.
        log("    animación…")
        final = build_mechanism(layout, carpeta, freecadcmd, min_gap_mm=min_gap_mm,
                                disenar=lambda nombre, c: None, animar=True)

    if reviewer is not None and final is not None and review is None and spec is not None:
        if presupuesto is not None:
            presupuesto.etapa("revisión final")
        log("    revisión del diseño frente a tu petición…")
        review = reviewer.review(peticion, spec, measurements(spec, layout, final))
    if review is not None and spec is not None:
        (carpeta / "review.md").write_text(
            "\n".join([f"# Revisión: {spec.title}", "", review.summary, ""]
                      + [f"- **{i.verdict}** — {i.requirement}: {i.comment}" for i in review.items]),
            encoding="utf-8")
    if parada != "resuelto" and spec is not None:
        _evidencias(carpeta, spec, rondas, parada, final, layout, peticion,
                    presupuesto.gastado_usd() if presupuesto else 0.0, freecadcmd, log)
    if presupuesto is not None:
        # El coste se guarda SIEMPRE, también si el proyecto no salió: saber
        # en qué se fue el dinero es lo que deja decidir si vale la pena seguir.
        presupuesto.escribir(carpeta)
    (carpeta / "rounds.json").write_text(
        json.dumps([r.model_dump() for r in rondas], indent=2, ensure_ascii=False), encoding="utf-8")
    return FlowReport(rounds=rondas, final=final, spec_path=str(spec_path), review=review,
                      stopped_because=parada,
                      spent_usd=presupuesto.gastado_usd() if presupuesto else 0.0)
