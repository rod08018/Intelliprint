"""Un proyecto es una solicitud; cada ejecución, una versión (F5.5 (web)).

Cada vez que se lanza un diseño nace una carpeta, y la portada pintaba una
fila por carpeta: el trinquete del 2026-09-21 salió a la quinta y la lista
enseñaba cinco «proyectos» con la misma petición, byte a byte. Aquí se juntan
las ejecuciones de una misma solicitud y se elige la que se enseña.

Qué carpeta es versión de qué proyecto, por orden:

1. `proyecto.json`, que escribe quien lanza una modificación desde la web;
2. una referencia que cita otro proyecto (`referencias/texto_N.md`): así se
   relanzó a mano el Ginebra, «Parte del proyecto 2026-09-21-185919-…»;
3. la misma petición, letra por letra, que una ejecución anterior.

Lo que no encaja en nada es un proyecto nuevo. Solo lee: nada se mueve.
"""

import json
import re
from pathlib import Path

from orchestrator.registry import indice
from orchestrator.web.estadisticas import estadisticas

MARCA = "proyecto.json"

SECCIONES = ("projects", "archivo")
"""Dónde buscar. `archivo/` también: archivar no es borrar, y un intento
fallido es la única prueba de por qué algo no funcionó."""

MERITO_ESTADO = {"aprobado": 5, "con reparos": 4, "antiguo": 3, "fallido": 2, "incompleto": 1,
                 "en marcha": 0}
"""Una versión aprobada gana a cualquier otra; la que funciona pero el
revisor suspende, a todo lo demás. `antiguo` es obra anterior al
registro que dejó piezas: no se sabe si salió, pero hay algo que imprimir."""


class ProyectoDesconocido(LookupError):
    """El id no nombra un proyecto del workspace."""


BANCO = "banco"


def secciones_del_banco(workspace: Path) -> list[str]:
    """`banco/<corrida>/<NN>/projects` de cada encargo de cada corrida: ahí
    deja el banco sus proyectos, y la web no los veía (2026-11-10)."""
    raiz = Path(workspace) / BANCO
    if not raiz.is_dir():
        return []
    return sorted(str(p.relative_to(workspace)).replace("\\", "/")
                  for p in raiz.glob("*/*/projects") if p.is_dir())


def resolver_proyecto(id: str, workspace: Path, banco: bool = False) -> Path:
    """La carpeta del proyecto `id`, en `projects/` o en `archivo/`; con
    `banco`, también en las corridas del banco, que solo se miran.

    `id` es un NOMBRE. Lo que no sea un nombre —separadores, `..`, rutas
    absolutas— se rechaza antes de tocar el disco: si no, bajar "el
    proyecto ../../" sería bajar lo que hay por encima del workspace.
    """
    if (not id or id in (".", "..") or id.startswith(".")
            or "/" in id or "\\" in id or ":" in id or Path(id).name != id):
        raise ProyectoDesconocido(id)
    raiz = Path(workspace).resolve()
    for seccion in [*SECCIONES, *(secciones_del_banco(workspace) if banco else [])]:
        carpeta = raiz / seccion / id
        # Segunda comprobación, sobre la ruta YA resuelta: un enlace
        # simbólico dentro de projects/ podría apuntar fuera.
        if carpeta.is_dir() and carpeta.resolve().is_relative_to(raiz):
            return Path(workspace) / seccion / id
    raise ProyectoDesconocido(id)


def piezas_de(carpeta: Path) -> list[Path]:
    """Las STL que construyó el sistema. Una pieza suelta (y los mecanismos
    que ya hay) las deja en parts/<nombre>/<nombre>.stl; una obra, en la
    carpeta de cada nodo (F7.2 (desglose))."""
    carpeta = Path(carpeta)
    # Y las de sus módulos impresos (F10.6 (módulo)), que no son de ningún nodo.
    return sorted([*carpeta.glob("parts/*/*.stl"), *carpeta.glob("nodos/*/parts/*/*.stl"),
                   *carpeta.glob("modulos/*/*/*.stl")])


