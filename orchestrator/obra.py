"""Proyectos por partes («obras», F7).

Un proyecto grande se diseña pieza a pieza, y cada pieza terminada se
convierte en una ficha (F7.1 (fichar)): la siguiente se diseña contra ella
con la misma maquinaria que contra un 608ZZ comprado. Así ninguna pieza se
pide de golpe junto con las demás, que es donde se murieron los mecanismos
grandes (la Ginebra, 2026-09-20: el razonador se cortó tres veces).
"""

import datetime as dt
import json
import shutil
import time
from pathlib import Path

import yaml

from orchestrator.componentes import Ficha
from orchestrator.schemas.obra import Obra

_EJES = {(1, 0, 0): "+x", (-1, 0, 0): "-x", (0, 1, 0): "+y", (0, -1, 0): "-y",
         (0, 0, 1): "+z", (0, 0, -1): "-z"}


def _step_de(carpeta: Path) -> Path:
    propio = carpeta / f"{carpeta.name}.step"
    if propio.is_file():
        return propio
    steps = sorted(carpeta.glob("*.step"))
    if len(steps) != 1:
        raise ValueError(f"{carpeta}: no sé qué STEP fichar ({len(steps)} encontrados)")
    return steps[0]


def _agujeros(rasgos: list[dict]) -> list[dict]:
    """Los agujeros con nombre de la pieza, en su marco: con ellos la pieza
    siguiente se atornilla a esta con `componente.punto(nombre)`. Solo los
    de eje alineado, que son los que una ficha sabe girar."""
    salida = []
    for r in rasgos:
        if r.get("tipo") != "agujero" or not r.get("diametro_mm"):
            continue
        eje = _EJES.get(tuple(round(c) for c in r["eje"]))
        if eje is None or any(abs(c - round(c)) > 1e-6 for c in r["eje"]):
            continue
        salida.append({"nombre": r["nombre"], "diametro": float(r["diametro_mm"]),
                       "en": [round(float(c), 6) for c in r["entrada"]], "eje": eje})
    return salida


def _como_cuerpo(p: dict, de: str) -> dict:
    """Una primitiva ya colocada (`mech_toolkit.componentes.primitivas`) como
    cuerpo de ficha, con el nombre del componente delante."""
    nombre = f"{de}: {p['nombre']}"
    extra = {"porque": p["porque"]} if p.get("porque") else {}
    if p.get("gira_con"):
        extra["gira_con"] = p["gira_con"]
    if p["tipo"] == "caja":
        return {"nombre": nombre, "en": [round(c, 6) for c in p["min"]],
                "caja": [round(b - a, 6) for a, b in zip(p["min"], p["max"])], **extra}
    if p["tipo"] == "cilindro":
        cil = {"diametro": p["diametro"], "alto": p["alto"],
               "eje": _EJES[tuple(int(c) for c in p["eje"])]}
        if p.get("interior"):
            cil["interior"] = p["interior"]
        return {"nombre": nombre, "en": [round(c, 6) for c in p["base"]], "cilindro": cil,
                **extra}
    raise ValueError(f"«{nombre}»: una pieza impresa dentro de otra no se ficha todavía")


def _montados(rasgos: list[dict], fichas: Path) -> tuple[list[dict], list[dict]]:
    """Lo comprado que la pieza aloja (los `componente` de sus rasgos), en el
    marco de la pieza: la siguiente se diseña contra la pieza MONTADA. La base
    del pan-tilt (2026-11-09) se fichó vacía, y el soporte de giro, que se
    apoya en el cuerno de su SG90, no veía la carcasa del servo."""
    from mech_toolkit.componentes import primitivas

    from orchestrator.componentes import cargar
    cuerpos, despejar = [], []
    for r in rasgos:
        if r.get("tipo") != "componente" or not r.get("ficha"):
            continue
        # Con las fichas de la obra a mano: la web no tiene
        # `INTELLIPRINT_FICHAS`, y «Está bien» al soporte de giro, que coloca
        # la base, reventó buscándola (2026-11-09).
        ficha = cargar(r["ficha"], [fichas])
        if ficha.origen == "impreso":
            continue   # su forma ya está en su propia ficha
        giros = [tuple(g) for g in r.get("giros") or []]
        for de, lista in (("cuerpos", cuerpos), ("despejar", despejar)):
            lista += [_como_cuerpo(p, r["nombre"]) for p in primitivas(ficha, r["en"], giros, de)]
    return cuerpos, despejar


