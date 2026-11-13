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
        agujero = {"nombre": r["nombre"], "diametro": float(r["diametro_mm"]),
                   "en": [round(float(c), 6) for c in r["entrada"]], "eje": eje}
        # La métrica, si el agujero salió de `tornillo()` (F9.4 (canal)): la
        # pieza siguiente sabe con qué se atornilla a esta, no solo un Ø.
        if r.get("tornillo"):
            agujero["tornillo"] = r["tornillo"]
        salida.append(agujero)
    return salida


def _salidas(rasgos: list[dict], fichas: Path) -> list[dict]:
    """Las salidas de lo comprado que la pieza monta, en el marco de la
    pieza (F9.4 (canal)): el eje sobre el que gira la siguiente. La
    plataforma del pan-tilt 1110-0313 se diseñó contra la ficha del soporte
    y el eje de su SG90 solo le llegaba como un cilindro que dejar libre."""
    from mech_toolkit.componentes import colocar, orientar

    from orchestrator.componentes import cargar
    salida = []
    for r in rasgos:
        if r.get("tipo") != "componente" or not r.get("ficha"):
            continue
        ficha = cargar(r["ficha"], [fichas])
        if ficha.origen == "impreso":
            continue   # las de otra pieza del backlog son de su ficha
        giros = [tuple(g) for g in r.get("giros") or []]
        for s in ficha.salidas:
            salida.append({
                "nombre": f"{r['nombre']}: {s.nombre}",
                "en": [round(float(c), 6) for c in colocar(s.en, r["en"], giros)],
                "eje": _EJES[tuple(orientar(s.eje, giros))],
                "recorrido": list(s.recorrido), "largo": s.largo,
                # F9.7 (acople): la pieza que gira se diseña contra esta
                # ficha y no contra la del servo.
                **({"acople": s.acople.model_dump()} if s.acople else {}),
                "porque": f"la salida «{s.nombre}» del {ficha.id} que monta esta pieza"})
    return salida


