"""Un juez rápido del concepto con JEV (TypeSafe), solo para avisar.

El usuario propuso (2026-11-09) una capa de modelo de decisión que juzgue
rápido cada tarea. Medido antes de cablearlo, sobre los conceptos reales del
workspace etiquetados a mano (más cuatro mutantes con la sujeción quitada):
de cuatro preguntas genéricas solo separó una, «¿queda algún componente
suelto?», y solo en inglés. Las otras —medida supuesta, tornillo
inaccesible, física errónea— daban lo mismo a buenos y malos: cablearlas
habría sido ruido. El detalle está en `tests/test_juez.py`.

Por eso: una pregunta, en inglés, y un aviso a la persona en la revisión del
concepto. Nunca frena ni rehace nada, y si JEV no contesta no pasa nada: lo
que comprueba de verdad que una pieza funciona sigue siendo la geometría.
"""

import httpx

URL = "https://api.typesafe.ai/v1/systemone"
JUEZ = "juez.json"

# El suelto más dudoso de la medida dio 0.77 y el bueno más alto 0.67 (un
# 608ZZ a presión con su reborde, que es como se monta un rodamiento).
UMBRAL_SUELTO = 0.75

# En inglés a propósito: la misma pregunta en español no separaba (el bueno
# más alto daba 0.88). No retocarla sin repetir la medida.
PREGUNTAS = {"suelto": {"type": "noul", "instructions":
    "Is any component held only by friction, a press fit or gravity, or placed in an "
    "open pocket with nothing retaining it, so it could come out during use?"}}


def juzgar_concepto(texto: str, clave: str | None, *, transporte=None,
                    timeout: float = 30) -> dict | None:
    """{"suelto": p} con la probabilidad que da JEV, o None si no hay clave
    o JEV no contesta: el juicio es un extra y el concepto sigue sin él."""
    if not clave:
        return None
    try:
        with httpx.Client(transport=transporte, timeout=timeout) as cliente:
            r = cliente.post(URL, headers={"Authorization": f"Bearer {clave}"},
                             json={"model": "jev-latest", "state": "PART CONCEPT:\n" + texto,
                                   "questions": PREGUNTAS})
            r.raise_for_status()
            return {"suelto": float(r.json()["answers"]["suelto"]["noul"])}
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return None


def avisos(veredicto: dict | None) -> list[str]:
    """Lo que hay que decirle a la persona antes de que apruebe."""
    p = (veredicto or {}).get("suelto")
    if not isinstance(p, (int, float)) or p < UMBRAL_SUELTO:
        return []
    return [f"Puede que algún componente quede suelto (JEV, {p:.2f}): mira en «Lo que aloja» "
            "cómo se sujeta cada uno y si algo lo frena en todas las direcciones."]