def fichar(carpeta: Path, id_: str, nombre: str, destino: Path, proyecto: str = "") -> Path:
    """La ficha de la pieza construida en `carpeta` (`parts/<pieza>/`), en
    `destino/<id_>.yaml`, con una copia de su STEP al lado. Es su forma
    CONSTRUIDA y sus agujeros con nombre, no lo que el programa dijo hacer:
    medir contra ella no es el etiquetado circular de la ADR-011."""
    carpeta, destino = Path(carpeta), Path(destino)
    envolvente = carpeta / "envolvente.json"
    if not envolvente.is_file():
        raise ValueError(f"{carpeta}: falta envolvente.json; vuelve a construir la pieza")
    caja = json.loads(envolvente.read_text(encoding="utf-8"))
    rasgos = (json.loads((carpeta / "rasgos.json").read_text(encoding="utf-8"))
              if (carpeta / "rasgos.json").is_file() else [])
    destino.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_step_de(carpeta), destino / f"{id_}.step")
    montados, despejar = _montados(rasgos, destino)
    datos = {
        "id": id_, "nombre": nombre, "origen": "impreso", "proyecto": proyecto,
        "verificado": False,
        "fuentes": [{"url": f"proyecto {proyecto or carpeta.name}",
                     "cita": f"construida por Intelliprint ({carpeta.name})"}],
        "marco": "El de la pieza construida: el mismo origen y los mismos ejes que su programa.",
        "mira": "+z",
        "cuerpos": [{"nombre": nombre, "en": [0, 0, 0],
                     "step": {"ruta": f"{id_}.step", "min": caja["min"], "max": caja["max"]}},
                    *montados],
        "despejar": despejar,
        "fijacion": _agujeros(rasgos),
    }
    Ficha(**datos)   # que no se guarde una ficha que luego no carga
    ruta = destino / f"{id_}.yaml"
    ruta.write_text(yaml.safe_dump(datos, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return ruta


# --- el avance pieza a pieza (F7.2 (desglose)) ---------------------------------------------

OBRA, APROBADA, NODOS, FICHAS, ARCHIVO = "obra.json", "obra_aprobada", "nodos", "fichas", "archivo"
ESPERAN_A_LA_PERSONA = ("concepto por aprobar", "diseñada", "con fallos")


def _ahora() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def es_obra(carpeta: Path) -> bool:
    return (Path(carpeta) / OBRA).is_file()


def cargar_obra(carpeta: Path) -> Obra:
    return Obra.model_validate_json((Path(carpeta) / OBRA).read_text(encoding="utf-8"))


def id_de_ficha(nodo: str) -> str:
    """`obra-<id>`: no choca con los ids de la biblioteca, y «base» a secas
    saldría como componente mencionado en cualquier petición."""
    return f"obra-{nodo}"


def carpeta_de_fichas(carpeta: Path) -> Path:
    return Path(carpeta) / FICHAS


def _marca(ruta: Path, **datos) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps({**datos, "cuando": datos.get("cuando") or _ahora()},
                               ensure_ascii=False), encoding="utf-8")


def guardar(carpeta: Path, obra: Obra, por: str) -> None:
    """El desglose propuesto. Un solo nodo no espera otro visto bueno: es el
    flujo de pieza de siempre, con su concepto, sin pasos extra."""
    carpeta = Path(carpeta)
    (carpeta / OBRA).write_text(obra.model_dump_json(indent=2), encoding="utf-8")
    (carpeta / "obra.md").write_text(presentar(obra), encoding="utf-8")
    if len(obra.nodos) == 1:
        _marca(carpeta / APROBADA, por=f"{por} (un solo nodo)")


def presentar(obra: Obra) -> str:
    lineas = [f"# {obra.titulo}: el desglose", ""]
    for i in obra.orden():
        n = obra.nodo(i)
        tipo = ", conjunto" if n.tipo == "conjunto" else ""
        lineas.append(f"- **{n.nombre}** (`{n.id}`{tipo}): {n.que_hace}")
        for titulo, cosas in (("compra", n.compra), ("depende de", n.depende_de),
                              ("ofrece", n.ofrece), ("necesita", n.necesita)):
            if cosas:
                lineas.append(f"  - {titulo}: {'; '.join(cosas)}")
    return "\n".join(lineas) + "\n"


def aprobada(carpeta: Path) -> bool:
    return (Path(carpeta) / APROBADA).is_file()


def _archivar(carpeta: Path, *rutas: Path) -> Path:
    """Archivar no es borrar: un intento descartado es la única prueba de
    por qué no valía."""
    carpeta = Path(carpeta)
    destino = carpeta / ARCHIVO / f"{dt.datetime.now():%Y%m%d-%H%M%S-%f}"
    for r in rutas:
        if r.exists():
            nuevo = destino / r.relative_to(carpeta)
            nuevo.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(r), str(nuevo))
    return destino