def ejecuciones(workspace: Path, banco: bool = False, solo=None) -> list[dict]:
    """Una fila por EJECUCIÓN. Lo que se enseña son proyectos: `agrupar`.
    Con `banco`, las de las corridas del banco y solo esas: no son proyectos
    de la persona y no se mezclan con los suyos. Con `solo`, nada más que
    las carpetas con esos nombres: el estado de cada proyecto recorre todos sus
    archivos, y para abrir uno del banco se miraban los 112 de las veinte
    corridas (27 a 33 s, 2026-11-12)."""
    filas = []
    for seccion in (secciones_del_banco(workspace) if banco else SECCIONES):
        carpeta = Path(workspace) / seccion
        if not carpeta.is_dir():
            continue
        for fila in indice(carpeta, solo):
            fila = {k: v for k, v in fila.items() if k != "carpeta"}
            fila["seccion"] = seccion
            fila["piezas"] = len(piezas_de(carpeta / fila["id"]))
            e = estadisticas(carpeta / fila["id"], en_marcha=fila["estado"] == "en marcha")
            # La lista lleva el resumen; la historia de rondas y la tabla de
            # requisitos son del detalle, o la portada pesaría lo que pesan
            # todos los proyectos juntos.
            e.pop("rondas")
            if e["requisitos"]:
                e["requisitos"] = {k: v for k, v in e["requisitos"].items() if k != "filas"}
            fila.update(e)
            filas.append(fila)
    return filas


_CITA = re.compile(r"^# proyecto (\S+) \(")


def _leer(ruta: Path):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def marca_de(carpeta: Path) -> dict:
    return _leer(Path(carpeta) / MARCA) or {}


def _citado(carpeta: Path) -> str | None:
    """El proyecto del que partió, si una de sus referencias lo cita:
    «proyecto <id> (…)». Las escribía el flujo de mecanismos, que ya no
    existe; se siguen leyendo para que los rediseños que dejó salgan como
    versiones de su proyecto y no como proyectos sueltos."""
    for texto in sorted((carpeta / "referencias").glob("texto_*.md")):
        try:
            primera = texto.read_text(encoding="utf-8").split("\n", 1)[0]
        except OSError:
            continue
        if m := _CITA.match(primera):
            return m.group(1)
    return None


def _carpetas(workspace: Path) -> list[Path]:
    """Todas las carpetas, de las dos secciones, de la más antigua a la más
    nueva. Por NOMBRE: empieza por la fecha y hora en que se lanzó, y la
    fecha de modificación cambia cada vez que alguien toca un archivo."""
    carpetas = []
    for seccion in SECCIONES:
        raiz = Path(workspace) / seccion
        if raiz.is_dir():
            carpetas.extend(p for p in raiz.iterdir() if p.is_dir())
    return sorted(carpetas, key=lambda p: (p.name, p.parent.name))


def raices(workspace: Path) -> dict[str, str]:
    """{id de la carpeta: id del proyecto}. El proyecto se llama como su
    primera ejecución, que es la solicitud original."""
    raiz_de: dict[str, str] = {}
    por_peticion: dict[str, str] = {}
    for carpeta in _carpetas(workspace):
        peticion = ""
        if (carpeta / "request.md").is_file():
            peticion = (carpeta / "request.md").read_text(encoding="utf-8", errors="ignore").strip()
        candidato = (marca_de(carpeta).get("proyecto") or _citado(carpeta)
                     or por_peticion.get(peticion))
        # El candidato puede ser a su vez una versión: se sube hasta la raíz.
        raiz_de[carpeta.name] = raiz_de.get(candidato, carpeta.name)
        if peticion:
            por_peticion.setdefault(peticion, carpeta.name)
    return raiz_de


def _merito(v: dict) -> tuple:
    """Cuánto vale una versión para enseñarla la primera.

    Entre fallidas, las que cumplen más requisitos medidos sobre un barrido
    completo; un 2/2 provisional no está comprobado y no puede ganar a un
    1/2 que sí. A igualdad, la más nueva: entre dos aprobadas, la última es
    la modificación que se pidió después."""
    r = v.get("requisitos") or {}
    fraccion = r["cumplen"] / r["total"] if r.get("total") else 0
    return (MERITO_ESTADO.get(v["estado"], 0), bool(r) and not r.get("provisional"),
            fraccion, -(v.get("fallos") or 0), v["version"])


_NOTA_GLOBAL = re.compile(r"\*\*Nota global:\*\*\s*(.+?)\s*$", re.M)
_FILA = re.compile(r"^\| (\S+) \| (\d+ %) \|", re.M)