def _como_cuerpo(p: dict, de: str, monta: str = "") -> dict:
    """Una primitiva ya colocada (`mech_toolkit.componentes.primitivas`) como
    cuerpo de ficha, con el nombre del componente delante."""
    nombre = f"{de}: {p['nombre']}"
    extra = {"porque": p["porque"]} if p.get("porque") else {}
    if monta:
        extra["monta"] = monta
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
            lista += [_como_cuerpo(p, r["nombre"], ficha.id)
                      for p in primitivas(ficha, r["en"], giros, de)]
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
        "salidas": _salidas(rasgos, destino),
    }
    Ficha(**datos)   # que no se guarde una ficha que luego no carga
    ruta = destino / f"{id_}.yaml"
    ruta.write_text(yaml.safe_dump(datos, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return ruta


# --- el avance pieza a pieza (F7.2 (desglose)) ---------------------------------------------

OBRA, APROBADA, NODOS, FICHAS, ARCHIVO = "obra.json", "obra_aprobada", "nodos", "fichas", "archivo"
PLAN_ANTERIOR = "obra_anterior.json"
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


def guardar(carpeta: Path, obra: Obra, por: str, avisos: list[str] | tuple = ()) -> None:
    """El desglose propuesto. Un solo nodo no espera otro visto bueno: es el
    flujo de pieza de siempre, con su concepto, sin pasos extra. `avisos`:
    lo que la persona tiene que saber del plan antes de aprobarlo."""
    carpeta = Path(carpeta)
    (carpeta / OBRA).write_text(obra.model_dump_json(indent=2), encoding="utf-8")
    (carpeta / "obra.md").write_text(presentar(obra, avisos), encoding="utf-8")
    if len(obra.nodos) == 1:
        _marca(carpeta / APROBADA, por=f"{por} (un solo nodo)")


def presentar(obra: Obra, avisos: list[str] | tuple = ()) -> str:
    lineas = [f"# {obra.titulo}: el desglose", ""]
    for i in obra.orden():
        n = obra.nodo(i)
        tipo = ", conjunto" if n.tipo == "conjunto" else ""
        lineas.append(f"- **{n.nombre}** (`{n.id}`{tipo}): {n.que_hace}")
        for titulo, cosas in (("compra", n.compra), ("depende de", n.depende_de),
                              ("ofrece", n.ofrece), ("necesita", n.necesita)):
            if cosas:
                lineas.append(f"  - {titulo}: {'; '.join(cosas)}")
    if obra.uniones:
        lineas += ["", "## Cómo se unen", "", *(f"- {union_en_palabras(obra, u)}"
                                               for u in obra.uniones)]
    # F9.6 (previsto): la persona aprueba sabiendo qué tornillería lleva, y
    # con eso se comprueba después cada pieza.
    from orchestrator.plan import compras_en_palabras
    try:
        tornilleria = compras_en_palabras(obra)
    except Exception:  # noqa: BLE001 — un plan con una ficha rota se enseña igual
        tornilleria = []
    if tornilleria:
        lineas += ["", "## Lo que lleva de tornillería", "", *(f"- {t}" for t in tornilleria),
                   "", "El largo de cada tornillo se mide en las piezas, cuando estén hechas."]
    if avisos:
        lineas += ["", "## Avisos", "", *(f"- {a}" for a in avisos)]
    return "\n".join(lineas) + "\n"


_AGARRES = {"tuerca": "con tuerca cautiva", "inserto": "con inserto térmico",
            "rosca": "roscados en el plástico"}


def union_en_palabras(obra: Obra, u) -> str:
    """Una unión del plan (F9.2 (uniones)) como la lee la persona antes de
    aprobar: sin ids de ficha ni claves del esquema."""
    from orchestrator.componentes import cargar
    from orchestrator.schemas.obra import EXTERIOR, Fija

    def nombre(i):
        return f"«{obra.nodo(i).nombre}»"

    if isinstance(u, Fija):
        tornillos = f"{u.cantidad} tornillo{'s' if u.cantidad > 1 else ''} {u.metrica}"
        if u.agarra == EXTERIOR:
            grosor = f" de {u.grosor_exterior_mm:g} mm" if u.grosor_exterior_mm else ""
            return f"{nombre(u.cabeza)} se atornilla a algo de fuera{grosor} con {tornillos}"
        return (f"{nombre(u.cabeza)} se atornilla a {nombre(u.agarra)} con {tornillos}, "
                f"{_AGARRES[u.agarre]} en {nombre(u.agarra)}")
    try:
        que = cargar(u.componente).nombre
    except Exception:  # noqa: BLE001 — un plan con una ficha que ya no está se enseña igual
        que = u.componente
    sitio = (f", y necesita {u.radio_libre_mm:g} mm libres alrededor del eje"
             if u.radio_libre_mm else "")
    eje = f", con el eje {u.eje}" if u.eje else ""
    return (f"{nombre(u.gira)} gira {u.recorrido_grados:g}° sobre el {que} de "
            f"{nombre(u.sobre)}{eje}{sitio}{_movida_por(u)}")


def transmision_en_palabras(t) -> str:
    """«correa 4:1», «reductora 30:1»."""
    return f"{t.tipo} {t.relacion:g}:1"


def _movida_por(u) -> str:
    from orchestrator.componentes import cargar
    if u.movido_por is None:
        return ""
    try:
        motor = cargar(u.movido_por.motor).nombre
    except Exception:  # noqa: BLE001 — como arriba: se enseña igual
        motor = u.movido_por.motor
    return f"; la mueve el {motor} por {transmision_en_palabras(u.movido_por)}"


def plan_anterior(carpeta: Path) -> str | None:
    """El plan que la persona vio y contestó, o None."""
    ruta = Path(carpeta) / PLAN_ANTERIOR
    return ruta.read_text(encoding="utf-8") if ruta.is_file() else None


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
    concepto aprobado, diseñando, diseñada, con fallos.

    «por revalidar» (F9.9 (revalidar)): la pieza está hecha, pero algo de lo
    que tiene debajo se corrigió después; mientras eso no vuelva a estar
    listo espera, aunque ella tenga su visto bueno."""
    from orchestrator.revalidar import MARCA
    carpeta = Path(carpeta)
    obra = cargar_obra(carpeta)
    salida: dict[str, str] = {}
    for i in obra.orden():
        n = obra.nodo(i)
        revalidar = n.tipo == "pieza" and (carpeta / NODOS / i / MARCA).is_file()
        if lista(carpeta, i) and not revalidar:
            salida[i] = "lista"
        elif any(salida[d] not in HECHOS for d in n.depende_de):
            salida[i] = "bloqueado"
        elif revalidar:
            salida[i] = "por revalidar"
        elif n.tipo == "conjunto":
            salida[i] = _estado_conjunto(carpeta / NODOS / i)
        else:
            salida[i] = _estado_pieza(carpeta / NODOS / i)
    return salida


SE_LANZAN = ("pendiente", "concepto aprobado", "por verificar", "por revalidar")
"""Lo que no espera a la persona: basta con lanzar la orden."""

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
    from orchestrator import ampliar
    a_medias = ampliar.pendiente(carpeta)
    if a_medias == "propuesta":
        return "por aprobar", ("la ampliación espera tu visto bueno: "
                               f"«{ampliar.pedida(carpeta)}»")
    if a_medias == "pedida":
        return "incompleto", f"falta proponer la ampliación «{ampliar.pedida(carpeta)}»"
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
            # El plan contestado es el punto de partida del siguiente, como
            # con el concepto de un nodo: desglosando de cero, corregir una
            # unión podía rebarajar todas las piezas (F9.3 (planificador)).
            shutil.copyfile(carpeta / OBRA, carpeta / PLAN_ANTERIOR)
            _archivar(carpeta, carpeta / OBRA, carpeta / "obra.md")
        else:
            _marca(carpeta / APROBADA, por=por)
        return "desglose"
    # F9.10 (ampliar): una función que se añade espera antes que nada más;
    # mientras, el plan no cambia y no se sigue con las piezas.
    from orchestrator import ampliar
    if ampliar.pendiente(carpeta) == "propuesta":
        ampliar.aprobar(carpeta, respuestas=respuestas, por=por)
        return "ampliación"
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
    from orchestrator.traceability import CONTEXTO
    lineas = [f"{n.nombre}: {n.que_hace}."]
    if n.ofrece:
        lineas += ["", "Lo que da a las demás piezas:", *(f"- {x}" for x in n.ofrece)]
    if n.necesita:
        lineas += ["", "Lo que necesita de las demás:", *(f"- {x}" for x in n.necesita)]
    # De aquí abajo lo escribe el sistema, y sus cifras no son cotas de la
    # pieza: el nombre de una ficha («NEMA 17 (17HS4401, 40 mm)») o lo que
    # hace la pieza vecina («150 mm entre ejes»). Ver `traceability.CONTEXTO`.
    lineas += ["", CONTEXTO, "",
               f"Es una de las piezas de «{obra.titulo}», que se diseñan una a una: aquí solo "
               "se diseña esta."]
    if n.compra:
        lineas += ["", "Lleva estos componentes comprados: "
                   + ", ".join(f"{cargar(c).nombre} ({c})" for c in n.compra) + "."]
    if n.depende_de:
        lineas += ["", "Se une a estas piezas, ya terminadas. Tienen ficha con su forma "
                   "construida y sus agujeros con nombre: colócalas con `kit.componente` "
                   "y atorníllate a sus agujeros con `punto()`:"]
        for d in n.depende_de:
            dep = obra.nodo(d)
            lineas.append(f"- {dep.nombre}: ficha {id_de_ficha(d)} ({dep.que_hace})")
            # Banco 1109-1949: la plataforma colocó otra vez el SG90 que ya
            # montaba el soporte de giro. Su ficha lo trae, con el eje.
            for c in dict.fromkeys(dep.compra):
                lineas.append(f"  Esta pieza ya lleva {c} montado: su cuerpo, su eje y lo que hay que dejar "
                              f"libre están en la ficha {id_de_ficha(d)}; no coloques otro {c}.")
    return "\n".join(lineas) + "\n"


def ajenos(carpeta: Path, nodo: str) -> dict[str, dict]:
    """Lo comprado que monta OTRA pieza del backlog: cuántos puede colocar
    este nodo (los suyos, de `compra`) y qué decirle si coloca más. Lo
    aplica el kit. Lo que no compra nadie no sale: no hay con qué duplicarse.

    `lejos`: ni lo compra este nodo ni lo monta una pieza a la que se une.
    El antebrazo del brazo mediano (banco 1113-1330) recibió en cada intento
    «no colocaste el cicloidal-nema17-28 (…) No lo coloques otra vez»: era
    el de la torreta, dos piezas más abajo, que su petición nombra al contar
    qué hace el brazo superior. Ni la ficha de la vecina lo trae ni el kit
    deja colocarlo: lo de lejos no se le exige a la pieza ni a su concepto."""
    obra = cargar_obra(Path(carpeta))
    n = obra.nodo(nodo)
    salida = {}
    for c in {c for otro in obra.nodos if otro.id != nodo for c in otro.compra}:
        quien = [o for o in obra.nodos if o.id != nodo and c in o.compra]
        nombres = " y ".join(f"«{o.nombre}» (ficha {id_de_ficha(o.id)})" for o in quien)
        cuantos = n.compra.count(c)
        lejos = not cuantos and not any(o.id in n.depende_de for o in quien)
        salida[c] = {"cuantos": cuantos, "lejos": lejos, "mensaje": (
            f"el {c} lo monta {nombres}; esta pieza compra {cuantos}. No lo coloques otra "
            f"vez: coloca la ficha de esa pieza con `kit.componente`, que ya lleva el {c} "
            "con su eje y lo que hay que dejar libre, y usa sus puntos.")}
    return salida


# --- las uniones de cada nodo (F9.4 (canal)) -------------------------------------------------

UNIONES = "uniones.json"

_COMO_AGARRA = {
    "tuerca": 'con tuerca cautiva: `tuerca(..., "{m}")` y su agujero pasante en línea',
    "inserto": 'con inserto térmico: `tornillo(..., "{m}", tipo="inserto")`',
    "rosca": 'roscados en el plástico: `tornillo(..., "{m}", tipo="rosca")`',
}


def _salidas_en_la_ficha(carpeta: Path, sobre: str, componente: str, salida: str) -> list[str]:
    """Cómo se llama en la ficha de `sobre` la salida sobre la que se gira:
    «<nombre que le dio al componente>: <salida>». Vacío si `sobre` aún no
    está fichada o su ficha es de antes de guardar las salidas."""
    from orchestrator.componentes import cargar
    try:
        ficha = cargar(id_de_ficha(sobre), [carpeta_de_fichas(carpeta)])
    except KeyError:
        return []
    return [s.nombre for s in ficha.salidas
            if s.nombre.endswith(f": {salida}") and f"del {componente} " in s.porque]


def uniones_del_nodo(carpeta: Path, nodo: str) -> list[dict]:
    """Lo que el plan decidió de este nodo, una entrada por unión: la unión,
    el `papel` del nodo en ella (gira, sobre, cabeza o agarra), el `otro`
    nodo y un `texto` para quien lo diseña.

    No va en `peticion_del_nodo`: esa la lee el agente de requisitos, que
    hace un requisito de cada cifra que ve. Va por aquí al ingeniero, al
    diseñador y a las medidas."""
    from orchestrator.componentes import acople_en_palabras, cargar
    from orchestrator.plan import salida_de
    from orchestrator.schemas.obra import EXTERIOR, Fija
    from orchestrator.transmision import para_quien_gira, para_quien_monta

    carpeta = Path(carpeta)
    obra = cargar_obra(carpeta)
    yo = obra.nodo(nodo)

    def nombre(i):
        return f"«{obra.nodo(i).nombre}»"

    def a_cada_lado(u, ficha) -> str:
        """Qué grados son, si el plan pide menos de lo que da el actuador:
        el conjunto se barre así (`conjunto._lo_pedido`), y quien dibuja
        tiene que saber desde dónde se cuenta. Con el recorrido entero no
        hay nada que aclarar."""
        lo, hi = salida_de(u, ficha).recorrido
        if u.recorrido_grados >= hi - lo - 1e-6:
            return ""
        return (f" Son {u.recorrido_grados / 2:g}° a cada lado de como se dibuje: se dibuja "
                "en mitad de su recorrido, y es en esos ángulos donde no puede chocar con "
                "nada.")

    def como_va_puesta(u) -> str:
        """Hacia dónde mira el eje, si el plan lo dice. El soporte del banco
        1113-0216 tenía «con el eje horizontal» en su encargo y se dibujó
        como mejor se imprime, con el eje hacia arriba."""
        if not u.eje:
            return ""
        como = ("paralelo a la mesa" if u.eje == "horizontal" else "hacia arriba, en z")
        return (f" El eje de ese giro va {u.eje}: dibuja esta pieza como va a quedar puesta "
                f"cuando se use, con z hacia arriba, y con el eje del {u.componente} {como}. "
                "No la tumbes para imprimirla mejor: se mide como la dibujes.")

    def movida(u, ficha) -> str:
        """A la pieza que monta el rodamiento y el motor: que el uno mueve
        lo que gira en el otro (F10.2 (transmisión)). Sin esto llevaría un
        motor en `compra` sin saber para qué."""
        if u.movido_por is None:
            return ""
        motor = cargar(u.movido_por.motor)
        if u.movido_por.tipo == "reductora":
            # Lo de «paralelo y a un lado» es de una correa (F10.7 (cicloidal)).
            return (f" La mueve el {motor.nombre} que también monta esta pieza, a través de "
                    f"esa reductora: los dos van en el mismo eje, con una pared de esta pieza "
                    "entre ellos. El motor por un lado de la pared, con su cara contra ella; "
                    "la reductora por el otro, con su cara de abajo contra ella y la salida "
                    "hacia fuera. Los cuatro tornillos del motor atraviesan la reductora y la "
                    "pared: la pared lleva sus cuatro pasantes y el paso del eje, y tiene que "
                    "ser fina (el eje del motor ha de entrar en la reductora).")
        return (f" No la mueve el {ficha.nombre}, que solo la deja girar: la mueve el "
                f"{motor.nombre} que también monta esta pieza, por "
                f"{transmision_en_palabras(u.movido_por)}. Pon el eje del motor paralelo al "
                f"del {u.componente} y a un lado, con sitio entre los dos para la "
                "transmisión." + (para_quien_monta(u, nombre(u.gira), motor.nombre)
                                  if u.movido_por.tipo == "correa" else ""))

    def donde_sale(u, otro) -> str:
        """De qué lado de los agujeros de `otro`, que lleva la cabeza, va
        esta pieza. El soporte de la pinza del banco 1112-1359 se puso
        donde `punto()` da el agujero, que es por donde entra la cabeza: el
        recuento leyó los dos M3 al revés y los dio por sueltos, y cinco
        intentos no lo sacaron de ahí porque nadie le dijo de qué lado iba."""
        if u.cabeza != otro:
            return ""
        try:
            from orchestrator.tornilleria import tornillos
            # Sin esta pieza ni lo que lleva encima: si ya está construida
            # (se está corrigiendo), sus agujeros comparten recta con esos.
            fuera = (nodo, *obra.dependientes(nodo))
            largos = {round(t.largo_mm, 1) for t in tornillos(carpeta, sin=fuera)
                      if t.piezas == [otro] and not t.componente
                      and t.metrica == u.metrica and t.termina == "superficie"}
        except Exception:  # noqa: BLE001  (sin medida se dice igual, sin la cifra)
            largos = set()
        cuanto = f", {largos.pop():g} mm más allá" if len(largos) == 1 else ""
        return (f" En {nombre(otro)} va la cabeza: entra por donde `punto()` da cada "
                "agujero, avanza hacia su `eje` (`agujeros()` lo da) y sale por el otro "
                f"lado{cuanto}. Esta pieza va donde sale el tornillo; del lado de `punto()` "
                "no, que ahí va la cabeza.")

    def lleva_un_giro(otro) -> str:
        """Lo que girará sobre `otro`, que aún no existe: quien taladra
        ahora decide dónde cabrá ese eje (`medida.sin_sitio_para_lo_nuevo`)."""
        from orchestrator.schemas.obra import Gira
        giros = [g for g in obra.uniones
                 if isinstance(g, Gira) and g.sobre == otro and g.radio_libre_mm]
        if not giros:
            return ""
        g = max(giros, key=lambda g: g.radio_libre_mm)
        return (f" Sobre {nombre(otro)} girará {nombre(g.gira)}, que necesita "
                f"{g.radio_libre_mm:g} mm libres alrededor de su eje en cualquier ángulo de "
                "los giros de debajo: tiene que caber saliendo de esos agujeros. Lo normal es "
                "la cara que mira hacia fuera del invento, lejos de la base.")

    def cuando(otro, u=None):
        """El otro ya está hecho (dependo de él) o se hará después."""
        if otro in yo.depende_de:
            return (f" {nombre(otro)} ya está hecha: colócala con `kit.componente("
                    f"\"{id_de_ficha(otro)}\", ...)` y pon tus agujeros en línea con los "
                    "suyos, que tienen nombre en su ficha (`punto()`)."
                    + (donde_sale(u, otro) if u is not None else ""))
        # A la plataforma del banco 1112-1359 no se le dijo, y puso los de
        # la pinza en la cara que da al servo. Sin nada debajo no hay a qué
        # dar, y el texto de una base no cambia.
        sitio = (f" {nombre(otro)} irá al otro lado de esos agujeros: ponlos en una cara que "
                 "dé a un sitio libre, sin nada de las piezas sobre las que va esta ni de lo "
                 "comprado que montan." + lleva_un_giro(otro) + " Al construir se mide."
                 if yo.depende_de else "")
        return (f" {nombre(otro)} se diseñará después, contra esta: da a cada agujero un "
                f"nombre que diga para qué es.{sitio}")

    salida = []
    for u in obra.uniones_de(nodo):
        dato = {**u.model_dump(), "papel": "", "otro": None, "texto": ""}
        if isinstance(u, Fija):
            tornillos = f"{u.cantidad} tornillo{'s' if u.cantidad > 1 else ''} {u.metrica}"
            if u.agarra == EXTERIOR:
                grosor = (f", de {u.grosor_exterior_mm:g} mm de grueso"
                          if u.grosor_exterior_mm else "")
                dato.update(papel="cabeza", texto=(
                    f"Se atornilla a algo de fuera{grosor} (una mesa, un tablero) con "
                    f"{tornillos}: esta pieza lleva los {u.cantidad} agujeros pasantes "
                    f"(`tornillo(..., \"{u.metrica}\")`) y en ella apoya la cabeza."))
            elif u.cabeza == nodo:
                dato.update(papel="cabeza", otro=u.agarra, texto=(
                    f"Se atornilla a {nombre(u.agarra)} con {tornillos}: en esta pieza apoya "
                    f"la cabeza, así que lleva los {u.cantidad} agujeros pasantes "
                    f"(`tornillo(..., \"{u.metrica}\")`); donde agarran es en "
                    f"{nombre(u.agarra)}." + cuando(u.agarra)))
            else:
                dato.update(papel="agarra", otro=u.cabeza, texto=(
                    f"{nombre(u.cabeza)} se atornilla a esta pieza con {tornillos}, que "
                    f"aquí agarran {_COMO_AGARRA[u.agarre].format(m=u.metrica)}."
                    + cuando(u.cabeza, u)))
        else:
            ficha = cargar(u.componente)
            eje = salida_de(u, ficha)
            radio = u.radio_libre_mm
            if u.gira == nodo:
                en_ficha = _salidas_en_la_ficha(carpeta, u.sobre, u.componente, eje.nombre)
                como = (f"`componente.salida(\"{en_ficha[0]}\")`" if len(en_ficha) == 1
                        else "`componente.salidas()`")
                dato.update(papel="gira", otro=u.sobre, salidas=en_ficha, texto=(
                    f"Esta pieza gira {u.recorrido_grados:g}° sobre el {ficha.nombre} que "
                    f"monta {nombre(u.sobre)}.{a_cada_lado(u, ficha)} Coloca {nombre(u.sobre)} con `kit.componente("
                    f"\"{id_de_ficha(u.sobre)}\", ...)`: {como} te da el punto por donde sale "
                    "el eje y hacia dónde. Acóplate a él por delante de esa cara. Toda la "
                    "pieza va por delante de ella: detrás están el actuador y lo que lo "
                    f"sujeta, y ahí no tiene sitio. No toques la carcasa ni a {nombre(u.sobre)} "
                    "(deja al menos 1 mm) y no te atornilles a ella: lo único que os une es "
                    "el eje."
                    + (f" Al eje te une su {acople_en_palabras(eje.acople)}. Deja sitio al "
                       "cubo y atorníllate a esos agujeros (`salida()[\"acople\"]` los da), "
                       "con los brazos en la dirección que te convenga; no a presión."
                       if eje.acople else "")
                    + (f" Nada de esta pieza puede quedar a más de {radio:g} mm de ese eje: "
                       f"es el sitio que {nombre(u.sobre)} deja libre." if radio else "")
                    # Lo de «por delante de la cara» es de un servo. En un
                    # rodamiento, hecha a mano (2026-11-12), un eje justo
                    # (0,05 mm) se dio por choque al mover el conjunto.
                    + (f" Aquí la salida es un aro de {eje.largo:g} mm de ancho que gira: lo "
                       "único de esta pieza que entra en él es un eje que lo atraviesa, y "
                       "con la holgura «slide» del perfil (`kit.holgura(\"slide\")`, en "
                       "diámetro): más justo, al mover el conjunto cuenta como choque."
                       if eje.largo and not eje.acople else "")
                    # El brazo del banco 1113-0423 se quedó en 149,1 mm de 150
                    # para no pasarse de su radio: nadie le dijo que llegara.
                    + (f" La punta de esta pieza tiene que llegar a {u.brazo_mm:g} mm de ese "
                       "eje: ni menos, ni más de lo que tiene reservado. Al construir se mide."
                       if u.brazo_mm and not any(isinstance(o, type(u)) and o.sobre == nodo
                                                 for o in obra.uniones) else "")
                    + (para_quien_gira(u, nombre(u.sobre))
                       if u.movido_por and u.movido_por.tipo == "correa" else "")))
            else:
                dato.update(papel="sobre", otro=u.gira, texto=(
                    f"{nombre(u.gira)} girará {u.recorrido_grados:g}° sobre el {ficha.nombre} "
                    f"que monta esta pieza.{a_cada_lado(u, ficha)}"
                    + (f" Necesita sitio: alrededor del eje de salida, desde la cara por "
                       f"donde sale hacia fuera, tiene que quedar libre un cilindro de radio "
                       f"{radio:g} mm. Ahí no puede haber nada de esta pieza, ni de las "
                       "piezas sobre las que va, ni de lo comprado que montan, en ningún "
                       f"ángulo. Pon el {u.componente} lo bastante alto o lo bastante afuera "
                       "para que así sea, y sujétalo por detrás de esa cara. Al construir "
                       "se mide." if radio else "")
                    + como_va_puesta(u)
                    + movida(u, ficha)))
        salida.append(dato)
    return salida


def sujeciones_del_nodo(carpeta: Path, nodo: str) -> list[dict]:
    """Con qué tornillos se sujeta lo comprado que monta el nodo, según su
    ficha (F9.6 (previsto)): una entrada por componente y métrica, con su
    `texto` para quien lo diseña.

    Las bases de los pan-tilt del banco alojaban su SG90 sin un tornillo: la
    ficha lo decía en «Agujeros de fijación», entre otras veinte líneas, y
    nadie lo pedía. Se cuenta al construir (`medida.uniones_sin_hacer`)."""
    from orchestrator.componentes import cargar
    from orchestrator.plan import compras_previstas

    carpeta = Path(carpeta)
    fichas = [carpeta_de_fichas(carpeta)]
    salida = []
    for p in compras_previstas(cargar_obra(carpeta), fichas):
        if not p.componente or p.piezas != (nodo,):
            continue
        ficha = cargar(p.componente, fichas)
        que = ficha.nombre
        tornillos = f"{p.cantidad} tornillo{'s' if p.cantidad > 1 else ''} {p.metrica}"
        d = float(p.metrica.lstrip("Mm"))
        en_la_pieza = any(f.rosca_en_la_pieza for f in ficha.fijacion
                          if f.tornillo == p.metrica)
        salida.append({"tipo": "sujeta", "id": p.componente, "metrica": p.metrica,
                       "cantidad": p.cantidad, "incluido": p.incluido, "texto": (
            f"El {que} que monta esta pieza se sujeta con {tornillos}"
            + (", que vienen con él" if p.incluido else ", que se compran aparte")
            + ", uno por cada fijación de su ficha. `componente.agujeros()` da de cada una el "
            "punto (`en`), hacia dónde va el tornillo (`eje`) y cuánto de él queda dentro del "
            "componente (`dentro_mm`). "
            + ("Atraviesan el componente y roscan en esta pieza: justo detrás de cada "
               "fijación va un agujero ciego en línea, más estrecho que el tornillo "
               f"({d:g} mm): `tornillo(..., \"{p.metrica}\", tipo=\"rosca\", "
               "profundidad=...)` si el perfil tiene esa métrica, y si no, `taladrar` con "
               f"menos de {d:g} y `profundidad`." if en_la_pieza else
               "Roscan en el componente: esta pieza lleva, en línea con cada fijación, el "
               f"agujero pasante por donde entra (`tornillo(..., \"{p.metrica}\")`), con "
               "sitio para la cabeza.")
            + " Al construir se cuentan.")})
    return salida


def escribir_uniones(carpeta: Path, nodo: str) -> Path:
    """Deja las uniones del nodo en su carpeta, donde las busca el flujo de
    pieza, que no sabe nada del backlog. Y con ellas, con qué se sujeta lo
    comprado que monta."""
    ruta = Path(carpeta) / NODOS / nodo / UNIONES
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps([*uniones_del_nodo(carpeta, nodo),
                                *sujeciones_del_nodo(carpeta, nodo)],
                               ensure_ascii=False, indent=1), encoding="utf-8")
    return ruta


def leer_uniones(dir_nodo: Path) -> list[dict]:
    ruta = Path(dir_nodo) / UNIONES
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.is_file() else []


def uniones_para_el_prompt(dir_nodo: Path) -> str:
    """Las uniones de la pieza de `dir_nodo` como se le dicen al ingeniero y
    al diseñador; vacío si no tiene (una pieza suelta)."""
    uniones = leer_uniones(dir_nodo)
    if not uniones:
        return ""
    return ("Son del plan del proyecto y están aprobadas por la persona. Hazlas tal cual: ni "
            "otra métrica, ni otro agarre, ni otra cantidad, ni menos sitio.\n"
            + "\n".join(f"- {u['texto']}" + ("" if u.get("tipo") == "sujeta"
                                              else f" (unión {u['id']})") for u in uniones))


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
        raise ValueError("el backlog ya está terminado")
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


def _por_revalidar(carpeta: Path, obra: Obra, nodo: str) -> list[str]:
    """Marca lo ya construido contra `nodo`, que se va a cambiar, y dice qué
    nodos quedaron marcados (F9.9 (revalidar)). ANTES de archivar nada de
    `nodo`: la marca se lleva una copia de su ficha de ahora."""
    from orchestrator import revalidar
    return [i for i in obra.dependientes(nodo) if revalidar.marcar(carpeta, i, por=nodo)]


def rehacer(carpeta: Path, nodo: str, cambio: str = "") -> list[str]:
    """Vuelve a diseñar `nodo`. Lo que se diseñó contra su ficha y está
    construido se queda, por revalidar contra la nueva (F9.9 (revalidar));
    lo que no llegó a construirse se archiva con él. Nada se borra. Devuelve
    los nodos archivados."""
    from orchestrator.pieza import CAMBIOS
    carpeta = Path(carpeta)
    obra = cargar_obra(carpeta)
    se_quedan = _por_revalidar(carpeta, obra, nodo)
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
    # La animación de la obra entera ya no sería de lo que hay (F7.6 (animacion)).
    _archivar(carpeta, carpeta / ANIMACION)
    rehechos = []
    for i in [nodo, *(d for d in obra.dependientes(nodo) if d not in se_quedan)]:
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


ANIMACION = "animation.gif"
"""La de la obra entera, copia de la de su último conjunto (F7.6 (animacion))."""

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
    programa queda como punto de partida (`retoque.json`).

    Lo que se diseñó contra la ficha del nodo y está construido NO se
    archiva (F9.9 (revalidar)): queda por revalidar contra la ficha nueva, y
    solo se toca si deja de valer. Hasta el 2026-11-11 se archivaba entero
    «porque la ficha va a cambiar»: al añadirle dos agujeros a la base del
    pan-tilt 1111-1342 se tiraron el soporte y la plataforma buena, y la que
    salió después no llevaba la cámara. Lo que no llegó a construirse —un
    concepto, la verificación de un conjunto— sí se archiva.
    Devuelve los nodos archivados."""
    from orchestrator import revalidar
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
    se_quedan = _por_revalidar(carpeta, obra, nodo)
    # Su propia marca también: si esperaba a revalidarse, ya no hay qué
    # revalidar; se corrige contra las fichas que haya cuando le toque.
    _archivar(carpeta, *(dir_nodo / n for n in (
                  *LO_CONSTRUIDO, RETOQUE, revalidar.MARCA, revalidar.CONTRA, revalidar.HECHA)),
              fichas / f"{id_de_ficha(nodo)}.yaml", fichas / f"{id_de_ficha(nodo)}.step",
              carpeta / ANIMACION)
    rehechos = [nodo]
    for i in obra.dependientes(nodo):
        if i in se_quedan:
            continue
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