def lista(carpeta: Path, nodo: str) -> dict | None:
    """La marca de «está bien, la siguiente», o None."""
    ruta = Path(carpeta) / NODOS / nodo / "lista.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.is_file() else None


def _estado_pieza(nodo: Path) -> str:
    from orchestrator.pieza import APROBADO, CONCEPTO, RETOQUE
    from orchestrator.registry import LATIDO, LATIDO_VALE_S
    latido = nodo / LATIDO
    # Corrigiendo la base del pan-tilt desde la web (2026-11-09) su tarjeta
    # decía «Concepto aprobado»: que se está corrigiendo tiene que verse.
    corrige = (nodo / RETOQUE).is_file()
    if latido.exists() and time.time() - latido.stat().st_mtime < LATIDO_VALE_S:
        return "corrigiendo" if corrige else "diseñando"
    informe = nodo / "pieza_report.json"
    if informe.is_file():
        resuelto = json.loads(informe.read_text(encoding="utf-8")).get("resuelto")
        return "diseñada" if resuelto else "con fallos"
    if (nodo / "blocked.md").is_file():
        return "con fallos"
    if corrige:
        return "corrigiendo"
    if (nodo / CONCEPTO).is_file():
        return "concepto aprobado" if (nodo / APROBADO).is_file() else "concepto por aprobar"
    return "pendiente"


def estados(carpeta: Path) -> dict[str, str]:
    """El estado de cada nodo, en orden: «lista»; «bloqueado» si algo de lo
    que depende no lo está; para un conjunto, lo que dijo su verificación
    (F7.4 (conjunto)): por verificar, verificando, verificado o con choques;
    o lo que diga la carpeta de la pieza: pendiente, concepto por aprobar,
    concepto aprobado, diseñando, diseñada, con fallos."""
    carpeta = Path(carpeta)
    obra = cargar_obra(carpeta)
    salida: dict[str, str] = {}
    for i in obra.orden():
        n = obra.nodo(i)
        if lista(carpeta, i):
            salida[i] = "lista"
        elif any(salida[d] not in HECHOS for d in n.depende_de):
            salida[i] = "bloqueado"
        elif n.tipo == "conjunto":
            salida[i] = _estado_conjunto(carpeta / NODOS / i)
        else:
            salida[i] = _estado_pieza(carpeta / NODOS / i)
    return salida


HECHOS = ("lista", "verificado")
"""Lo que ya no hay que tocar: una pieza con su visto bueno, o un conjunto
que se movió entero sin chocar."""


def _estado_conjunto(nodo: Path) -> str:
    from orchestrator.conjunto import VERIFICACION
    from orchestrator.registry import LATIDO, LATIDO_VALE_S
    latido = nodo / LATIDO
    if latido.exists() and time.time() - latido.stat().st_mtime < LATIDO_VALE_S:
        return "verificando"
    if not (nodo / VERIFICACION).is_file():
        return "por verificar"
    v = json.loads((nodo / VERIFICACION).read_text(encoding="utf-8"))
    return "verificado" if v.get("ok") else "con choques"


def siguiente(carpeta: Path) -> str | None:
    """El nodo en el que se está: el primero, en orden, que se puede tocar."""
    for i, e in estados(carpeta).items():
        if e not in (*HECHOS, "bloqueado"):
            return i
    return None


