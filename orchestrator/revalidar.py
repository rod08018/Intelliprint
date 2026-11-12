"""Revalidar en vez de rehacer (F9.9 (revalidar)).

Corregir una pieza de un backlog archivaba todo lo que se había diseñado
contra ella. En el pan-tilt 1111-1342 (2026-11-11) a la base le faltaban dos
agujeros bajo las orejas del servo; corregirla tiró el soporte y la
plataforma, que no tocaban esos agujeros, y la plataforma que salió después
(30 × 28.5) ya no llevaba la cámara que sí cabía en la archivada (32 × 27):
47 minutos y 0,53 USD para cambiar un fallo por otro.

Ahora lo construido contra la pieza que se corrige se queda, marcado, con una
copia de la ficha contra la que se hizo. Cuando la pieza corregida vuelve a
estar lista se comprueba, sin modelo:

- que no cambió nada de lo que la otra pudo usar: sus agujeros con nombre,
  lo comprado que monta y las salidas sobre las que se gira;
- que la pieza corregida sigue cabiendo y entrando donde la otra la colocó,
  y que si la tocaba la sigue tocando (una sonda de FreeCAD, con el STEP);
- y que no le aparece ningún defecto del plan —el sitio de un giro, un
  tornillo— que no tuviera ya.

Si todo se cumple la pieza no se toca. Si no, se corrige partiendo de ella
(`obra.corregir`), con lo que cambió dicho en cifras.

Lo que NO se comprueba: que un agujero que cambió lo usara de verdad la otra
pieza (se da por usado: se peca de rehacer de más, no de menos), ni el
choque al moverse, que lo mide después el conjunto entero.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

MARCA = "revalidar.json"
"""{por, antes}: qué piezas se corrigieron debajo y qué defectos del plan
tenía ya esta antes de que se tocara nada."""

CONTRA = "contra"
"""Las fichas contra las que se construyó la pieza, copiadas al marcarla: la
de la pieza corregida se archiva y la nueva se llama igual."""

HECHA = "revalidada.json"

TOL_MM = 0.01
"""Por debajo de esto dos cotas son la misma: las fichas se guardan con seis
decimales y FreeCAD no repite el último."""

TOCA_MM = 1.0
"""A esto o menos, dos piezas se tocaban: el mismo umbral que usa la sonda
`componente_cabe` para lo comprado."""

SE_ALEJA_MM = 0.5
"""Lo que una pieza puede separarse de la que tocaba sin que cuente. Es un
criterio, no una medida: medio milímetro es lo que ya se da de holgura entre
piezas que encajan."""


def _p(v) -> str:
    return "(" + ", ".join(f"{round(float(c), 3) + 0.0:g}" for c in v) + ")"


def _igual(a, b) -> bool:
    return len(a) == len(b) and all(abs(float(x) - float(y)) <= TOL_MM for x, y in zip(a, b))


def _forma(c) -> list[float]:
    """Las cotas de un cuerpo de ficha, para compararlas con tolerancia."""
    if c.caja is not None:
        return [0.0, *c.caja]
    if c.cilindro is not None:
        return [1.0, c.cilindro.diametro, c.cilindro.alto, c.cilindro.interior or 0.0]
    return []


def _cuerpo_cambiado(a, b) -> list[str]:
    dif = []
    if not _igual(a.en, b.en):
        dif.append(f"estaba en {_p(a.en)} y ahora está en {_p(b.en)}")
    eje_a = a.cilindro.eje if a.cilindro else None
    eje_b = b.cilindro.eje if b.cilindro else None
    if not _igual(_forma(a), _forma(b)) or eje_a != eje_b:
        dif.append("cambió de tamaño o de forma")
    return dif


def interfaz_cambiada(antes, ahora) -> list[str]:
    """Lo que tenía la ficha `antes` y ya no está igual en `ahora`: agujeros
    con nombre, lo comprado que monta (y lo que hay que dejarle libre) y
    salidas. Lo que se AÑADE no cuenta: nadie pudo diseñarse contra algo que
    no existía. La forma de la pieza tampoco: esa se sondea."""
    cambios = []
    nuevos = {h.nombre: h for h in ahora.fijacion}
    for h in antes.fijacion:
        n = nuevos.get(h.nombre)
        if n is None:
            cambios.append(f"el agujero «{h.nombre}» ya no está")
            continue
        dif = []
        if not _igual(h.en, n.en):
            dif.append(f"estaba en {_p(h.en)} y ahora está en {_p(n.en)}")
        if h.eje != n.eje:
            dif.append(f"iba hacia {h.eje} y ahora va hacia {n.eje}")
        if abs(h.diametro - n.diametro) > TOL_MM:
            dif.append(f"era de Ø{h.diametro:g} y ahora es de Ø{n.diametro:g}")
        if h.tornillo != n.tornillo:
            dif.append(f"era para {h.tornillo or 'ningún tornillo'} y ahora para "
                       f"{n.tornillo or 'ninguno'}")
        if dif:
            cambios.append(f"el agujero «{h.nombre}» " + ", ".join(dif))

    for que, de_antes, de_ahora in (
            ("lo que monta", [c for c in antes.cuerpos if c.monta],
             [c for c in ahora.cuerpos if c.monta]),
            ("lo que hay que dejar libre", antes.despejar, ahora.despejar)):
        nuevos = {c.nombre: c for c in de_ahora}
        for c in de_antes:
            n = nuevos.get(c.nombre)
            if n is None:
                cambios.append(f"«{c.nombre}» ({que}) ya no está")
            elif dif := _cuerpo_cambiado(c, n):
                cambios.append(f"«{c.nombre}» ({que}) " + ", ".join(dif))

    nuevas = {s.nombre: s for s in ahora.salidas}
    for s in antes.salidas:
        n = nuevas.get(s.nombre)
        if n is None:
            cambios.append(f"la salida «{s.nombre}» ya no está")
            continue
        dif = []
        if not _igual(s.en, n.en):
            dif.append(f"estaba en {_p(s.en)} y ahora está en {_p(n.en)}")
        if s.eje != n.eje:
            dif.append(f"salía hacia {s.eje} y ahora sale hacia {n.eje}")
        if not _igual(s.recorrido, n.recorrido):
            dif.append(f"giraba de {s.recorrido[0]:g}° a {s.recorrido[1]:g}° y ahora de "
                       f"{n.recorrido[0]:g}° a {n.recorrido[1]:g}°")
        if abs(s.largo - n.largo) > TOL_MM:
            dif.append(f"sobresalía {s.largo:g} mm y ahora {n.largo:g}")
        if dif:
            cambios.append(f"la salida «{s.nombre}» " + ", ".join(dif))
    return cambios


# --- marcar ---------------------------------------------------------------------------------

def _colocadas(parte: Path) -> list[dict]:
    """Los rasgos con los que la pieza construida colocó otras del backlog."""
    ruta = parte / "rasgos.json"
    rasgos = json.loads(ruta.read_text(encoding="utf-8")) if ruta.is_file() else []
    return [r for r in rasgos if r.get("tipo") == "componente"
            and str(r.get("ficha", "")).startswith("obra-")]


def _del_plan(carpeta: Path, nodo: str) -> list[str]:
    """Lo que la pieza construida no cumple del plan, sin FreeCAD: el sitio
    de cada giro (F9.1 (barrido)) y sus tornillos (F9.6 (previsto))."""
    from orchestrator.medida import (defectos_de_giro, sin_sitio_para_lo_nuevo,
                                     uniones_sin_hacer)
    return [*defectos_de_giro(carpeta, nodo), *uniones_sin_hacer(carpeta, nodo),
            *sin_sitio_para_lo_nuevo(carpeta, nodo)]


def _marca(dir_nodo: Path) -> dict | None:
    ruta = dir_nodo / MARCA
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.is_file() else None


def marcar(carpeta: Path, nodo: str, por: str) -> bool:
    """Deja la pieza construida de `nodo` por revalidar, porque `por` se va
    a corregir. Hay que llamarlo ANTES de archivar nada de `por`: copia las
    fichas contra las que se hizo y apunta los defectos del plan que ya
    tenía, que no serán culpa de la corrección.

    False si no hay pieza que guardar (sin construir, o es un conjunto): eso
    se archiva como siempre."""
    from orchestrator import obra as O

    carpeta = Path(carpeta)
    dir_nodo = carpeta / O.NODOS / nodo
    if O.cargar_obra(carpeta).nodo(nodo).tipo != "pieza":
        return False
    try:
        parte = O._pieza_construida(dir_nodo)
    except ValueError:
        return False
    fichas = O.carpeta_de_fichas(carpeta)
    for r in _colocadas(parte):
        for ext in (".yaml", ".step"):
            origen, copia = fichas / f"{r['ficha']}{ext}", dir_nodo / CONTRA / f"{r['ficha']}{ext}"
            # La primera copia manda: si la pieza de abajo se corrige dos
            # veces antes de revalidar esta, se hizo contra la primera.
            if origen.is_file() and not copia.exists():
                copia.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(origen, copia)
    marca = _marca(dir_nodo)
    if marca is None:
        try:
            antes = _del_plan(carpeta, nodo)
        except Exception:  # noqa: BLE001 — una medida rota no impide corregir
            antes = None   # no se sabe: al revalidar no se comparará
        marca = {"por": [], "antes": antes}
    if por not in marca["por"]:
        marca["por"].append(por)
    O._marca(dir_nodo / MARCA, **marca)
    return True


def pendientes(carpeta: Path) -> list[str]:
    """Los nodos por revalidar, en el orden del backlog."""
    from orchestrator import obra as O
    carpeta = Path(carpeta)
    return [i for i in O.cargar_obra(carpeta).orden()
            if (carpeta / O.NODOS / i / MARCA).is_file()]


# --- revalidar ------------------------------------------------------------------------------

def _mismo(a: Path, b: Path) -> bool:
    return a.is_file() == b.is_file() and (not a.is_file() or a.read_bytes() == b.read_bytes())


def revalidar(carpeta: Path, nodo: str, freecadcmd: str, material: dict) -> list[str]:
    """Por qué la pieza construida de `nodo` ya no vale contra las fichas de
    ahora; vacío si sigue valiendo. No cambia nada.

    Lanza `RuntimeError` si la sonda no corre: sin medir no se puede dar la
    pieza por buena ni tirarla."""
    from orchestrator import obra as O
    from orchestrator.banco import ComponenteCabe, ComponenteEntra, medir_sondas
    from orchestrator.componentes import cargar_de

    carpeta = Path(carpeta)
    dir_nodo = carpeta / O.NODOS / nodo
    marca = _marca(dir_nodo) or {"por": [], "antes": None}
    parte = O._pieza_construida(dir_nodo)
    fichas, obra = O.carpeta_de_fichas(carpeta), O.cargar_obra(carpeta)

    motivos: list[str] = []
    sondeos: list[tuple[str, list]] = []
    for r in _colocadas(parte):
        id_ = r["ficha"]
        try:
            nombre = obra.nodo(id_.removeprefix("obra-")).nombre
        except KeyError:
            nombre = id_
        nueva, vieja = fichas / f"{id_}.yaml", dir_nodo / CONTRA / f"{id_}.yaml"
        if not nueva.is_file():
            raise ValueError(f"«{nodo}» no se puede revalidar: «{nombre}» no está lista")
        if not vieja.is_file():
            motivos.append(f"no queda la ficha de «{nombre}» contra la que se hizo esta "
                           "pieza: no hay con qué compararla")
            continue
        if _mismo(nueva, vieja) and _mismo(nueva.with_suffix(".step"),
                                           vieja.with_suffix(".step")):
            continue   # la de abajo no cambió: no hay nada que medir
        antes, ahora = cargar_de(vieja), cargar_de(nueva)
        motivos += [f"«{nombre}» cambió: {c}" for c in interfaz_cambiada(antes, ahora)]
        donde = {"en": r["en"], "giros": r.get("giros") or []}
        # Contra la de antes también: si ya entonces no cabía o no entraba,
        # la pieza se aprobó así y no es la corrección la que lo rompe.
        sondeos.append((nombre, [
            s for f in (antes, ahora) for s in (
                ComponenteCabe(tipo="componente_cabe", ficha=f.model_dump(), **donde),
                ComponenteEntra(tipo="componente_entra", ficha=f.model_dump(),
                                entra_por=r["entra_por"], **donde))]))

    if sondeos:
        medidas = iter(medir_sondas(O._step_de(parte), [s for _, ss in sondeos for s in ss],
                                    freecadcmd, material))
        for nombre, _ in sondeos:
            cabia, entraba, cabe, entra = (next(medidas) for _ in range(4))
            for era, es, que in ((cabia, cabe, "no cabe donde esta pieza la colocó"),
                                 (entraba, entra, "no entra por donde esta pieza la monta")):
                if es.estado == "sin_medir":
                    raise RuntimeError(f"no se pudo sondear contra «{nombre}»: {es.detalle}")
                if es.estado == "no_cumple" and era.estado != "no_cumple":
                    motivos.append(f"«{nombre}», ya corregida, {que}: {es.detalle}")
            if (cabia.valor is not None and cabe.valor is not None
                    and cabia.valor <= TOCA_MM and cabe.valor > cabia.valor + SE_ALEJA_MM):
                motivos.append(
                    f"«{nombre}», ya corregida, dejó de tocar a esta pieza: estaban a "
                    f"{cabia.valor:.1f} mm y ahora quedan a {cabe.valor:.1f} mm")

    if marca.get("antes") is not None:
        motivos += [d for d in _del_plan(carpeta, nodo) if d not in marca["antes"]]
    return motivos


def resolver(carpeta: Path, nodo: str, freecadcmd: str, material: dict) -> list[str]:
    """Revalida `nodo` y actúa: si sigue valiendo le quita la marca y vuelve
    a estar como estaba; si no, se corrige partiendo de ella con lo que
    cambió (o se rehace, si no tiene programa del que partir). Devuelve los
    motivos, vacío si sigue valiendo."""
    from orchestrator import obra as O

    carpeta = Path(carpeta)
    dir_nodo = carpeta / O.NODOS / nodo
    motivos = revalidar(carpeta, nodo, freecadcmd, material)
    marca = _marca(dir_nodo) or {"por": []}
    if not motivos:
        contra = sorted(p.stem for p in (dir_nodo / CONTRA).glob("*.yaml"))
        O._archivar(carpeta, dir_nodo / MARCA, dir_nodo / CONTRA)
        O._marca(dir_nodo / HECHA, por=marca["por"], contra=contra)
        return []
    obra = O.cargar_obra(carpeta)
    corregidas = " y ".join(f"«{obra.nodo(i).nombre}»" for i in marca["por"]) or "otra pieza"
    cambio = (f"Se corrigió {corregidas}, contra la que se diseñó esta pieza, y esta ya no "
              "vale tal cual:\n" + "\n".join(f"- {m}" for m in motivos)
              + "\nAjústala a como ha quedado: su ficha de ahora da los puntos y las salidas "
              "nuevos. Lo demás, igual.")
    if O.programa_construido(carpeta, nodo):
        O.corregir(carpeta, nodo, cambio)
    else:
        O.rehacer(carpeta, nodo, cambio)
    return motivos
