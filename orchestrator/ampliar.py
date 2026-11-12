"""Añadir una función a un invento ya diseñado (F9.10 (ampliar)).

Un backlog solo se podía cambiar pieza a pieza. Para ponerle una pinza a un
pan-tilt, o una muñeca a un brazo, había que pedir el invento entero otra
vez: se desglosaba de cero, las piezas ya diseñadas —y pagadas— no servían,
y nada aseguraba que las nuevas se parecieran a las de antes.

Ahora la función se pide aparte y pasa por dos manos:

1. `pedir` la deja apuntada (`ampliacion_pedida.json`).
2. `proponer` le pide al desglosador el plan entero con lo nuevo, comprueba
   sin modelo que no quita ni cambia nada de lo aprobado (`diferencia`) y
   deja la propuesta en `ampliacion.json`. **`obra.json` no se toca.**
3. La persona la ve —piezas nuevas, uniones nuevas y qué piezas ya hechas
   habrá que corregir— y la aprueba, la contesta o la descarta.
4. `aprobar` cambia el plan: archiva el anterior y la verificación del
   conjunto, y corrige, partiendo de lo construido, solo las piezas que la
   función toca. Lo demás sigue listo; lo que se diseñó contra una pieza
   corregida se comprueba contra ella (F9.9 (revalidar)).

Lo que NO hace: quitar una función, ni cambiar una unión aprobada. Eso sigue
siendo corregir la pieza, o pedir el invento de nuevo.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from orchestrator.schemas.obra import Obra

PEDIDA = "ampliacion_pedida.json"
"""{peticion, respuestas, anterior}: lo que se pidió y aún no se ha propuesto.
`anterior` es la propuesta que la persona vio y contestó, si la hubo."""

PROPUESTA = "ampliacion.json"
"""La propuesta que espera el visto bueno: el plan entero con lo nuevo."""

PRESENTACION = "ampliacion.md"

HECHAS = "ampliaciones.json"
"""Las ampliaciones ya aprobadas, en orden: qué se pidió, qué piezas trajo,
cuáles se mandaron corregir y la huella de cada pieza justo antes. Con las
huellas el banco cuenta después cuáles siguen idénticas (`banco.Conserva`)."""


@dataclass
class Diferencia:
    """Lo que una ampliación añade al plan, y lo que no puede hacer."""
    nuevos: list[str] = field(default_factory=list)
    uniones: list[str] = field(default_factory=list)
    corregir: dict[str, list[str]] = field(default_factory=dict)
    """Las piezas que ya había y que la función toca, con el porqué."""
    errores: list[str] = field(default_factory=list)


def diferencia(antes: Obra, despues: Obra) -> Diferencia:
    """Qué añade `despues` a `antes`, sin modelo. En `errores`, lo que una
    ampliación no puede hacer: lo aprobado y diseñado no se cambia por
    debajo, porque las piezas se hicieron con ello."""
    from orchestrator import obra as O
    from orchestrator.componentes import cargar

    d = Diferencia()
    ahora = {n.id: n for n in despues.nodos}
    motivos: dict[str, list[str]] = {}
    gana_algo = False
    for n in antes.nodos:
        m = ahora.get(n.id)
        if m is None:
            d.errores.append(
                f"falta «{n.id}» ({n.nombre}): una ampliación no quita piezas. Devuelve todas "
                "las que había, con su mismo id")
            continue
        if m.tipo != n.tipo:
            d.errores.append(f"«{n.id}» era «{n.tipo}» y ahora es «{m.tipo}»: no se cambia")
        quita = [x for x in n.depende_de if x not in m.depende_de]
        pone = [x for x in m.depende_de if x not in n.depende_de]
        if quita or (pone and n.tipo == "pieza"):
            d.errores.append(
                f"«{n.id}» ya existe y su `depende_de` era [{', '.join(n.depende_de)}]: no "
                "puede cambiar. Una pieza hecha no puede pasar a depender de otra, habría que "
                "rediseñarla contra ella: lo nuevo depende de lo que hay, nunca al revés")
        pierde = Counter(n.compra) - Counter(m.compra)
        if pierde:
            d.errores.append(f"«{n.id}» llevaba {', '.join(sorted(pierde))} y ya no: una "
                             "ampliación no quita lo comprado")
        for c, cuantos in (Counter(m.compra) - Counter(n.compra)).items():
            gana_algo = True
            try:
                que = cargar(c).nombre
            except KeyError:
                que = c
            motivos.setdefault(n.id, []).append(
                f"ahora lleva además {cuantos} × {que} ({c}), que hay que alojar y sujetar")

    viejas = {u.id: u for u in antes.uniones}
    nuevas = {u.id: u for u in despues.uniones}
    for i, u in viejas.items():
        if nuevas.get(i) != u:
            d.errores.append(
                f"la unión «{i}» ya estaba aprobada y las piezas se hicieron con ella: no se "
                "quita ni se cambia. Devuélvela igual")
    hechas = {n.id for n in antes.nodos if n.tipo == "pieza"}
    for u in despues.uniones:
        if u.id in viejas:
            continue
        d.uniones.append(u.id)
        for i in u.nodos():
            if i in hechas:
                motivos.setdefault(i, []).append(O.union_en_palabras(despues, u))
    d.nuevos = [i for i in despues.orden() if i not in {n.id for n in antes.nodos}]
    d.corregir = {i: motivos[i] for i in antes.orden() if i in motivos}
    if not d.errores and not (d.nuevos or d.uniones or gana_algo):
        d.errores.append("la ampliación no añade nada: ni piezas, ni uniones, ni componentes. "
                         "Añade lo que hace falta para la función que se pide")
    return d


def _con_lo_de_antes(antes: Obra, despues: Obra) -> Obra:
    """El título y el nombre de cada pieza que ya había no cambian aunque el
    modelo los reescriba: son los que la persona ya conoce."""
    nombres = {n.id: n.nombre for n in antes.nodos}
    datos = despues.model_dump()
    datos["titulo"] = antes.titulo
    for n in datos["nodos"]:
        n["nombre"] = nombres.get(n["id"], n["nombre"])
    return Obra.model_validate(datos)


# --- el estado ------------------------------------------------------------------------------

def _leer(ruta: Path) -> dict | None:
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.is_file() else None


def _escribir(ruta: Path, datos: dict) -> None:
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")


def huella(step: Path) -> str:
    """Lo que identifica una pieza construida: el SHA-256 de su STEP."""
    import hashlib
    return hashlib.sha256(Path(step).read_bytes()).hexdigest()


def hechas(carpeta: Path) -> list[dict]:
    """Las ampliaciones aprobadas de este invento, la primera delante."""
    ruta = Path(carpeta) / HECHAS
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.is_file() else []


def pendiente(carpeta: Path) -> str | None:
    """«propuesta» si espera el visto bueno, «pedida» si aún no se ha
    propuesto, None si no hay ninguna ampliación a medias."""
    carpeta = Path(carpeta)
    if (carpeta / PROPUESTA).is_file():
        return "propuesta"
    return "pedida" if (carpeta / PEDIDA).is_file() else None


def pedida(carpeta: Path) -> str:
    """Lo que la persona pidió añadir, en sus palabras; vacío si nada."""
    datos = _leer(Path(carpeta) / PROPUESTA) or _leer(Path(carpeta) / PEDIDA) or {}
    return datos.get("peticion", "")


def pedir(carpeta: Path, peticion: str) -> None:
    """Apunta la función que se quiere añadir. No llama a ningún modelo ni
    toca el plan: la propuesta la hace `proponer`."""
    from orchestrator import obra as O
    carpeta = Path(carpeta)
    if not O.es_obra(carpeta):
        raise ValueError(f"{carpeta.name} no es un invento por partes: solo a un backlog se "
                         "le añade una función")
    if not O.aprobada(carpeta):
        raise ValueError("el desglose todavía espera tu visto bueno: contéstalo ahí con lo "
                         "que le falta, en vez de ampliarlo")
    if not peticion.strip():
        raise ValueError("di qué función quieres añadir")
    if pendiente(carpeta):
        raise ValueError("ya hay una ampliación esperando: apruébala, contéstala o "
                         "descártala antes de pedir otra")
    _escribir(carpeta / PEDIDA, {"peticion": peticion.strip(), "respuestas": [],
                                 "anterior": None})


def descartar(carpeta: Path) -> None:
    """La ampliación a medias se archiva y el invento sigue como estaba."""
    from orchestrator import obra as O
    carpeta = Path(carpeta)
    if not pendiente(carpeta):
        raise ValueError("no hay ninguna ampliación que descartar")
    O._archivar(carpeta, carpeta / PEDIDA, carpeta / PROPUESTA, carpeta / PRESENTACION)


# --- proponer -------------------------------------------------------------------------------

def _peticion(carpeta: Path, datos: dict) -> str:
    """La petición del invento con la función nueva al final, que es donde
    el desglosador busca lo que la persona contestó."""
    texto = (carpeta / "request.md").read_text(encoding="utf-8").strip()
    texto += f"\n\nFunción que se añade al invento, que ya está diseñado: {datos['peticion']}"
    for r in datos.get("respuestas") or []:
        texto += f"\nRespuestas a la propuesta de ampliación: {r}"
    return texto


def proponer(carpeta: Path, agente, agujeros: dict | None = None) -> dict:
    """Pide al desglosador el plan con la función nueva y lo deja esperando
    el visto bueno. `agente` es un `DesglosadorAgent`; `agujeros`, `holes`
    del perfil activo. No toca `obra.json`."""
    from orchestrator import obra as O
    from orchestrator.plan import compras_en_palabras, validar_plan

    carpeta = Path(carpeta)
    datos = _leer(carpeta / PEDIDA)
    if datos is None:
        raise ValueError("no hay ninguna ampliación pedida que proponer")
    actual = O.cargar_obra(carpeta)
    anterior = datos.get("anterior") or (carpeta / O.OBRA).read_text(encoding="utf-8")
    propuesta = _con_lo_de_antes(actual, agente.desglosar(
        _peticion(carpeta, datos), agujeros=agujeros or {}, anterior=anterior, ampliar=actual))
    d = diferencia(actual, propuesta)
    if d.errores:   # el agente ya lo comprueba en sus reintentos: aquí no debería llegar
        raise ValueError("la ampliación propuesta no vale:\n- " + "\n- ".join(d.errores))
    fichas = [O.carpeta_de_fichas(carpeta)]
    avisos = validar_plan(propuesta, agujeros or {}, fichas)[1]
    try:
        ya = set(compras_en_palabras(actual, fichas))
        tornilleria = [t for t in compras_en_palabras(propuesta, fichas) if t not in ya]
    except Exception:  # noqa: BLE001 — una ficha rota no impide enseñar la propuesta
        tornilleria = []
    propuesta_ = {
        "peticion": datos["peticion"], "respuestas": datos.get("respuestas") or [],
        "obra": propuesta.model_dump(), "nuevos": d.nuevos, "uniones": d.uniones,
        "corregir": d.corregir, "tornilleria": tornilleria, "avisos": avisos,
        "cuando": O._ahora()}
    _escribir(carpeta / PROPUESTA, propuesta_)
    (carpeta / PRESENTACION).write_text(presentar(actual, propuesta, propuesta_),
                                        encoding="utf-8")
    O._archivar(carpeta, carpeta / PEDIDA)
    return propuesta_


def presentar(antes: Obra, despues: Obra, propuesta: dict) -> str:
    """Lo que la persona lee antes de aprobar: lo que se añade y lo que se
    le toca a lo que ya tenía."""
    from orchestrator import obra as O

    def nombre(i):
        return despues.nodo(i).nombre

    lineas = [f"# {antes.titulo}: añadir una función", "", f"> {propuesta['peticion']}"]
    lineas += [f"> Contestaste: {r}" for r in propuesta.get("respuestas") or []]
    lineas += ["", "## Piezas nuevas", ""]
    for i in propuesta["nuevos"]:
        n = despues.nodo(i)
        # En la misma línea: una lista anidada sale en la web como un
        # «- lleva: sg90» suelto, sin decir de qué pieza es.
        detalles = [f"{titulo}: {', '.join(cosas)}" for titulo, cosas in (
            ("Lleva", n.compra), ("Va sobre", [nombre(x) for x in n.depende_de]))
            if cosas and n.tipo == "pieza"]
        lineas.append(f"- **{n.nombre}**: {n.que_hace.rstrip('.')}."
                      + "".join(f" {x}." for x in detalles))
    if not propuesta["nuevos"]:
        lineas.append("Ninguna.")
    uniones = [u for u in despues.uniones if u.id in propuesta["uniones"]]
    if uniones:
        lineas += ["", "## Uniones nuevas", "",
                   *(f"- {O.union_en_palabras(despues, u)}" for u in uniones)]
    lineas += ["", "## Piezas ya hechas que hay que corregir", ""]
    for i, motivos in propuesta["corregir"].items():
        lineas.append(f"- **{nombre(i)}**: " + "; ".join(motivos))
    if propuesta["corregir"]:
        lineas += ["", "Se corrigen partiendo de la pieza que hay: solo se les añade eso."]
    else:
        lineas.append("Ninguna.")
    intactas = [nombre(n.id) for n in antes.nodos
                if n.tipo == "pieza" and n.id not in propuesta["corregir"]]
    conjuntos = [n.nombre for n in despues.nodos if n.tipo == "conjunto"]
    lineas += ["", "## Lo que no se toca", ""]
    if intactas:
        lineas.append(f"- {', '.join(intactas)}: siguen como están. Las que se diseñaron "
                      "contra una pieza corregida se comprueban contra ella, y solo se tocan "
                      "si dejan de valer.")
    if conjuntos:
        lineas.append(f"- {', '.join(conjuntos)}: se vuelve a mover entero cuando todas las "
                      "piezas estén listas.")
    if propuesta.get("tornilleria"):
        lineas += ["", "## Tornillería que se añade", "",
                   *(f"- {t}" for t in propuesta["tornilleria"])]
    if propuesta.get("avisos"):
        lineas += ["", "## Avisos", "", *(f"- {a}" for a in propuesta["avisos"])]
    return "\n".join(lineas) + "\n"


# --- aprobar --------------------------------------------------------------------------------

def aprobar(carpeta: Path, respuestas: str = "", por: str = "") -> None:
    """El visto bueno a la propuesta: ahora sí cambia el plan. Con
    `respuestas` no se aprueba: se guardan y se vuelve a proponer partiendo
    de la propuesta que la persona vio, como con el desglose."""
    from orchestrator import obra as O

    carpeta = Path(carpeta)
    datos = _leer(carpeta / PROPUESTA)
    if datos is None:
        raise ValueError("no hay ninguna ampliación esperando el visto bueno")
    if respuestas.strip():
        _escribir(carpeta / PEDIDA, {
            "peticion": datos["peticion"],
            "respuestas": [*datos.get("respuestas", []), respuestas.strip()],
            "anterior": Obra.model_validate(datos["obra"]).model_dump_json(indent=2)})
        O._archivar(carpeta, carpeta / PROPUESTA, carpeta / PRESENTACION)
        return

    actual = O.cargar_obra(carpeta)
    nueva = Obra.model_validate(datos["obra"])
    d = diferencia(actual, nueva)
    if d.errores:
        raise ValueError("la propuesta ya no encaja con el plan que hay:\n- "
                         + "\n- ".join(d.errores))
    # Cómo está cada pieza ahora, antes de tocar nada: es contra lo que se
    # sabrá después cuáles siguieron idénticas.
    antes = {}
    for n in actual.nodos:
        try:
            antes[n.id] = huella(O._step_de(O._pieza_construida(carpeta / O.NODOS / n.id)))
        except (ValueError, OSError):
            continue   # sin construir (o es el conjunto): no hay qué conservar
    (carpeta / HECHAS).write_text(json.dumps([*hechas(carpeta), {
        "peticion": datos["peticion"], "respuestas": datos.get("respuestas") or [],
        "por": por, "cuando": O._ahora(), "nuevos": d.nuevos, "uniones": d.uniones,
        "corregidas": list(d.corregir), "antes": antes}], ensure_ascii=False, indent=1),
        encoding="utf-8")
    # El plan anterior y lo que se midió con él se archivan, no se borran: la
    # verificación y el estudio del conjunto eran de un invento sin la función.
    tocadas = {*d.nuevos, *d.corregir}
    conjuntos = [n.id for n in nueva.nodos
                 if n.tipo == "conjunto" and tocadas & set(n.depende_de)]
    O._archivar(carpeta, carpeta / O.OBRA, carpeta / "obra.md", carpeta / O.ANIMACION,
                carpeta / PROPUESTA, carpeta / PRESENTACION,
                *(carpeta / O.NODOS / c for c in conjuntos))
    O.guardar(carpeta, nueva, por=por, avisos=datos.get("avisos") or [])
    with (carpeta / "request.md").open("a", encoding="utf-8") as f:
        f.write(f"\nAmpliación: {datos['peticion']}\n")
        for r in datos.get("respuestas") or []:
            f.write(f"Respuestas a la ampliación: {r}\n")

    for i in actual.orden():
        if i not in d.corregir:
            continue
        cambio = (f"Al invento se le añade una función: {datos['peticion']}\n"
                  "Esta pieza ya estaba hecha y la función nueva la toca:\n"
                  + "\n".join(f"- {m}" for m in d.corregir[i])
                  + "\nAñádele solo lo que eso pide. Lo demás, igual: lo que ya hace y lo que "
                  "ofrece a las piezas que se diseñaron contra ella no cambia.")
        if O.programa_construido(carpeta, i):
            O.corregir(carpeta, i, cambio)
        elif (carpeta / O.NODOS / i).exists():
            # Con un concepto a medias, sin pieza: se rehace con el cambio dicho.
            O.rehacer(carpeta, i, cambio)