def resumen_de_estado(carpeta: Path) -> tuple[str, str]:
    """(estado, motivo) de la obra entera, con las palabras del registro."""
    obra = cargar_obra(carpeta)
    if not aprobada(carpeta):
        return "por aprobar", (f"el desglose en {len(obra.nodos)} piezas espera tu visto "
                               "bueno")
    todos = estados(carpeta)
    i = siguiente(carpeta)
    if i is None:
        return "aprobado", ""
    nombre, e = obra.nodo(i).nombre, todos[i]
    if e == "concepto por aprobar":
        return "por aprobar", f"«{nombre}»: el concepto espera tu visto bueno"
    if e == "diseñada":
        return "por aprobar", f"«{nombre}» está diseñada: revísala y da el visto bueno"
    if e == "con fallos":
        return "fallido", f"«{nombre}» no salió del todo: mira su informe"
    if e == "con choques":
        return "fallido", f"«{nombre}» choca al moverse: mira en qué ángulos"
    return "incompleto", f"falta «{nombre}» ({e})"


def aprobar(carpeta: Path, respuestas: str = "", por: str = "") -> str:
    """El visto bueno a lo que espera: el desglose, o el concepto del nodo en
    el que se está. Con `respuestas` no se aprueba: se guardan y se vuelve a
    proponer, como con el concepto de una pieza (F3.20 (concepto)).
    Devuelve «desglose» o el id del nodo."""
    from orchestrator.pieza import CONCEPTO, aprobar_concepto
    carpeta = Path(carpeta)
    if not aprobada(carpeta):
        if respuestas.strip():
            with (carpeta / "request.md").open("a", encoding="utf-8") as f:
                f.write(f"\nRespuestas al desglose: {respuestas.strip()}\n")
            _archivar(carpeta, carpeta / OBRA, carpeta / "obra.md")
        else:
            _marca(carpeta / APROBADA, por=por)
        return "desglose"
    i = siguiente(carpeta)
    if i is None or estados(carpeta)[i] != "concepto por aprobar":
        raise ValueError("no hay ningún desglose ni concepto esperando el visto bueno")
    nodo = carpeta / NODOS / i
    if respuestas.strip():
        with (nodo / "respuestas.md").open("a", encoding="utf-8") as f:
            f.write(respuestas.strip() + "\n")
        # El concepto contestado es el punto de partida del siguiente: con
        # el cable del SG90 por respuesta, el pan-tilt (2026-11-09) recibió
        # un concepto entero nuevo, sin los tornillos de fijar la base.
        visto = _ultimo_concepto(nodo)
        _archivar(carpeta, nodo / CONCEPTO, nodo / "concepto.md")
        if visto:
            _guardar_anterior(nodo, visto)
    else:
        aprobar_concepto(nodo, por=por)
    return i


def peticion_del_nodo(carpeta: Path, nodo: str) -> str:
    """Lo que se le pide al flujo de pieza para este nodo. Solo lo del nodo:
    con la petición entera, el ingeniero exigiría en cada pieza todos los
    componentes que nombra, y las cifras de una saldrían como requisitos de
    todas."""
    from orchestrator.componentes import cargar
    carpeta = Path(carpeta)
    obra = cargar_obra(carpeta)
    n = obra.nodo(nodo)
    # Sin lo que la persona contestó a los conceptos: va al ingeniero
    # (`pieza._de_la_vuelta_anterior`). Aquí lo leía el agente de requisitos,
    # y cada cifra de una respuesta acababa de requisito.
    if len(obra.nodos) == 1:
        return (carpeta / "request.md").read_text(encoding="utf-8").strip()
    lineas = [f"{n.nombre}: {n.que_hace}.", "",
              f"Es una de las piezas de «{obra.titulo}», que se diseñan una a una: aquí solo "
              "se diseña esta."]
    if n.compra:
        lineas += ["", "Lleva estos componentes comprados: "
                   + ", ".join(f"{cargar(c).nombre} ({c})" for c in n.compra) + "."]
    if n.ofrece:
        lineas += ["", "Lo que da a las demás piezas:", *(f"- {x}" for x in n.ofrece)]
    if n.necesita:
        lineas += ["", "Lo que necesita de las demás:", *(f"- {x}" for x in n.necesita)]
    if n.depende_de:
        lineas += ["", "Se une a estas piezas, ya terminadas. Tienen ficha con su forma "
                   "construida y sus agujeros con nombre: colócalas con `kit.componente` "
                   "y atorníllate a sus agujeros con `punto()`:"]
        lineas += [f"- {obra.nodo(d).nombre}: ficha {id_de_ficha(d)} ({obra.nodo(d).que_hace})"
                   for d in n.depende_de]
    return "\n".join(lineas) + "\n"