def _late(corrida: Path) -> bool:
    """Si algún proyecto de la corrida tiene el latido reciente: hay un
    proceso diseñando en ella ahora mismo."""
    import time

    from orchestrator.registry import LATIDO, LATIDO_VALE_S
    ahora = time.time()
    for latido in (*corrida.glob(f"*/projects/*/{LATIDO}"),
                   *corrida.glob(f"*/projects/*/nodos/*/{LATIDO}")):
        try:
            if ahora - latido.stat().st_mtime < LATIDO_VALE_S:
                return True
        except OSError:   # se quitó entre el glob y el stat
            pass
    return False


def _encargos_por_su_marca(corrida: Path) -> list[dict]:
    """Los encargos de una corrida que aún no tiene informe, por la marca
    que deja el banco en cada carpeta al empezarla (`banco.marcar_carpeta`)."""
    encargos = []
    for marca in sorted(corrida.glob("*/encargo.txt")):
        hecho = sorted((marca.parent / "projects").glob("*"))
        encargos.append({"nombre": marca.read_text(encoding="utf-8").strip(), "nota": "",
                         "proyecto": hecho[-1].name if hecho else None})
    return encargos


def corridas_del_banco(workspace: Path) -> list[dict]:
    """Cada corrida del banco, de la última a la primera, con su nota y la
    de cada encargo según su último informe (el de la última reanudación,
    si la hubo: es la última palabra), y el proyecto de cada encargo.

    Una corrida sin informe también sale, con sus encargos y sin nota: el
    informe se escribe al final, y durante la hora que tarda un backlog no
    había por dónde entrar a mirarlo (2026-11-11, el primer brazo).
    `en_marcha` dice si hay un proceso diseñando en ella ahora."""
    raiz = Path(workspace) / BANCO
    if not raiz.is_dir():
        return []
    def cuando(corrida: Path) -> float:
        # Por la fecha de su informe, no por el nombre: la de 2026-11-03 se
        # llamaba con el año y las de después no, y salía la primera.
        primero = corrida / "banco.md"
        return (primero if primero.is_file() else corrida).stat().st_mtime

    corridas = []
    for corrida in sorted((p for p in raiz.iterdir() if p.is_dir()), key=cuando, reverse=True):
        # El más reciente, sea una reanudación o un rejuicio: el 1110-0313 se
        # rejuzgó con el 608ZZ ya medido y la web seguía con la reanudada.
        informes = sorted(list(corrida.glob("banco_reanudado*.md"))
                          + list(corrida.glob("banco_rejuzgado*.md")),
                          key=lambda p: p.stat().st_mtime)
        informe = informes[-1] if informes else corrida / "banco.md"
        en_marcha = _late(corrida)
        if not informe.is_file():
            encargos = _encargos_por_su_marca(corrida)
            if encargos:   # una carpeta sin encargos no es una corrida
                corridas.append({"id": corrida.name, "informe": None, "nota": "",
                                 "encargos": encargos, "en_marcha": en_marcha})
            continue
        texto = informe.read_text(encoding="utf-8", errors="ignore")
        nota = _NOTA_GLOBAL.search(texto)
        encargos = []
        # La tabla va en el orden de los encargos, y cada uno en su carpeta
        # numerada en ese orden (`banco.reanudar`).
        for n, (nombre, su_nota) in enumerate(_FILA.findall(texto), 1):
            hecho = sorted((corrida / f"{n:02d}" / "projects").glob("*"))
            encargos.append({"nombre": nombre, "nota": su_nota,
                             "proyecto": hecho[-1].name if hecho else None})
        corridas.append({"id": corrida.name, "informe": informe.name,
                         "nota": nota.group(1) if nota else "", "encargos": encargos,
                         "en_marcha": en_marcha})
    return corridas


