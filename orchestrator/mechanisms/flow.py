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
from orchestrator.mechanisms.run import MechanismReport, build_mechanism
from orchestrator.mechanisms.spec_layout import SpecLayout

MAX_RONDAS = 3


class Round(BaseModel):
    number: int
    title: str
    feedback: str = ""
    """Lo que falló en esta ronda y se le devolvió al agente ("" si nada)."""


class FlowReport(BaseModel):
    rounds: list[Round]
    final: MechanismReport | None
    spec_path: str

    @property
    def ok(self) -> bool:
        return self.final is not None and self.final.ok and not self.rounds[-1].feedback


def design_mechanism(
    peticion: str,
    mechanism_agent,
    part_agent,
    carpeta: Path,
    freecadcmd: str,
    *,
    min_gap_mm: float,
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
                    part=p.name, request=p.brief,
                    check=lambda r, nombre=p.name: layout.check_bounds(nombre, r),
                )
                (destino / "recipe.json").write_text(receta.model_dump_json(indent=2), encoding="utf-8")
                (destino / "brief.md").write_text(p.brief + "\n", encoding="utf-8")
                hechas[p.name] = clave
            except ConstruccionFallida as e:
                hechas.pop(p.name, None)
                fallos.append(f"- la pieza «{p.name}» no se pudo dibujar como la describes: {e.motivo}")

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
            feedback = "\n".join(f"- {linea}" for linea in final.collision_summary())

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
    (carpeta / "rounds.json").write_text(
        json.dumps([r.model_dump() for r in rondas], indent=2, ensure_ascii=False), encoding="utf-8")
    return FlowReport(rounds=rondas, final=final, spec_path=str(spec_path))