def _pieza_construida(nodo: Path) -> Path:
    partes = sorted(p.parent for p in (nodo / "parts").glob("*/envolvente.json"))
    if len(partes) != 1:
        raise ValueError(f"«{nodo.name}»: no hay una pieza construida que congelar "
                         f"({len(partes)} encontradas)")
    return partes[0]


def dar_por_lista(carpeta: Path, nodo: str | None = None, por: str = "",
                  impresa: bool = False, nota: str = "") -> str:
    """«Está bien, la siguiente»: congela el nodo y lo ficha, para que los
    que dependen de él se diseñen contra su forma real. Lo decide la persona
    con su visto bueno (decidido con el usuario, 2026-11-09)."""
    carpeta = Path(carpeta)
    obra = cargar_obra(carpeta)
    nodo = nodo or siguiente(carpeta)
    if nodo is None:
        raise ValueError("la obra ya está terminada")
    estado = estados(carpeta)[nodo]
    if estado not in ("diseñada", "con fallos"):
        raise ValueError(f"«{nodo}» está «{estado}»: no hay pieza diseñada que dar por buena")
    fichar(_pieza_construida(carpeta / NODOS / nodo), id_de_ficha(nodo),
           obra.nodo(nodo).nombre, carpeta_de_fichas(carpeta), proyecto=carpeta.name)
    _marca(carpeta / NODOS / nodo / "lista.json", por=por, impresa=impresa, nota=nota)
    return nodo


def marcar_impresa(carpeta: Path, nodo: str, nota: str = "") -> None:
    """La prueba física, que el sistema no puede hacer: queda registrada y
    no frena nada."""
    marca = lista(carpeta, nodo)
    if marca is None:
        raise ValueError(f"«{nodo}» todavía no está dada por buena")
    _marca(Path(carpeta) / NODOS / nodo / "lista.json",
           **{**marca, "impresa": True, "nota": nota or marca.get("nota", "")})


def rehacer(carpeta: Path, nodo: str, cambio: str = "") -> list[str]:
    """Vuelve a diseñar `nodo`, y con él lo que se diseñó contra su ficha,
    que ya no será la misma. Todo se archiva, nada se borra. Devuelve los
    nodos archivados."""
    from orchestrator.pieza import CAMBIOS
    carpeta = Path(carpeta)
    obra = cargar_obra(carpeta)
    # Lo que se lleva a la vuelta nueva, leído antes de archivar. Sin esto
    # la base del pan-tilt (2026-11-09) salió de cero cada vez, y el segundo
    # cambio borró el primero.
    dir_nodo = carpeta / NODOS / nodo
    anterior = _ultimo_concepto(dir_nodo)
    previos = (dir_nodo / CAMBIOS).read_text(encoding="utf-8").strip() \
        if (dir_nodo / CAMBIOS).is_file() else ""
    # Lo que la persona contestó (por dónde sale un cable) sigue siendo
    # verdad aunque la pieza se rehaga por otra cosa.
    respuestas = (dir_nodo / "respuestas.md").read_text(encoding="utf-8") \
        if (dir_nodo / "respuestas.md").is_file() else ""
    rehechos = []
    for i in [nodo, *obra.dependientes(nodo)]:
        fichas = carpeta_de_fichas(carpeta)
        rutas = [carpeta / NODOS / i, fichas / f"{id_de_ficha(i)}.yaml",
                 fichas / f"{id_de_ficha(i)}.step"]
        if any(r.exists() for r in rutas):
            _archivar(carpeta, *rutas)
            rehechos.append(i)
    todos = "\n".join(c for c in (previos, cambio.strip()) if c)
    if todos or anterior or respuestas:
        dir_nodo.mkdir(parents=True, exist_ok=True)
    if respuestas:
        (dir_nodo / "respuestas.md").write_text(respuestas, encoding="utf-8")
    if todos:
        (dir_nodo / CAMBIOS).write_text(todos + "\n", encoding="utf-8")
    if anterior:
        _guardar_anterior(dir_nodo, anterior)
    return rehechos