def agrupar(filas: list[dict], workspace: Path) -> list[dict]:
    """Las ejecuciones de `filas` juntas por proyecto.

    Cada proyecto lleva, arriba, lo de su MEJOR versión —lo que enseña la
    fila— y debajo `versiones`, de la primera a la última. `id` es el del
    proyecto y `mejor` el de la versión que se enseña: no son el mismo."""
    raiz_de = raices(workspace)
    por_raiz: dict[str, list[dict]] = {}
    for fila in sorted(filas, key=lambda f: f["id"]):
        por_raiz.setdefault(raiz_de.get(fila["id"], fila["id"]), []).append(fila)

    proyectos = []
    for raiz, versiones in por_raiz.items():
        for n, v in enumerate(versiones, 1):
            v["version"] = n
            v["modificacion"] = marca_de(Path(workspace) / v["seccion"] / v["id"]).get("modificacion")
        # Una en marcha no ha terminado de decir lo que vale: no se elige
        # salvo que sea la única.
        terminadas = [v for v in versiones if v["estado"] != "en marcha"] or versiones
        mejor = max(terminadas, key=_merito)
        en_marcha = next((v for v in versiones if v["estado"] == "en marcha"), None)
        primera = versiones[0]
        proyectos.append({
            **mejor,
            "id": raiz,
            "mejor": mejor["id"],
            "titulo": primera.get("peticion") or primera.get("titulo") or raiz,
            # Si alguna sigue en projects/, el proyecto está vivo aunque sus
            # intentos fallidos se archivaran.
            "seccion": "projects" if any(v["seccion"] == "projects" for v in versiones) else "archivo",
            "en_marcha": en_marcha["id"] if en_marcha else None,
            "usd_total": round(sum((v.get("coste") or {}).get("usd", 0) for v in versiones), 4),
            "versiones": versiones,
        })
    # Arriba, lo último en lo que se trabajó.
    return sorted(proyectos, key=lambda p: p["versiones"][-1]["id"], reverse=True)


def componer_modificacion(peticion_base: str, base: str, cambio: str) -> str:
    """La petición de una versión nueva: la de la versión de la que parte
    —que ya lleva sus propias modificaciones— y el cambio, literal. El
    diseñador no ve el historial del proyecto: lo que no esté aquí no existe
    para él."""
    partes = [peticion_base.strip()] if peticion_base.strip() else []
    partes.append(f"MODIFICACIÓN sobre la versión {base} (lo que no se mencione, "
                  f"se queda como estaba):\n{cambio.strip()}")
    return "\n\n".join(partes)


def proyectos(workspace: Path) -> list[dict]:
    """Los proyectos del workspace, cada uno con sus versiones."""
    return agrupar(ejecuciones(workspace), workspace)


def lanzar_modificacion(trabajos, workspace: Path, base: Path, cambio: str,
                        orden_pieza: list[str] | None = None) -> dict:
    """Una versión nueva del proyecto de `base`, partiendo de `base`. La usan
    la web y Crafty: antes Crafty solo podía pedir un diseño NUEVO, y una
    corrección del sargento salió como otro proyecto (2026-10-26).

    Solo de una pieza suelta. Lo demás se dice con `ValueError` y no lanza
    nada: sin esto, lo que no era una pieza caía en la orden por omisión del
    gestor con la petición entera del proyecto."""
    base = Path(base)
    if (base / "obra.json").is_file():
        raise ValueError("un backlog se cambia pieza a pieza, con Corregir o Rehacer en su "
                         "tarjeta; no se rehace entero")
    if (base / "mechanism.json").is_file():
        raise ValueError(
            f"{base.name} es un mecanismo, y el flujo de mecanismos se retiró: se puede ver, "
            "descargar y abrir en PrusaSlicer, pero no cambiar. Lo que se mueve se pide ahora "
            "como un robot o conjunto")
    # Una pieza se rehace como pieza (2026-11-04: el gancho, al cambiarlo,
    # salía por la orden por omisión, entonces el flujo viejo de recetas).
    es_pieza = (base / "pieza.json").is_file() or "pieza" in (
        (_leer(base / "job.json") or {}).get("comando") or [])
    if not es_pieza:
        raise ValueError(f"{base.name} no es una pieza suelta: no hay con qué rehacerlo")
    if not orden_pieza:
        raise RuntimeError("esto no tiene con qué rehacer una pieza suelta")
    raiz = raices(workspace).get(base.name, base.name)
    original = ((base / "request.md").read_text(encoding="utf-8", errors="ignore")
                if (base / "request.md").is_file() else "")
    cambio = cambio.strip()
    nueva = trabajos.start(
        componer_modificacion(original, base.name, cambio), comando=orden_pieza,
        proyecto={"proyecto": raiz, "basado_en": base.name, "modificacion": cambio})
    return {"id": nueva, "proyecto": raiz}
