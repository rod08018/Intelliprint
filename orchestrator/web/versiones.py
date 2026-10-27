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


def resolver_proyecto(id: str, workspace: Path) -> Path:
    """La carpeta del proyecto `id`, en `projects/` o en `archivo/`.

    `id` es un NOMBRE. Lo que no sea un nombre —separadores, `..`, rutas
    absolutas— se rechaza antes de tocar el disco: si no, bajar "el
    proyecto ../../" sería bajar lo que hay por encima del workspace.
    """
    if (not id or id in (".", "..") or id.startswith(".")
            or "/" in id or "\\" in id or ":" in id or Path(id).name != id):
        raise ProyectoDesconocido(id)
    raiz = Path(workspace).resolve()
    for seccion in SECCIONES:
        carpeta = raiz / seccion / id
        # Segunda comprobación, sobre la ruta YA resuelta: un enlace
        # simbólico dentro de projects/ podría apuntar fuera.
        if carpeta.is_dir() and carpeta.resolve().is_relative_to(raiz):
            return Path(workspace) / seccion / id
    raise ProyectoDesconocido(id)


def piezas_de(carpeta: Path) -> list[Path]:
    """Las STL que construyó el sistema. Las dos rutas del diseño —pieza
    única y mecanismo— las dejan en parts/<nombre>/<nombre>.stl."""
    return sorted(Path(carpeta).glob("parts/*/*.stl"))


def ejecuciones(workspace: Path) -> list[dict]:
    """Una fila por EJECUCIÓN. Lo que se enseña son proyectos: `agrupar`."""
    filas = []
    for seccion in SECCIONES:
        carpeta = Path(workspace) / seccion
        if not carpeta.is_dir():
            continue
        for fila in indice(carpeta):
            fila = {k: v for k, v in fila.items() if k != "carpeta"}
            fila["seccion"] = seccion
            fila["piezas"] = len(piezas_de(carpeta / fila["id"]))
            fila["es_mecanismo"] = (carpeta / fila["id"] / "mechanism.json").is_file()
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
    """El proyecto del que partió, si una de sus referencias lo cita. El
    título lo escribe `referencias._proyecto`: «proyecto <id> (…)»."""
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
                        pieza: str = "") -> dict:
    """Una versión nueva del proyecto de `base`, partiendo de `base`. La usan
    la web y Crafty: antes Crafty solo podía pedir un diseño NUEVO, y una
    corrección del sargento salió como otro proyecto (2026-10-26).

    `pieza`: si el cambio es de una sola pieza, cuál. Va en la petición para
    que el diseñador no toque las demás."""
    base = Path(base)
    raiz = raices(workspace).get(base.name, base.name)
    original = ((base / "request.md").read_text(encoding="utf-8", errors="ignore")
                if (base / "request.md").is_file() else "")
    cambio, pieza = cambio.strip(), pieza.strip()
    if pieza and pieza not in nombres_de_piezas(base):
        raise ValueError(f"la versión {base.name} no tiene ninguna pieza «{pieza}»; tiene: "
                         + ", ".join(nombres_de_piezas(base)))
    texto = (f"Solo la pieza «{pieza}»; las demás se quedan como están: {cambio}"
             if pieza else cambio)
    # Sin mechanism.json el cargador de referencias rechaza el id y el
    # trabajo moriría al arrancar; la petición ya lleva lo que se pidió.
    referencias = [base.name] if (base / "mechanism.json").is_file() else []
    nueva = trabajos.start(
        componer_modificacion(original, base.name, texto),
        referencias=referencias,
        # `cambio` y `pieza` por separado: la CLI los lee (`edicion_de`) para
        # editar la base en vez de diseñar desde cero.
        proyecto={"proyecto": raiz, "basado_en": base.name, "modificacion": texto,
                  "cambio": cambio, "pieza": pieza})
    return {"id": nueva, "proyecto": raiz}


def nombres_de_piezas(carpeta: Path) -> list[str]:
    spec = _leer(Path(carpeta) / "mechanism.json") or {}
    return [p["name"] for p in spec.get("parts", []) if "name" in p]


def edicion_de(carpeta: Path, workspace: Path) -> tuple[Path, str, str] | None:
    """Si `carpeta` es una modificación de otra versión que tiene diseño:
    (esa versión, el cambio, la pieza o ""). Si no, None: se diseña desde
    cero. Las modificaciones de antes de esto no guardaban `cambio` y se
    siguen rediseñando enteras, como se hacía entonces."""
    marca = marca_de(carpeta)
    if not marca.get("basado_en") or not marca.get("cambio"):
        return None
    try:
        base = resolver_proyecto(marca["basado_en"], workspace)
    except ProyectoDesconocido:
        return None
    if not (base / "mechanism.json").is_file():
        return None
    return base, marca["cambio"], marca.get("pieza") or ""