LO_CONSTRUIDO = ("parts", "fabrication", "pieza_report.json", "blocked.md", "rounds.json",
                 "lista.json")
"""Lo que deja el diseño de un nodo; la spec y el concepto aprobados son de
antes y se quedan."""


def programa_construido(carpeta: Path, nodo: str) -> str | None:
    """El programa de la pieza de `nodo`, si está construida y su concepto
    aprobado: entonces se puede corregir en vez de diseñarla otra vez."""
    from orchestrator.pieza import APROBADO
    dir_nodo = Path(carpeta) / NODOS / nodo
    if not (dir_nodo / APROBADO).is_file():
        return None
    try:
        programa = _pieza_construida(dir_nodo) / "programa.py"
    except ValueError:
        return None
    return programa.read_text(encoding="utf-8") if programa.is_file() else None


def corregir(carpeta: Path, nodo: str, cambio: str) -> list[str]:
    """Corrige la pieza de `nodo` como lo haría una persona: abre la que hay
    y cambia lo que se le pide. La base del pan-tilt (2026-11-09) tenía la
    tuerca 2 mm demasiado cerca de una cara, y rehacerla volvía a pedir
    especificación, concepto, visto bueno y un diseño desde cero; salía otra
    pieza, y otras cosas cambiaban sin que nadie lo pidiera.

    Se quedan la spec y el concepto aprobados; lo construido se archiva y su
    programa queda como punto de partida (`retoque.json`). Lo que se diseñó
    contra la ficha del nodo se archiva entero: la ficha va a cambiar.
    Devuelve los nodos archivados."""
    from orchestrator.pieza import CAMBIOS, RETOQUE
    carpeta = Path(carpeta)
    obra = cargar_obra(carpeta)
    programa = programa_construido(carpeta, nodo)
    if programa is None:
        raise ValueError(f"«{nodo}» no tiene una pieza construida que corregir")
    if not cambio.strip():
        raise ValueError("para corregir una pieza hay que decir qué cambiar")
    dir_nodo = carpeta / NODOS / nodo
    fichas = carpeta_de_fichas(carpeta)
    _archivar(carpeta, *(dir_nodo / n for n in (*LO_CONSTRUIDO, RETOQUE)),
              fichas / f"{id_de_ficha(nodo)}.yaml", fichas / f"{id_de_ficha(nodo)}.step")
    rehechos = [nodo]
    for i in obra.dependientes(nodo):
        rutas = [carpeta / NODOS / i, fichas / f"{id_de_ficha(i)}.yaml",
                 fichas / f"{id_de_ficha(i)}.step"]
        if any(r.exists() for r in rutas):
            _archivar(carpeta, *rutas)
            rehechos.append(i)
    (dir_nodo / RETOQUE).write_text(json.dumps({"programa": programa, "cambio": cambio.strip()},
                                               ensure_ascii=False, indent=1), encoding="utf-8")
    with (dir_nodo / CAMBIOS).open("a", encoding="utf-8") as f:
        f.write(cambio.strip() + "\n")
    return rehechos


def _ultimo_concepto(nodo: Path) -> str | None:
    """El último concepto que vio la persona en este nodo: el de ahora si lo
    hay y se sostiene, si no el anterior que ya traía."""
    from orchestrator.pieza import ANTERIOR, CONCEPTO
    from orchestrator.schemas.concepto import ConceptoComprobado
    for nombre in (CONCEPTO, ANTERIOR):
        try:
            texto = (nodo / nombre).read_text(encoding="utf-8")
            ConceptoComprobado.model_validate_json(texto)
            return texto
        except (OSError, ValueError):
            continue
    return None


def _guardar_anterior(nodo: Path, texto: str) -> None:
    from orchestrator.pieza import ANTERIOR
    (nodo / ANTERIOR).write_text(texto, encoding="utf-8")
