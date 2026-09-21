"""Lo que la interfaz cuenta de cada proyecto, sacado de su carpeta
(F5.5 (web)).

Solo lee: los datos los escriben el flujo (`rondas/N/resultado.json`,
`review.json`) y el presupuesto (`design_cost.json`), y lo hacen mientras el
proyecto trabaja, no al final. Un proyecto anterior a esto no tiene nada de
eso, y tiene que seguir viéndose.
"""

import json
from pathlib import Path


def _leer(ruta: Path):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _rondas(carpeta: Path, en_marcha: bool) -> list[dict]:
    """Cada ronda con su resultado. Sin resultado, solo la ÚLTIMA puede estar
    en curso, y solo si el proyecto sigue trabajando: un proyecto lanzado
    antes de que existiera resultado.json tiene rondas sin él, y pintarlas
    todas «en curso» sería falso."""
    raiz = carpeta / "rondas"
    if not raiz.is_dir():
        return []
    numeros = sorted(int(d.name) for d in raiz.iterdir() if d.is_dir() and d.name.isdigit())
    historia = []
    for n in numeros:
        resultado = _leer(raiz / str(n) / "resultado.json")
        if resultado is None:
            spec = _leer(raiz / str(n) / "mechanism.json") or {}
            en_curso = en_marcha and n == numeros[-1]
            historia.append({"ronda": n, "titulo": spec.get("title", ""), "en_curso": en_curso,
                             "sin_datos": not en_curso, "plan": spec.get("fix_plan")})
        else:
            historia.append({**resultado, "en_curso": False})
    return historia


def _requisitos(historia: list[dict]) -> dict | None:
    """Los de la ÚLTIMA ronda que midió algo, diciendo cuál es: la ronda en
    curso todavía no ha medido nada, y enseñar ceros sería mentir."""
    for r in reversed(historia):
        filas = r.get("requisitos") or []
        if filas:
            return {
                "de_la_ronda": r["ronda"],
                "total": len(filas),
                "cumplen": sum(1 for f in filas if f.get("cumple") is True),
                # Sin medir no es cumplido: un requisito que depende de un
                # apoyo sin resolver no se puede dar por bueno.
                "sin_medir": sum(1 for f in filas if f.get("medido") is None),
                "filas": filas,
            }
    return None


def _coste(carpeta: Path) -> tuple[dict | None, str | None]:
    datos = _leer(carpeta / "design_cost.json")
    if not datos:
        return None, None
    r = datos.get("resumen") or {}
    tope = r.get("limite_usd") or 0
    coste = {
        "usd": round(r.get("total_usd", 0.0), 4),
        "tope_usd": tope,
        "fraccion": (r.get("total_usd", 0.0) / tope) if tope else None,
        "tokens_salida": r.get("tokens_salida", 0),
        "llamadas": r.get("llamadas", 0),
    }
    # Las llamadas van en orden: la última dice qué está haciendo ahora.
    detalle = datos.get("detalle") or []
    return coste, (detalle[-1].get("etapa") if detalle else None)


def _revisor(carpeta: Path) -> dict | None:
    datos = _leer(carpeta / "review.json")
    if not datos:
        return None
    cuenta = {"cumple": 0, "no_cumple": 0, "no_verificable": 0}
    for item in datos.get("items", []):
        if item.get("verdict") in cuenta:
            cuenta[item["verdict"]] += 1
    return cuenta


def estadisticas(carpeta: Path, en_marcha: bool = False) -> dict:
    carpeta = Path(carpeta)
    historia = _rondas(carpeta, en_marcha)
    coste, ultima_etapa = _coste(carpeta)
    return {
        "ronda": historia[-1]["ronda"] if historia else 0,
        "rondas": historia,
        "ultima_etapa": ultima_etapa,
        "coste": coste,
        "requisitos": _requisitos(historia),
        "revisor": _revisor(carpeta),
        "animacion": (carpeta / "animation.gif").is_file(),
    }
