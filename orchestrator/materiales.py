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
    # Un módulo impreso (F10.6 (módulo)) no se compra: se imprimen sus piezas
    # y se compra lo que lleva dentro.
    from orchestrator import modulos
    sueltos: Counter = Counter()
    for id_ in [i for i in comprado if modulos.es_modulo(i)]:
        cuantos, modulo = comprado.pop(id_), modulos.cargar(id_)
        hechas = {p.stem for p in modulos.piezas_construidas(carpeta) if p.parent.parent.name == id_}
        impresas += [{"id": f"{id_}/{pieza}", "nombre": f"{modulo.ficha['nombre']}: {pieza}"
                      + (f" (× {cuantos})" if cuantos > 1 else ""),
                      "impresa": False, "construida": pieza in hechas}
                     for pieza in modulo.piezas]
        for c, n in modulo.compras.items():
            comprado[c] += n * cuantos
        for c, n in modulo.otros.items():
            sueltos[c] += n * cuantos
    tornilleria, incluido, con = _tornilleria(carpeta)
    correas: Counter = Counter()
    if O.es_obra(carpeta):
        # Lo que pide cada correa del plan (F10.3 (correa)): la polea del
        # motor, que nadie coloca en el dibujo, y la correa que da la
        # distancia a la que quedaron los ejes. Sin esa distancia no se sabe
        # cuál es, y no se inventa.
        from orchestrator import transmision as TR
        medidas = TR.medidas(carpeta)
        comprado[TR.POLEA_DEL_MOTOR] = max(comprado[TR.POLEA_DEL_MOTOR], len(medidas))
        if not medidas:
            del comprado[TR.POLEA_DEL_MOTOR]
        for _, m in medidas:
            if m["correa"]:
                correas[f"Correa GT2 cerrada de {TR.ANCHO_DE_CORREA:g} mm de ancho, "
                        f"{m['correa']['dientes']} dientes ({m['correa']['largo_mm']:g} mm)"] += 1
    return {
        "impresas": impresas,
        "comprado": [{"id": f, "nombre": _nombre_de_ficha(f, fichas), "cuantos": n,
                      "tipo": "componente"} for f, n in sorted(comprado.items())]
                    + [{"id": nombre, "nombre": nombre, "cuantos": n, "tipo": "modulo"}
                       for nombre, n in sorted(sueltos.items())]
                    + [{"id": nombre, "nombre": nombre, "cuantos": n, "tipo": "transmision"}
                       for nombre, n in sorted(correas.items())]
                    + [{"id": nombre, "nombre": nombre, "cuantos": n, "tipo": "tornilleria"}
                       for nombre, n in sorted(tornilleria.items())],
        "incluido": [{"nombre": nombre, "cuantos": n, "viene_con": con[nombre]}
                     for nombre, n in sorted(incluido.items())],
    }
