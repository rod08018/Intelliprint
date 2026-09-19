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
from pathlib import Path

from pydantic import BaseModel

from mech_toolkit.generators import CATALOGO
from orchestrator.build import ConstruccionFallida, design_and_build
from orchestrator.llm.structured import SalidaInvalida
from orchestrator.mechanisms.checks import joint_axis_problems, stop_problems
from orchestrator.mechanisms.contact import SinApoyo, block_problems, solve_contacts
from orchestrator.mechanisms.run import MechanismReport, build_mechanism
from orchestrator.mechanisms.spec_layout import SpecLayout
from orchestrator.schemas.review import ReviewReport

MAX_RONDAS = 5
"""Cada ronda cuesta unos 4 minutos de modelo. Con 3 se quedaban a medias
diseños que iban por buen camino (el gato de tijera)."""


class Round(BaseModel):
    number: int
    title: str
    feedback: str = ""
    """Lo que falló en esta ronda y se le devolvió al agente ("" si nada)."""


class FlowReport(BaseModel):
    rounds: list[Round]
    final: MechanismReport | None
    spec_path: str
    review: ReviewReport | None = None
    """Informe del Design Reviewer: requisito por requisito. No aprueba
    nada (ADR-003); marca lo que nadie ha verificado."""

    @property
    def ok(self) -> bool:
        return self.final is not None and self.final.ok and not self.rounds[-1].feedback


def measurements(spec, layout, final: MechanismReport) -> list[str]:
    """Lo que el CÓDIGO comprobó sobre la geometría ya construida. Es lo
    único que el revisor puede tomar como dato."""
    lineas = [
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
    sin_verificar = [b.name for b in spec.bodies
                     if b.joint and b.joint.value is not None and b.parent is None]
    if sin_verificar:
        lineas.append(
            "movimiento IMPUESTO por fórmula (nadie comprueba que lo cause el mecanismo): "
            + ", ".join(f"«{n}»" for n in sin_verificar))
    return lineas


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
    animar: bool = True,
    log=print,
) -> FlowReport:
    carpeta = Path(carpeta)
    (carpeta / "request.md").parent.mkdir(parents=True, exist_ok=True)
    (carpeta / "request.md").write_text(peticion + "\n", encoding="utf-8")
    hechas: dict[str, tuple] = {}
    rondas: list[Round] = []
    rechazo = None
    final = None
    spec_path = carpeta / "mechanism.json"

    for n in range(1, max_rounds + 1):
        log(f"  ronda {n}: el Mechanism Designer propone el mecanismo…")
        spec = mechanism_agent.design(peticion, rechazo=rechazo)
        texto_spec = spec.model_dump_json(indent=2)
        (carpeta / "rondas" / str(n)).mkdir(parents=True, exist_ok=True)
        (carpeta / "rondas" / str(n) / "mechanism.json").write_text(texto_spec, encoding="utf-8")
        spec_path.write_text(texto_spec, encoding="utf-8")
        layout = SpecLayout(spec)
        log(f"    «{spec.title}»: {len(spec.parts)} piezas, {len(spec.pins)} pasadores/ejes")

        fallos = []
        for p in spec.parts:
            clave = (p.brief, tuple(p.bbox_min), tuple(p.bbox_max))
            destino = carpeta / "parts" / p.name
            if hechas.get(p.name) == clave and (destino / f"{p.name}.step").exists():
                continue
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

        ultima = n == max_rounds
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

        rondas.append(Round(number=n, title=spec.title, feedback=feedback))
        if not feedback or ultima:
            break
        log(f"    ✗ vuelve al Mechanism Designer:\n{feedback}")
        rechazo = (texto_spec, feedback)

    if final is not None and animar and not fallos:
        # La animación, una vez y del último diseño, que es el que se montó.
        log("    animación…")
        final = build_mechanism(layout, carpeta, freecadcmd, min_gap_mm=min_gap_mm,
                                disenar=lambda nombre, c: None, animar=True)
    review = None
    if reviewer is not None and final is not None:
        log("    revisión del diseño frente a tu petición…")
        review = reviewer.review(peticion, spec, measurements(spec, layout, final))
        (carpeta / "review.md").write_text(
            "\n".join([f"# Revisión: {spec.title}", "", review.summary, ""]
                      + [f"- **{i.verdict}** — {i.requirement}: {i.comment}" for i in review.items]),
            encoding="utf-8")
    (carpeta / "rounds.json").write_text(
        json.dumps([r.model_dump() for r in rondas], indent=2, ensure_ascii=False), encoding="utf-8")
    return FlowReport(rounds=rondas, final=final, spec_path=str(spec_path), review=review)
