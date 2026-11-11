"""La lista de materiales de un invento (F7.8 (inventario)): las piezas que se
imprimen y todo lo que no se imprime —lo comprado, los tornillos, las
tuercas— contado.

Sale de lo que cada pieza construida dejó en `rasgos.json`, no de lo que
dijo un modelo: un SG90 cuenta porque la pieza lo colocó con `kit.componente`,
y un tornillo, porque hay un agujero con su métrica (`orchestrator.tornilleria`).
"""

import json
from collections import Counter
from pathlib import Path


def _rasgos(parte: Path) -> list[dict]:
    ruta = parte / "rasgos.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.is_file() else []


def _nombre_de_ficha(ficha: str, fichas: list[Path]) -> str:
    from orchestrator.componentes import cargar
    try:
        return cargar(ficha, fichas).nombre
    except Exception:   # una ficha que ya no está en la biblioteca: su id basta
        return ficha


def _tornilleria(carpeta: Path) -> tuple[Counter, Counter, dict]:
    """(lo que se compra, lo que viene con lo comprado, con qué viene)."""
    from orchestrator.tornilleria import tornillos
    compra, incluido, con = Counter(), Counter(), {}
    for t in tornillos(carpeta):
        if t.viene_con:
            incluido[t.nombre()] += 1
            con[t.nombre()] = t.viene_con
            continue
        compra[t.nombre()] += 1
        for _ in t.tuercas if not t.compra_aparte else ():
            compra[f"Tuerca {t.metrica}"] += 1
        if t.termina == "inserto":
            # No salía en ninguna lista: el agujero era un ciego más.
            compra[f"Inserto térmico {t.metrica}"] += 1
        if t.compra_aparte:
            compra[t.compra_aparte] += 1
    return compra, incluido, con


def materiales(carpeta: Path) -> dict:
    """{"impresas": [{id, nombre, impresa}],
    "comprado": [{id, nombre, cuantos, tipo}],          tipo: componente | tornilleria
    "incluido": [{nombre, cuantos, viene_con}]}: lo que viene en la bolsa
    de un componente, que se ve en el ensamble pero no se compra aparte."""
    from orchestrator import obra as O

    carpeta = Path(carpeta)
    comprado: Counter = Counter()
    impresas = []
    if O.es_obra(carpeta):
        from orchestrator.conjunto import leer_piezas
        ob = O.cargar_obra(carpeta)
        # Lo comprado, ya sin repetir: la plataforma del pan-tilt vuelve a
        # colocar el SG90 del soporte para dejarle hueco, y no es un tercero.
        for p in leer_piezas(carpeta, solo_construidas=True).values():
            comprado.update(r["ficha"] for r in p.propios)
        for i in ob.orden():
            if ob.nodo(i).tipo != "pieza":
                continue
            lista = O.lista(carpeta, i) or {}
            impresas.append({"id": i, "nombre": ob.nodo(i).nombre,
                             "impresa": bool(lista.get("impresa"))})
        fichas = [O.carpeta_de_fichas(carpeta)]
    else:
        titulo = (json.loads((carpeta / "pieza.json").read_text(encoding="utf-8")).get("title")
                  if (carpeta / "pieza.json").is_file() else None)
        for parte in sorted((carpeta / "parts").glob("*")):
            comprado.update(r["ficha"] for r in _rasgos(parte)
                            if r.get("tipo") == "componente" and r.get("ficha")
                            and not r["ficha"].startswith("obra-"))
            impresas.append({"id": parte.name, "nombre": titulo or parte.name, "impresa": False})
        fichas = []
    tornilleria, incluido, con = _tornilleria(carpeta)
    return {
        "impresas": impresas,
        "comprado": [{"id": f, "nombre": _nombre_de_ficha(f, fichas), "cuantos": n,
                      "tipo": "componente"} for f, n in sorted(comprado.items())]
                    + [{"id": nombre, "nombre": nombre, "cuantos": n, "tipo": "tornilleria"}
                       for nombre, n in sorted(tornilleria.items())],
        "incluido": [{"nombre": nombre, "cuantos": n, "viene_con": con[nombre]}
                     for nombre, n in sorted(incluido.items())],
    }
