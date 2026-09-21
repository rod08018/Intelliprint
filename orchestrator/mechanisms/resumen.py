"""Cada ronda del diseño de un mecanismo, como DATO (F5.5 (web)).

La interfaz enseña en qué ronda va un proyecto, qué falló, qué dijo el
diseñador que iba a cambiar y cuánto se acercó a lo pedido. Hasta ahora
nada de eso existía mientras el trabajo corría: `rounds.json` se escribía al
terminar, y las mediciones acababan convertidas en frases para el revisor.
Aquí se guardan como números, y en el momento.

Todo lo de este resumen es aritmética del código —medido, contado—, no un
juicio (ADR-003). El juicio del revisor va aparte, en `review.json`.
"""

import json
from pathlib import Path


def requisitos_medidos(spec, layout) -> list[dict]:
    """Cada requisito del mecanismo: lo que se pidió y lo que se midió con
    la cinemática, en el mismo recorrido que ve el revisor."""
    frames = layout.frames()
    filas = []
    for c in spec.checks:
        fila = {"descripcion": c.description, "magnitud": c.measure,
                "esperado": c.expected, "tolerancia": c.tolerance}
        try:
            medido = layout.kin.measure(c, frames)
        except ValueError as e:
            # Un requisito que depende de un apoyo no se puede medir hasta que
            # el apoyo se resuelve en la geometría. Se dice, no se inventa.
            fila.update(medido=None, desviacion=None, cumple=None, nota=str(e))
        else:
            desviacion = medido - c.expected
            fila.update(medido=round(medido, 4), desviacion=round(desviacion, 4),
                        cumple=abs(desviacion) <= c.tolerance)
        filas.append(fila)
    return filas


def resumen_de_ronda(numero: int, spec, layout, final, feedback: str,
                     rechazados: int = 0) -> dict:
    """`final` es el montaje de ESTA ronda, o None si no llegó a montarse
    (una pieza que no se pudo dibujar, un apoyo sin resolver). Nunca el de
    una ronda anterior: enseñarlo como suyo sería mentir."""

    return {
        "ronda": numero,
        "titulo": spec.title,
        "plan": spec.fix_plan.model_dump() if spec.fix_plan else None,
        "feedback": feedback,
        "resuelta": not feedback,
        "rechazados": rechazados,
        "piezas": len(spec.parts),
        "pasadores": len(spec.pins),
        "barrido": _barrido(final),
        "requisitos": requisitos_medidos(spec, layout),
        # Lo que el sistema comprobó con la geometría, frente a lo que solo
        # se mueve porque una fórmula lo dice. Esa diferencia es la que
        # separa «el mecanismo funciona» de «el dibujo se mueve».
        "verificado": {
            "contactos": sum(1 for r in spec.rules if r.kind == "contact"),
            "topes": len(spec.stops),
            "bloqueos": len(spec.blocks),
            "apoyos": sum(1 for b in spec.bodies if b.joint and b.joint.rest_on),
        },
        "impuesto_por_formula": [b.name for b in spec.bodies
                                 if b.joint and b.joint.value is not None],
    }


def _barrido(final) -> dict | None:
    if final is None:
        return None
    choques = final.collisions
    return {
        "posiciones": len(final.angles),
        "hueco_minimo_mm": final.min_gap_mm,
        "choques": len(choques),
        "peor_hueco_mm": min(c.gap_mm for c in choques) if choques else None,
        "pares": [list(p) for p in sorted({tuple(sorted((c.a, c.b))) for c in choques})],
    }


def guardar_ronda(carpeta: Path, resumen: dict) -> None:
    """`rondas/N/resultado.json`, en cuanto la ronda termina."""
    destino = Path(carpeta) / "rondas" / str(resumen["ronda"])
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "resultado.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
