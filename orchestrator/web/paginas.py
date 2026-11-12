"""Las páginas de la web: la galería y la página de cada proyecto (F5.5 (web)).

La anterior era una tabla con un acordeón que volcaba el informe entero
del revisor —27 líneas `cumple/no_cumple`—, las rondas y los «movimientos
medidos». El usuario (2026-10-26): «es horrible», «a un usuario le vale
pito eso». Lo que quiere es ver sus cosas por categorías, entrar en una,
saber si se puede imprimir y cambiarle una pieza con una frase.

Así que aquí solo hay tres cosas: la galería, la página de un proyecto y,
plegado al final de esta, lo técnico para depurar. Todo el texto que
escribió un modelo (títulos, motivos, frases del revisor) se escapa: es
dato, no HTML.
"""

import datetime as dt
import html
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import yaml

from orchestrator.categorias import CATEGORIAS, OTROS, normalizar
from orchestrator.web.documentos import a_html, documentos_de
from orchestrator.web.versiones import piezas_de, resolver_proyecto

e = html.escape

ESTADOS = {
    "aprobado": ("Listo para imprimir", "ok"),
    "antiguo": ("Listo para imprimir", "ok"),
    "con reparos": ("Listo, pero distinto a lo pedido", "ambar"),
    "fallido": ("No salió", "mal"),
    "incompleto": ("Se quedó a medias", "suave"),
    "en marcha": ("Diseñando…", "vivo"),
    "por aprobar": ("Espera tu visto bueno", "ambar"),
}
"""Lo que se le dice al usuario de cada estado del registro, y su color."""

CATEGORIA_FIJADA = "categoria.json"
"""La categoría que el usuario eligió en la web, en la carpeta del proyecto
(la de su primera versión). Manda sobre la que propuso el diseñador."""

MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def _leer(ruta: Path):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _recortar(texto: str, n: int) -> str:
    """Corta en un espacio, no a mitad de palabra."""
    texto = " ".join((texto or "").split())
    if len(texto) <= n:
        return texto
    corte = texto.rfind(" ", 0, n)
    return texto[:corte if corte > n * 0.6 else n].rstrip(" ,;:.") + "…"


def _fecha(id_: str) -> str:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", id_)
    return f"{int(m.group(3))} {MESES[int(m.group(2)) - 1]}" if m else ""


def _carpeta(workspace: Path, v: dict) -> Path:
    return Path(workspace) / v["seccion"] / v["id"]


def _ficha(carpeta: Path) -> dict:
    """Lo que el sistema dijo de la versión: `mechanism.json` en un
    mecanismo, `pieza.json` en una pieza suelta (F5.17 (pieza)). Leyendo
    solo el primero, dos soportes del 608ZZ distintos se llamaban igual y
    caían en «Otros» (2026-11-08). Una obra (F7.2 (desglose)) lleva su
    título en el desglose."""
    obra = _leer(carpeta / "obra.json")
    if obra:
        return {"title": obra.get("titulo")}
    return _leer(carpeta / "mechanism.json") or _leer(carpeta / "pieza.json") or {}


def nombre_de(workspace: Path, g: dict) -> str:
    """El nombre que le dio el diseñador a su mejor versión, o la primera
    línea de la petición. Con la petición cortada a 60 caracteres, dos
    sargentos se llamaban igual: «…imprimible en 3D, par»."""
    for v in [next(x for x in g["versiones"] if x["id"] == g["mejor"]), *g["versiones"]]:
        titulo = _ficha(_carpeta(workspace, v)).get("title")
        if titulo:
            return titulo
    primera = _carpeta(workspace, g["versiones"][0]) / "request.md"
    linea = (primera.read_text(encoding="utf-8", errors="ignore").strip().splitlines() or [""])[0] \
        if primera.is_file() else ""
    return _recortar(linea or g["id"], 70)


def categoria_de(workspace: Path, g: dict) -> str:
    raiz = _carpeta(workspace, g["versiones"][0])
    fijada = (_leer(raiz / CATEGORIA_FIJADA) or {}).get("categoria")
    if fijada:
        return normalizar(fijada)
    for v in [next(x for x in g["versiones"] if x["id"] == g["mejor"]), *reversed(g["versiones"])]:
        propuesta = _ficha(_carpeta(workspace, v)).get("categoria")
        if propuesta:
            return normalizar(propuesta)
    if any((_carpeta(workspace, v) / "calibracion.md").is_file() for v in g["versiones"]):
        return "calibración"
    return OTROS


def fijar_categoria(workspace: Path, proyecto: str, categoria: str) -> None:
    raiz = resolver_proyecto(proyecto, workspace)
    (raiz / CATEGORIA_FIJADA).write_text(
        json.dumps({"categoria": categoria}, ensure_ascii=False), encoding="utf-8")


TIPOS = (("pieza", "Piezas"), ("mecanismo", "Mecanismos"), ("ensamble", "Ensambles"),
         ("robot", "Robots"))
ETAPAS = (("diseñando", "Diseñando"), ("por-aprobar", "Por aprobar"), ("listo", "Listos"),
          ("impreso", "Impresos"), ("no-salio", "No salieron"))
_ETAPA_DE_ESTADO = {"en marcha": "diseñando", "por aprobar": "por-aprobar", "aprobado": "listo",
                    "antiguo": "listo", "con reparos": "listo", "fallido": "no-salio",
                    "incompleto": "no-salio"}


def tipo_de(carpeta: Path) -> tuple[str, str]:
    """(tipo, cómo se dice) de un invento (F7.8 (inventario)). Un ensamble
    cuyas piezas giran con un servo es un robot: lo dice su verificación,
    no un modelo."""
    obra = _leer(carpeta / "obra.json")
    if obra:
        n = sum(1 for x in obra.get("nodos", []) if x.get("tipo", "pieza") == "pieza")
        mueve = any((_leer(v) or {}).get("articulaciones")
                    for v in (carpeta / "nodos").glob("*/verificacion.json"))
        tipo = "robot" if mueve else "ensamble"
        return tipo, f"{'Robot' if mueve else 'Ensamble'} · {n} pieza{'s' if n != 1 else ''}"
    if (carpeta / "mechanism.json").is_file():
        return "mecanismo", "Mecanismo"
    return "pieza", "Pieza"


_MATERIALES: dict[str, tuple] = {}
"""Los materiales ya calculados de cada invento, con la firma de lo que
había en disco cuando se calcularon."""

_DE_QUE_DEPENDEN = ("obra.json", "pieza.json", "parts/*/rasgos.json", "parts/*/*.stl",
                    "nodos/*/lista.json", "nodos/*/parts/*/rasgos.json",
                    "nodos/*/parts/*/*.stl", "fichas/*.yaml")


def _firma(carpeta: Path) -> tuple:
    firma = []
    for patron in _DE_QUE_DEPENDEN:
        for ruta in sorted(carpeta.glob(patron)):
            dato = ruta.stat()
            firma.append((str(ruta), dato.st_mtime_ns, dato.st_size))
    return tuple(firma)


def _materiales(carpeta: Path) -> dict | None:
    """Con memoria. Medido el 2026-11-11 con tres inventos: la portada tardaba
    10 segundos en cada carga, 8 de ellos midiendo otra vez en la malla de
    cada pieza el grosor que atraviesa cada tornillo; y mientras algo se
    diseña se recarga sola cada 15. Se vuelve a calcular solo si cambió algo
    de lo que depende: una pieza, una ficha, el backlog o una marca de
    «impresa»."""
    from orchestrator.materiales import materiales
    try:
        firma = _firma(carpeta)
    except OSError:      # un archivo que desaparece a media lectura
        firma = None
    guardado = _MATERIALES.get(str(carpeta))
    if firma is not None and guardado is not None and guardado[0] == firma:
        return guardado[1]
    try:
        m = materiales(carpeta)
    except Exception:   # un proyecto a medias no tumba la portada
        m = None
    if firma is not None:
        _MATERIALES[str(carpeta)] = (firma, m)
    return m


def _compras(m: dict | None) -> str:
    """«2 × Micro servo SG90»: sin el paréntesis de la ficha, que en la
    tarjeta no cabe."""
    return " · ".join(f"{c['cuantos']} × " + re.sub(r"\s*\(.*\)$", "", c["nombre"])
                      for c in (m or {}).get("comprado", []) if c.get("tipo") != "tornilleria")


def _etapa(estado: str, m: dict | None) -> str:
    etapa = _ETAPA_DE_ESTADO.get(estado, "no-salio")
    impresas = (m or {}).get("impresas") or []
    if etapa == "listo" and impresas and all(p["impresa"] for p in impresas):
        return "impreso"
    return etapa


def _imagen(v: dict) -> str | None:
    if v.get("animacion"):
        return f"/proyectos/{v['id']}/animation.gif"
    if v.get("piezas"):
        return f"/proyectos/{v['id']}/vista.png"
    return None


def diferencias(carpeta: Path) -> list[str]:
    """Lo que no salió como se pidió, en tres frases como mucho. Las del
    revisor si las dio; si no (proyectos de antes), los tres primeros
    requisitos que suspendió, recortados."""
    revision = _leer(Path(carpeta) / "review.json") or {}
    frases = [f for f in revision.get("para_el_usuario") or [] if f.strip()][:3]
    if frases:
        return frases
    return [_recortar(i.get("requirement", ""), 110) for i in revision.get("items", [])
            if i.get("verdict") == "no_cumple"][:3]


def _progreso(v: dict) -> str:
    """En qué va un diseño, sin jerga: «intento 3 · dibujando «mango»»."""
    etapa = v.get("ultima_etapa") or ""
    # «pieza «x»» es la etapa de coste de un mecanismo; «dibuja «x»», la
    # línea del registro de una pieza suelta.
    if m := re.search(r"(?:pieza|dibuja) «([^»]+)»", etapa):
        que = f"dibujando «{_legible(m.group(1))}»"
    elif "laminado" in etapa:
        que = "preparando la impresión"
    elif "ingeniero" in etapa:
        que = "pensando cómo resolverlo"
    elif "admisión" in etapa:
        que = "leyendo tu petición"
    elif "revisión" in etapa:
        que = "comprobando que sea lo que pediste"
    elif "afinado" in etapa:
        que = "afinando medidas"
    elif "diseño" in etapa:
        que = "pensando el mecanismo"
    else:
        que = "arrancando"
    intento = f"intento {v['ronda']} · " if v.get("ronda") else ""
    colgado = " · lleva un rato sin moverse" if v.get("parece_colgado") else ""
    return f"{intento}{que}{colgado}"


# --- La galería ------------------------------------------------------------------


def galeria(grupos: list[dict], workspace: Path, hay_puente: bool, puede_pedir: bool,
            tope_usd: float | None = None, tope_backlog_usd: float | None = None) -> str:
    """El inventario de inventos (F7.8 (inventario)): de cada uno, qué es
    (pieza, mecanismo, ensamble o robot), en qué punto está, qué se compra y
    cuánto costó. Antes era una galería por categorías donde una pieza y un
    pan-tilt de tres piezas se veían igual."""
    tarjetas, por_tipo, por_etapa = [], {}, {}
    # Lo que está trabajando, arriba; luego lo último.
    for g in sorted(grupos, key=lambda g: not g.get("en_marcha")):
        v = next(x for x in g["versiones"] if x["id"] == g["mejor"])
        carpeta = _carpeta(workspace, v)
        estado = "en marcha" if g.get("en_marcha") else v["estado"]
        frase, clase = ESTADOS.get(estado, (estado, "suave"))
        tipo, como = tipo_de(carpeta)
        m = _materiales(carpeta) if tipo != "mecanismo" else None
        etapa = _etapa(estado, m)
        if etapa == "impreso":
            frase = "Impreso"
        archivado = g["seccion"] == "archivo"
        if not archivado:
            por_tipo[tipo] = por_tipo.get(tipo, 0) + 1
            por_etapa[etapa] = por_etapa.get(etapa, 0) + 1
        nombre = nombre_de(workspace, g)
        imagen = _imagen(v)
        foto = (f'<img src="{e(imagen)}" alt="" loading="lazy">' if imagen else
                '<span class="sin-foto">Diseñando…</span>' if estado == "en marcha" else
                '<span class="sin-foto">Sin piezas</span>')
        versiones = len(g["versiones"])
        usd = g.get("usd_total") or 0
        detalle = " · ".join(x for x in (_fecha(g["versiones"][-1]["id"]),
                                         f"{versiones} versiones" if versiones > 1 else "",
                                         f"{usd:.2f} USD" if usd >= 0.005 else "") if x)
        compras = _compras(m)
        tarjetas.append(f"""
      <a class="tarjeta" href="/p/{e(g['id'])}" data-estado="{e(estado)}"
         data-tipo="{tipo}" data-etapa="{etapa}" data-nombre="{e(nombre.lower())}"{' data-archivado="1"' if archivado else ''}>
        <div class="foto">{foto}</div>
        <div class="pie-tarjeta">
          <div class="linea"><span class="tipo {tipo}">{e(como)}</span></div>
          <div class="nombre">{e(nombre)}</div>
          {f'<div class="compras">{e(compras)}</div>' if compras else ''}
          <div class="linea"><span class="pastilla {clase}">{e(frase)}</span><span class="suave">{e(detalle)}</span></div>
        </div>
      </a>""")
    archivados = sum(1 for g in grupos if g["seccion"] == "archivo")
    filtros = [f'<button class="filtro activo" data-filtro="todas">Todos <span>{sum(por_tipo.values())}</span></button>']
    filtros += [f'<button class="filtro" data-filtro="tipo:{t}">{nombre} <span>{por_tipo[t]}</span></button>'
                for t, nombre in TIPOS if por_tipo.get(t)]
    etapas = [f'<button class="filtro" data-filtro="etapa:{t}">{nombre} <span>{por_etapa[t]}</span></button>'
              for t, nombre in ETAPAS if por_etapa.get(t)]
    if etapas:
        filtros += ['<span class="separa" aria-hidden="true"></span>', *etapas]
    if archivados:
        filtros.append(f'<button class="filtro" data-filtro="archivo">Archivo <span>{archivados}</span></button>')
    vacio = ('<p class="vacio">Todavía no hay inventos. Pide el primero con «Nuevo diseño», '
             'o por Telegram a Crafty.</p>') if not grupos else ""
    ocupado = any(g.get("en_marcha") for g in grupos)
    # Lo que tarda y cuesta va siempre: con algo en marcha desaparecía, y es
    # justo cuando la persona decide si esperar o volver luego.
    # El tope, el de `config/models.yaml`: el mismo que se comprueba al gastar.
    # Un backlog tiene su tope aparte, más alto: quien pide tiene que saber
    # cuál le toca.
    coste = "Tarda de 5 a 60 minutos" + (
        f" y cuesta hasta {tope_usd:g} USD una pieza y hasta {tope_backlog_usd:g} USD un backlog."
        if tope_usd and tope_backlog_usd else
        f" y cuesta hasta {tope_usd:g} USD." if tope_usd else ".")
    nota = ("Esta web no tiene con qué lanzar diseños." if not puede_pedir else
            f"{coste} Hay un diseño en marcha: espera a que termine." if ocupado else
            f"{coste} Lo verás aparecer en la galería.")
    return _documento("Intelliprint", f"""
  <header class="barra">
    <a class="marca" href="/">Intelliprint</a>
    <input id="buscar" type="search" placeholder="Buscar" aria-label="Buscar inventos">
    <a class="btn" href="/banco">Banco</a>
    <a class="btn" href="/impresora">Impresora</a>
    <button class="btn pri" id="abrir-nuevo">＋ Nuevo diseño</button>
  </header>
  <dialog id="nuevo">
    <form method="dialog" class="cabeza-dialogo"><h2>Nuevo diseño</h2><button class="cerrar" aria-label="Cerrar">✕</button></form>
    <label class="partir">Qué es <select id="tipo"><option value="pieza" data-ejemplo="{e(EJEMPLOS['pieza'])}">una pieza (soporte, gancho, adaptador…)</option><option value="obra" data-ejemplo="{e(EJEMPLOS['obra'])}">un backlog: un robot o un conjunto, pieza a pieza</option></select></label>
    <label for="peticion" class="partir">Qué quieres</label>
    <textarea id="peticion" rows="9" placeholder="{e(EJEMPLOS['pieza'])}"></textarea>
    <div class="pie-dialogo"><span class="nota" id="nota-pedir">{e(nota)}</span>
      <button class="btn pri" id="disenar" {"" if puede_pedir and not ocupado else "disabled"}>Diseñar</button></div>
  </dialog>
  <nav class="filtros">{"".join(filtros)}</nav>
  <div id="vivo">
    <div class="rejilla">{"".join(tarjetas)}</div>{vacio}
  </div>
  <footer class="estado-puente">{_puente(hay_puente)}</footer>""", GUION_GALERIA)


# --- El concepto por aprobar (F3.20 (concepto)) ----------------------------------------

GRUPOS_DE_ORIGEN = (
    ("usuario", "Lo que pediste", ""),
    ("catalogo", "Buscado en internet",
     "Compruébalo con un calibre: una hoja de datos puede no coincidir con tu unidad."),
    ("estimado", "Lo decide el sistema", "Si alguna no te vale, corrígela abajo."),
)
"""El orden en que se leen las medidas: lo tuyo, lo que se buscó, lo supuesto."""


def _medida(r: dict) -> str:
    """«2 × 8 mm, a 26 mm entre centros»: lo que se va a medir en la pieza."""
    valor, unidad = r.get("valor"), r.get("unidad") or ""
    if valor is None:
        return ""
    texto = f"{valor:g} {unidad}".strip()
    if (r.get("cantidad") or 0) > 1:
        texto = f"{r['cantidad']} × {texto}"
    if r.get("separaciones_mm"):
        texto += ", a " + " × ".join(f"{s:g}" for s in r["separaciones_mm"]) + " mm entre centros"
    if r.get("seccion_mm"):
        texto += ", sección " + " × ".join(f"{s:g}" for s in r["seccion_mm"]) + " mm"
    return texto


def _dominio(url: str) -> str:
    return (urlparse(url).hostname or url).removeprefix("www.")


def _fila(r: dict, datos: list[dict]) -> str:
    texto = r.get("texto") or ""
    fuente = ""
    if r.get("origen") == "catalogo":
        # El texto trae «…: 43 mm (fuente: thepihut.com)»: la cifra ya va en
        # su columna y la fuente en la suya, con el enlace y la cita.
        texto = re.sub(r":\s*[-\d.,]+\s*[^\s(]*\s*\(fuente:[^)]*\)\s*$", "", texto)
        texto = re.sub(r"\s*\(fuente:[^)]*\)\s*$", "", texto)
        dato = next((d for d in datos if d.get("valor") == r.get("valor")
                     and d.get("medida", "\0") in (r.get("texto") or "")), None)
        if dato:
            fuente = (f'<a href="{e(dato["fuente"])}" target="_blank" rel="noopener">'
                      f'{e(_dominio(dato["fuente"]))}</a>')
            texto_cita = f'<q>{e(dato.get("cita", ""))}</q>' if dato.get("cita") else ""
            return (f'<tr><td>{e(texto)}{texto_cita}</td><td class="valor">{e(_medida(r))}</td>'
                    f'<td class="fuente">{fuente}</td></tr>')
    return (f'<tr><td>{e(texto)}</td><td class="valor">{e(_medida(r))}</td>'
            f'<td class="fuente">{fuente}</td></tr>')


def _sin_ficha(id_: str, piezas: dict) -> str:
    """Cómo se nombra lo que no tiene ficha. `obra-<nodo>` es el id interno
    de la ficha de una pieza del backlog: a la persona se le dice qué pieza
    es, con el nombre que le dio el desglose si se sabe (F9.13 (limpieza)).
    Lo demás es de la biblioteca y se llama por su id, que es el que se busca."""
    from orchestrator import obra

    prefijo = obra.id_de_ficha("")
    if not id_.startswith(prefijo):
        return id_
    nodo = id_.removeprefix(prefijo)
    return f"la pieza «{piezas.get(nodo, nodo)}» del backlog"


def _componente(x: dict, fichas=(), piezas: dict | None = None) -> str:
    """Un componente que aloja la pieza (F6.11 (biblioteca)): su tamaño, cómo
    entra, cómo se sujeta y de qué planos salen sus medidas. `fichas`: las de
    las piezas ya terminadas de la obra; sin ellas, el soporte de giro del
    pan-tilt (2026-11-09) decía «obra-base (no hay ficha)» con la base fichada.
    `piezas`: {nodo: nombre} del backlog, para nombrar la que no tenga ficha."""
    from orchestrator.componentes import cargar, envolvente

    from orchestrator.schemas.concepto import AJUSTES

    # Antes iba en una línea: «entra Se introduce a presión… .; se sujeta:
    # A presión…» (proyecto del 608ZZ, 2026-11-06).
    ajuste = AJUSTES.get(x.get("ajuste") or "slide", "")
    como = (f'<br>Cómo entra: {e(x.get("como_entra", ""))}'
            f'<br>Cómo se sujeta: {e(x.get("como_se_sujeta", ""))}'
            f'<br>Ajuste: {e(ajuste)} <small>(la holgura sale del perfil de la impresora)</small>')
    try:
        f = cargar(str(x.get("id")), fichas)
    except (KeyError, ValueError):
        return (f'<tr><td>{e(_sin_ficha(str(x.get("id")), piezas or {}))} (no hay ficha){como}</td>'
                '<td class="valor"></td><td class="fuente"></td></tr>')
    a, b = envolvente(f)
    tamano = " × ".join(f"{round(y - z, 3):g}" for z, y in zip(a, b)) + " mm"
    urls = list(dict.fromkeys(fuente.url for fuente in f.fuentes))
    fuentes = ", ".join(f'<a href="{e(u)}" target="_blank" rel="noopener">{e(_dominio(u))}</a>'
                        for u in urls)
    medido = "medido con calibre" if f.verificado else "sin verificar con calibre"
    if f.origen == "impreso":
        medido = "pieza de este proyecto"
    return (f'<tr><td><b>{e(f.nombre)}</b>{como}</td><td class="valor">{e(tamano)}</td>'
            f'<td class="fuente">{fuentes}<br><small>{medido}</small></td></tr>')


def _concepto(carpeta: Path, aprobado: bool = False) -> str | None:
    """Lo que se aprueba, para que se vea qué se aprueba. Con `aprobado`, lo
    que ya se aprobó: sin pedir el visto bueno ni las preguntas, que se
    contestaron antes.

    Antes se pegaba `concepto.md` entero en una caja ámbar: idea, camino de
    carga, orientación, cálculo, descartes y catorce medidas con URLs de 250
    caracteres, todo con el mismo peso. El usuario (2026-11-05): «totalmente
    ilegible, no se sabe qué está aprobando uno». Y lo que se aprueba es la
    idea MÁS los requisitos de `spec.yaml`, que no salían como tales: ahí iba
    un Ø8 mal sacado de una tienda para unos transductores de Ø16.

    None si el concepto es de antes y no trae su JSON: se enseña el md."""
    datos = (_leer(carpeta / "concepto.json") or {})
    c = datos.get("concepto")
    if not isinstance(c, dict) or not c.get("idea"):
        return None
    try:
        spec = yaml.safe_load((carpeta / "spec.yaml").read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        spec = {}
    investigacion = _leer(carpeta / "investigacion.json") or {}
    encontrados = investigacion.get("datos") or []

    partes = ([] if aprobado else
              ['<p class="lead">Si lo apruebas, se dibuja <b>esta idea</b> con <b>estas '
               'medidas</b>. Una medida mal aquí es una pieza mal: revísalas.</p>'])
    if not aprobado:
        from orchestrator.juez import JUEZ, avisos
        partes += [f'<div class="aviso ambar juez">{e(a)}</div>'
                   for a in avisos(_leer(carpeta / JUEZ))]
    partes.append(f'<h3>La idea</h3><p class="idea">{e(c["idea"])}</p>')
    if c.get("preguntas") and not aprobado:
        partes.append('<div class="preguntas"><b>Antes, contéstame</b><ol>'
                      + "".join(f"<li>{e(p)}</li>" for p in c["preguntas"]) + "</ol></div>")

    componentes = [x for x in c.get("componentes") or [] if isinstance(x, dict)]
    from orchestrator import obra
    fichas = ([obra.carpeta_de_fichas(carpeta.parent.parent)]
              if carpeta.parent.name == obra.NODOS else [])
    piezas = {}
    if fichas and componentes:
        try:
            piezas = {n.id: n.nombre for n in obra.cargar_obra(carpeta.parent.parent).nodos}
        except (OSError, ValueError):
            pass   # sin desglose que leer, la pieza se nombra por su nodo
    if componentes:
        partes.append('<h3>Lo que aloja</h3><p class="nota-grupo">Su forma sale de la '
                      'ficha de la biblioteca; al dibujar se mete en la pieza para ver si '
                      'cabe y si entra. Mide el tuyo: las unidades varían.</p>'
                      '<table class="medidas"><tbody>'
                      + "".join(_componente(x, fichas, piezas) for x in componentes)
                      + "</tbody></table>")

    requisitos = spec.get("requisitos") or []
    for origen, titulo, nota in GRUPOS_DE_ORIGEN:
        filas = [_fila(r, encontrados) for r in requisitos if r.get("origen") == origen]
        sin = (investigacion.get("sin_encontrar") or []) if origen == "catalogo" else []
        if not filas and not sin:
            continue
        partes.append(f"<h3>{e(titulo)}</h3>")
        if nota and filas:
            partes.append(f'<p class="nota-grupo">{e(nota)}</p>')
        if filas:
            partes.append(f'<table class="medidas"><tbody>{"".join(filas)}</tbody></table>')
        if sin:
            partes.append('<p class="nota-grupo">No encontré: '
                          + "; ".join(e(s) for s in sin) + ".</p>")

    razonamiento = []
    if c.get("camino_de_carga"):
        razonamiento.append(f'<h4>Cómo trabaja</h4><p>{e(c["camino_de_carga"])}</p>')
    if c.get("orientacion"):
        razonamiento.append(f'<h4>Cómo se imprime</h4><p>{e(c["orientacion"])}</p>')
    listas = [("Fijaciones", c.get("fijaciones") or []),
              ("Cálculo", [_calculo(x) for x in datos.get("comprobaciones") or []]),
              ("Otras formas, descartadas", c.get("alternativas") or [])]
    for titulo, lista in listas:
        if lista:
            razonamiento.append(f"<h4>{titulo}</h4><ul>"
                                + "".join(f"<li>{e(x)}</li>" for x in lista) + "</ul>")
    if razonamiento:
        partes.append('<details class="razonamiento"><summary>Cómo lo ha pensado: carga, '
                      f'impresión, fijaciones y cálculo</summary>{"".join(razonamiento)}</details>')
    return "".join(partes)


def _duracion(segundos: float) -> str:
    """«25 min», «1 h», «1 h 23 min»: como lo dice una persona."""
    minutos = max(1, round(segundos / 60))
    h, m = divmod(minutos, 60)
    return f"{m} min" if not h else f"{h} h" + (f" {m} min" if m else "")


def _impresion(carpeta: Path) -> str:
    """Lo que cuesta imprimirla, tal como lo calculó el laminado: gramos,
    tiempo, soportes y caja. Antes no salía en ningún sitio y era lo primero
    que hay que saber antes de mandarla a la impresora (2026-11-08). Sin
    laminado no se estima nada (una cifra estimada aquí parecería medida):
    desde el 2026-11-09 el diseño no lamina, porque no se sabe en qué
    impresora se va a imprimir, y se dice dónde se sabe."""
    lamina = _leer(carpeta / "fabrication" / "slicing_report.json")
    caja = (_leer(carpeta / "pieza_report.json") or {}).get("bbox_mm") or []
    if not lamina and len(caja) != 3:
        return ""
    datos = ([f"{lamina['grams']:.0f} g", _duracion(lamina["time_s"]),
              "con soportes" if lamina.get("needs_supports") else "sin soportes"]
             if lamina else [])
    if len(caja) == 3:
        datos.append(" × ".join(f"{round(x):g}" for x in caja) + " mm")
    if not lamina:
        datos.append("gramos y tiempo, al abrirla en PrusaSlicer")
    return ('<ul class="impresion" aria-label="Lo que cuesta imprimirla">'
            + "".join(f"<li>{e(d)}</li>" for d in datos) + "</ul>")


def _legible(nombre: str) -> str:
    """«soporte_de_rodamiento» → «Soporte de rodamiento». El nombre de la
    carpeta es para el sistema; la persona lee castellano."""
    texto = nombre.replace("_", " ").strip()
    return texto[:1].upper() + texto[1:]


def _fallos_legibles(motivo: str) -> list[str]:
    """Qué falla, uno por línea y solo su primera frase: lo que sigue son
    instrucciones para el diseñador («Hazlos con `taladrar`…»). El soporte de
    giro del pan-tilt (2026-11-09) se las enseñaba a la persona en un párrafo."""
    fallos = []
    for linea in motivo.splitlines():
        linea = linea.strip().removeprefix("- ").strip()
        if not linea or linea.casefold().startswith("la pieza entregada no cumple"):
            continue
        fallos.append(re.split(r"(?<=\.)\s+(?=[A-ZÁÉÍÓÚÑ¿`])", linea, maxsplit=1)[0])
    return fallos


def _lleva(carpeta: Path) -> str:
    """Cuánto lleva trabajando, de la hora en que se lanzó (job.json)."""
    inicio = (_leer(carpeta / "job.json") or {}).get("inicio")
    try:
        segundos = (dt.datetime.now() - dt.datetime.fromisoformat(inicio)).total_seconds()
    except (TypeError, ValueError):
        return ""
    return f" · lleva {_duracion(segundos)}" if segundos >= 0 else ""


def _calculo(x: dict) -> str:
    from orchestrator.ingenieria import Comprobacion
    try:
        return Comprobacion(**x).texto()
    except (TypeError, ValueError):
        return str(x.get("que", ""))


def _visto_bueno(vid: str, bloqueo: str, si: str = "Aprobar y diseñar",
                 ejemplo: str = "los transductores miden 16 mm de diámetro") -> str:
    return (f'<form class="visto-bueno" data-aprobar="{vid}">'
            '<label><b>¿Algo mal o que contestar?</b> Escríbelo y pulsa '
            '«Contestar»: propondrá otra vez con tu corrección.'
            f'<textarea name="respuestas" rows="2" placeholder="Por ejemplo: «{e(ejemplo)}»"'
            f'{bloqueo}></textarea></label>'
            f'<div class="pie-cambiar"><button class="btn" data-contestar{bloqueo}>Contestar</button>'
            f'<button class="btn pri" data-si{bloqueo}>{e(si)}</button></div></form>')


def _revision_del_concepto(carpeta: Path, formulario: str) -> str:
    revision = _concepto(carpeta)
    if revision is not None:
        return f'<div class="revision">{revision}{formulario}</div>'
    concepto = carpeta / "concepto.md"
    # Sin su título: la página ya lleva el nombre del proyecto encima.
    texto = (a_html(re.sub(r"\A#[^\n]*\n", "", concepto.read_text(encoding="utf-8", errors="ignore")))
             if concepto.is_file() else "")
    return f'<div class="aviso ambar concepto"><b>Así lo resolvería</b>{texto}{formulario}</div>'


# --- La obra, nodo a nodo (F7.3 (arbol)) -------------------------------------------

ESTADOS_DE_NODO = {
    "lista": ("Lista", "ok"),
    "pendiente": ("Por empezar", "suave"),
    "concepto por aprobar": ("Su concepto espera tu visto bueno", "ambar"),
    "concepto aprobado": ("Concepto aprobado", "suave"),
    "diseñando": ("Diseñando…", "vivo"),
    "corrigiendo": ("Corrigiéndose…", "vivo"),
    "diseñada": ("Diseñada: revísala", "ambar"),
    "con fallos": ("No salió del todo", "mal"),
    "por revalidar": ("Por comprobar contra la pieza que se corrigió", "suave"),
    "por verificar": ("Por mover entero con las piezas reales", "suave"),
    "verificando": ("Moviéndose por todo su recorrido…", "vivo"),
    "verificado": ("Se mueve entero sin chocar", "ok"),
    "con choques": ("Choca al moverse", "mal"),
}


def _arbol(carpeta: Path, vid: str, bloqueo: str, hay_puente: bool) -> tuple[str, str]:
    """(lo de arriba, la sección del árbol). Cada nodo es una tarjeta con su
    estado, lo que hace, su pieza y los botones de lo que le toca. Lo
    bloqueado dice a qué espera: sin eso, una pieza sin botones parecía rota."""
    from orchestrator import obra as O
    ob = O.cargar_obra(carpeta)
    if not O.aprobada(carpeta):
        # HTML propio y no obra.md: el markdown anidado salía como «- compra:
        # sg90» suelto, sin decir de qué pieza era.
        filas = []
        for i in ob.orden():
            n = ob.nodo(i)
            detalles = [(t, x) for t, xs in (
                ("Lleva", n.compra), ("Va sobre", [ob.nodo(d).nombre for d in n.depende_de]),
                ("Da", n.ofrece), ("Necesita", n.necesita)) for x in xs]
            filas.append(f'<li><b>{e(n.nombre)}</b>: {e(n.que_hace)}'
                         + ('<ul class="interfaz">' + "".join(
                             f"<li><b>{t}:</b> {e(x)}</li>" for t, x in detalles) + "</ul>"
                            if detalles else "") + "</li>")
        return (f'<div class="revision"><p class="lead">Así lo partiría: <b>una pieza cada '
                'vez</b>, y cada una contra las que ya estén terminadas. Revisa qué hace cada '
                f'una y sobre cuál va.</p><ol class="desglose">{"".join(filas)}</ol>'
                + _visto_bueno(vid, bloqueo, "Aprobar el desglose",
                               ejemplo="que la base se atornille a la mesa con dos M3")
                + "</div>"), ""

    estados = O.estados(carpeta)
    siguiente = O.siguiente(carpeta)
    boton = ""
    if siguiente and estados[siguiente] in O.SE_LANZAN:
        # Sin esto, si la orden moría a medias la página decía «Siguiente:
        # Conjunto pan-tilt» y no había por dónde seguir (2026-11-09).
        que = ("Moverlo entero" if ob.nodo(siguiente).tipo == "conjunto" else
               "Comprobarla" if estados[siguiente] == "por revalidar" else "Empezar")
        boton = f' <button class="btn pri" data-seguir="{vid}"{bloqueo}>{que}</button>'
    arriba = (f'<div class="aviso ambar"><b>Siguiente: {e(ob.nodo(siguiente).nombre)}</b>{boton}</div>'
              if siguiente else '<div class="aviso"><b>Todas las piezas están listas.</b></div>')
    tarjetas = []
    for i in ob.orden():
        n, estado = ob.nodo(i), estados[i]
        dir_nodo = carpeta / O.NODOS / i
        if estado == "bloqueado":
            espera = [ob.nodo(d).nombre for d in n.depende_de if estados[d] not in O.HECHOS]
            frase, clase = f"Espera a {', '.join(espera)}", "suave"
        else:
            frase, clase = ESTADOS_DE_NODO.get(estado, (estado, "suave"))
        partes = [f'<div class="nombre-pieza">{e(n.nombre)} '
                  f'<span class="estado-nodo {clase}">{e(frase)}</span></div>',
                  f'<p class="que-hace">{e(n.que_hace)}</p>']
        detalles = [(t, x) for t, xs in (("Lleva", n.compra), ("Da", n.ofrece),
                                          ("Necesita", n.necesita)) for x in xs]
        if detalles:
            partes.append('<ul class="interfaz">' + "".join(
                f"<li><b>{t}:</b> {e(x)}</li>" for t, x in detalles) + "</ul>")
        # Qué se pidió corregir: mientras se corrige, y después, porque es lo
        # que hay que mirar al revisarla (pan-tilt, 2026-11-09).
        retoque = _leer(dir_nodo / "retoque.json")
        if retoque and retoque.get("cambio"):
            rotulo = "Se corrige" if estado == "corrigiendo" else "Corregida"
            # La primera frase, y el resto desplegable: la de la plataforma
            # del pan-tilt eran doce líneas y la tarjeta era un muro de texto.
            primera, resto = _primera_frase(retoque["cambio"])
            mas = f"<details><summary>Ver todo</summary>{e(resto)}</details>" if resto else ""
            partes.append(f'<p class="corregida"><b>{rotulo}:</b> {e(primera)}</p>{mas}')
        for stl in piezas_de(dir_nodo):
            partes.insert(0, f'<div class="foto-pieza"><img src="/proyectos/{vid}/piezas/'
                             f'{e(stl.stem)}.png" alt="{e(n.nombre)}" loading="lazy"></div>')
        if n.tipo == "conjunto" and estado in ("verificado", "con choques"):
            # F7.6 (animacion): moviéndose, con lo que choca en rojo.
            if (dir_nodo / "animation.gif").is_file():
                partes.insert(0, f'<div class="foto-pieza"><img src="/proyectos/{vid}/nodos/'
                                 f'{e(i)}/animation.gif" alt="{e(n.nombre)} moviéndose" '
                                 'loading="lazy"></div>')
            verificacion = _leer(dir_nodo / "verificacion.json") or {}
            partes.append(_movimiento(ob, verificacion))
            if estado == "con choques":
                partes.append(_corregir_choques(ob, vid, verificacion, bloqueo))
        if estado == "concepto por aprobar":
            partes.append(_revision_del_concepto(dir_nodo, _visto_bueno(vid, bloqueo)))
        if estado == "con fallos":
            motivo = (_leer(dir_nodo / "pieza_report.json") or {}).get("motivo", "")
            fallos = "".join(f"<li>{e(f)}</li>" for f in _fallos_legibles(motivo))
            partes.append(f'<div class="aviso mal"><b>Qué falla</b><ul>{fallos}</ul></div>')
        if estado in ("diseñada", "con fallos"):
            partes.append(_impresion(dir_nodo))
            sin_puente = "" if hay_puente else " disabled"
            partes.append(
                f'<div class="acciones"><button class="btn pri" data-lista="{e(i)}" '
                f'data-proyecto-obra="{vid}"{bloqueo}>Está bien, la siguiente</button>'
                f'<button class="btn" data-abrir="{vid}" data-nodo="{e(i)}"{sin_puente}>'
                'Abrir en PrusaSlicer</button></div>')
        marca = O.lista(carpeta, i)
        # Lo que no es lo que toca ahora va plegado bajo «Más»: «Impresa y
        # probada» y «Corregir» en cada tarjeta hacían un muro de botones.
        extra = []
        if marca:
            if marca.get("impresa"):
                nota = f": {e(marca['nota'])}" if marca.get("nota") else ""
                partes.append(f'<p class="impresa">✓ Impresa y probada{nota}</p>')
            else:
                extra.append(
                    f'<form class="cambiar-pieza" data-impresa="{e(i)}" data-proyecto-obra="{vid}">'
                    f'<input name="nota" placeholder="Cómo entró (opcional)" '
                    f'aria-label="Nota de la prueba de {e(n.nombre)}">'
                    '<button class="btn">Impresa y probada</button></form>')
        if marca or estado in ("diseñada", "con fallos"):
            # El aviso antes de pulsar. Lo construido contra esta pieza ya no
            # se deshace con ella (F9.9 (revalidar)): se comprueba contra la
            # corregida y solo se toca si deja de valer. Lo que no llegó a
            # construirse (un concepto, el conjunto movido) sí se rehace.
            encima = [d for d in ob.dependientes(i) if (carpeta / O.NODOS / d).exists()]
            se_comprueba = [ob.nodo(d).nombre for d in encima
                            if ob.nodo(d).tipo == "pieza"
                            and list((carpeta / O.NODOS / d / "parts").glob("*/envolvente.json"))]
            arrastra = [ob.nodo(d).nombre for d in encima
                        if ob.nodo(d).nombre not in se_comprueba]
            aviso = "".join(f" ({que} también {', '.join(cuales)})" for que, cuales in (
                ("se comprueba", se_comprueba), ("se rehace", arrastra)) if cuales)
            extra.append(
                f'<form class="cambiar-pieza" data-rehacer="{e(i)}" data-proyecto-obra="{vid}">'
                # Un textarea: el cambio de la brida del pan-tilt eran tres
                # frases, y en una línea no se leía lo que se escribía.
                f'<textarea name="cambio" rows="3" placeholder="Qué cambiar de esta pieza; '
                f'se corrige la que hay, no se rediseña" '
                f'aria-label="Qué cambiar de {e(n.nombre)}{e(aviso)}"{bloqueo}></textarea>'
                f'<button class="btn"{bloqueo}>Corregir</button></form>'
                + (f'<p class="nota-grupo">Después se comprueba también '
                   f'{e(", ".join(se_comprueba))}, que se diseñó contra esta: si sigue '
                   'valiendo no se toca.</p>' if se_comprueba else "")
                + (f'<p class="nota-grupo">Cambiarla deshace también {e(", ".join(arrastra))}: '
                   'se diseñó contra esta.</p>' if arrastra else ""))
        if extra and i != siguiente and estado not in ("diseñada", "con fallos"):
            partes.append('<details class="mas"><summary>Más</summary>' + "".join(extra)
                          + "</details>")
        else:
            partes.extend(extra)
        actual = ' aria-current="step"' if i == siguiente else ""
        tarjetas.append(f'<div class="pieza nodo"{actual}>{"".join(partes)}</div>')
    return arriba, (f'<section><h2>Las piezas, una a una</h2>'
                    f'<div class="piezas arbol">{"".join(tarjetas)}</div></section>')


def _primera_frase(texto: str) -> tuple[str, str]:
    m = re.match(r"(.+?[.!?])\s+(\S.*)", texto.strip(), re.S)
    return (m.group(1), m.group(2)) if m else (texto.strip(), "")


def _corregir_choques(ob, vid: str, v: dict, bloqueo: str) -> str:
    """Un formulario por pieza que causa un choque, con su corrección ya
    escrita (F7.7 (culpable)). La persona la lee, la cambia si quiere y la
    manda: la web no corrige nada sola."""
    formularios = []
    for nodo, texto in (v.get("correcciones") or {}).items():
        try:
            nombre = ob.nodo(nodo).nombre
        except KeyError:
            continue
        formularios.append(
            f'<form class="cambiar-pieza" data-rehacer="{e(nodo)}" data-proyecto-obra="{vid}">'
            f'<textarea name="cambio" rows="5" aria-label="Qué cambiar de {e(nombre)}"{bloqueo}>'
            f'{e(texto)}</textarea>'
            f'<button class="btn pri"{bloqueo}>Corregir «{e(nombre)}» con esto</button></form>')
    return "".join(formularios)


def _movimiento(ob, v: dict) -> str:
    """Qué gira con qué y, si choca, con qué y en qué ángulos: es lo que hay
    que saber para corregir la pieza que choca (F7.4 (conjunto))."""
    def nombre(i):
        try:
            return ob.nodo(i).nombre
        except KeyError:
            return i
    giros = [f"{nombre(a['pieza'])} gira con el {a['de']} de {nombre(a['padre'])}, "
             f"de {a['recorrido'][0]:g}° a {a['recorrido'][1]:g}°"
             for a in v.get("articulaciones") or []]
    partes = []
    if giros:
        partes.append('<ul class="interfaz">' + "".join(f"<li>{e(g)}</li>" for g in giros)
                      + "</ul>")
    if v.get("resumen"):
        partes.append('<div class="aviso mal"><b>Qué choca</b><ul>'
                      + "".join(f"<li>{e(r)}</li>" for r in v["resumen"]) + "</ul></div>")
    return "".join(partes)


# --- La página de un proyecto -------------------------------------------------------


def proyecto(g: dict, elegida: str | None, workspace: Path, hay_puente: bool,
             puede_pedir: bool, ocupado: bool, del_banco: str = "") -> str:
    """`del_banco`: la corrida del banco de la que es; entonces se mira sin
    tocarlo (ver `banco`)."""
    versiones = g["versiones"]
    v = next((x for x in versiones if x["id"] == elegida), None) or \
        next(x for x in versiones if x["id"] == g["mejor"])
    carpeta = _carpeta(workspace, v)
    nombre = nombre_de(workspace, g)
    frase, clase = ESTADOS.get(v["estado"], (v["estado"], "suave"))
    raiz = e(g["id"])
    vid = e(v["id"])

    # Lo grande: la animación o las piezas.
    imagen = _imagen(v)
    foto = (f'<img src="{e(imagen)}" alt="{e(nombre)}">' if imagen else
            '<span class="sin-foto">Todavía no hay imagen</span>')

    # Las versiones, en una tira.
    tira = []
    for x in versiones:
        img = _imagen(x)
        mini = f'<img src="{e(img)}" alt="" loading="lazy">' if img else "<i></i>"
        _, c = ESTADOS.get("en marcha" if x["id"] == g.get("en_marcha") else x["estado"], ("", "suave"))
        actual = ' aria-current="true"' if x["id"] == v["id"] else ""
        titulo = x.get("modificacion") or "primera versión"
        tira.append(f'<a class="version"{actual} href="/p/{raiz}?v={e(x["id"])}" title="{e(titulo)}">'
                    f'{mini}<span><b class="punto {c}"></b>v{x["version"]}</span></a>')

    # Una pieza suelta se cambia desde aquí (hasta el 2026-11-08 a un soporte
    # no había por dónde pedirle un cambio). Un backlog no: se cambia pieza a
    # pieza en su árbol. Y los mecanismos que ya hay se ven, pero su flujo se
    # quitó (F9.13 (limpieza)) y no hay con qué rehacerlos.
    # Por aprobar ya tiene su formulario, «Contestar»: dos sitios donde
    # escribir una corrección y no se sabría cuál vale.
    se_puede_modificar = (carpeta / "pieza.json").is_file() and v["estado"] != "por aprobar"

    # Qué es, en una frase, y lo que no salió como se pidió.
    explicacion = ""
    es_obra = (carpeta / "obra.json").is_file()
    bloqueo = "" if puede_pedir and not ocupado else " disabled"
    arbol = ""
    if es_obra:
        # F7.3 (arbol): lo que espera a la persona está en el árbol, nodo a
        # nodo; arriba, el desglose mientras no se apruebe, o lo que toca.
        explicacion, arbol = _arbol(carpeta, vid, bloqueo, hay_puente)
    elif v["estado"] == "con reparos":
        lista = "".join(f"<li>{e(d)}</li>" for d in diferencias(carpeta))
        explicacion = f'<div class="aviso ambar"><b>Lo que no salió como pediste</b><ul>{lista}</ul></div>'
    elif v["estado"] == "fallido":
        motivo = v.get("fallo") or v.get("motivo") or ""
        salida = ("Puedes pedir un cambio abajo, o ver los detalles técnicos."
                  if se_puede_modificar else "Lo que pasó está en los detalles técnicos.")
        explicacion = (f'<div class="aviso mal"><b>Por qué no salió</b><p>{e(_recortar(motivo, 220))}</p>'
                       f'<p class="suave">{salida}</p></div>')
    elif v["estado"] == "por aprobar":
        # F3.20 (concepto): lo primero que hay que ver es la idea, y con qué
        # aprobarla o contestar a sus preguntas. Sin botones, el proyecto se
        # quedaba parado sin que la página dijera por qué.
        explicacion = _revision_del_concepto(carpeta, _visto_bueno(vid, bloqueo))
    elif v["estado"] == "incompleto":
        explicacion = '<div class="aviso"><p>Este diseño se detuvo antes de terminar.</p></div>'

    vivo = ""
    if g.get("en_marcha"):
        corriendo = next(x for x in versiones if x["id"] == g["en_marcha"])
        # F9.12 (pantalla): pararlo desde aquí. Un diseño tarda hasta una hora
        # y cuesta dinero, y solo se podía cancelar pidiéndoselo a Crafty.
        # Botón secundario: no es lo que se viene a hacer. Sin lanzador (o en
        # lo del banco) no sale: solo podría fallar.
        cancelar = (f'<p><button class="btn" data-cancelar="{e(corriendo["id"])}">Cancelar</button></p>'
                    if puede_pedir else "")
        vivo = (f'<div class="aviso vivo" id="en-marcha" data-version="{e(corriendo["id"])}">'
                f'<b>Diseñando la versión {corriendo["version"]}</b>'
                f'<p>{e(_progreso(corriendo) + _lleva(_carpeta(workspace, corriendo)))}. '
                f'Esta página se actualiza sola.</p>{cancelar}</div>')

    # Lo que se aprobó, a la vista después de aprobarlo: es contra lo que se
    # juzga la pieza, y antes desaparecía al darle el visto bueno.
    aprobado = ""
    if v["estado"] != "por aprobar" and (carpeta / "concepto_aprobado").exists():
        lo_aprobado = _concepto(carpeta, aprobado=True)
        if lo_aprobado:
            aprobado = (f'<details class="aprobado"><summary>Lo que aprobaste: la idea y '
                        f'las medidas</summary><div class="revision">{lo_aprobado}</div></details>')

    # Las acciones. «Abrir», no «Imprimir»: el botón abre las piezas en el
    # PrusaSlicer del PC, y desde el móvil «Imprimir» prometía otra cosa.
    sin_piezas = not v.get("piezas")
    imprimir_titulo = ("Este diseño no tiene piezas" if sin_piezas else
                       "Arranca el puente en el PC para abrir PrusaSlicer" if not hay_puente else
                       "Abre las piezas en el PrusaSlicer de tu PC, con el perfil de la impresora")
    acciones = (f'<button class="btn pri" data-abrir="{vid}" title="{e(imprimir_titulo)}"'
                f'{" disabled" if sin_piezas or not hay_puente else ""}>Abrir en PrusaSlicer</button>'
                f'<a class="btn" href="/proyectos/{vid}.zip" download>Descargar</a>')
    # Un concepto por aprobar no tiene nada que imprimir ni que bajar, y una
    # caja vacía de «Todavía no hay imagen» se comía media pantalla.
    # En una obra, igual mientras no haya ninguna pieza hecha (también
    # mientras se corrige la única que había): cada pieza enseña la suya en
    # su tarjeta.
    revisando = (v["estado"] == "por aprobar" or es_obra) and sin_piezas
    # Lo que se está diseñando tampoco: «Descargar» bajaba un zip a medias de
    # 7 KB con la petición y el concepto (2026-11-08).
    if revisando or v["id"] == g.get("en_marcha"):
        acciones = ""
    nav_tira = f'<nav class="tira" aria-label="Versiones">{"".join(tira)}</nav>'
    vacia = "" if imagen else " vacia"
    # F7.9 (visor): el ensamble final en 3D, el del último conjunto de la
    # obra. El GIF se queda dentro hasta que el visor carga: sin WebGL, o en
    # un proyecto de antes del visor, es lo que se ve.
    con_visor = _conjunto_con_ensamble(carpeta) if es_obra else None
    mandos = ""
    if con_visor:
        foto = f'<div class="visor3d" data-visor="/proyectos/{vid}/nodos/{e(con_visor)}">{foto}</div>'
        vacia, mandos = "", '<div class="mandos" hidden></div>'
    visor = (f'<div class="visor"><div class="foto grande{vacia}">{foto}</div>{mandos}{nav_tira}</div>'
             if imagen or con_visor or not revisando else
             (f'<div class="visor">{nav_tira}</div>' if len(versiones) > 1 else ""))

    se_puede_cambiar = puede_pedir and not ocupado
    motivo_no = ("" if se_puede_cambiar else
                 "Hay un diseño en marcha: espera a que termine." if ocupado else
                 "Esta web no puede lanzar diseños.")
    desactivado = "" if se_puede_cambiar else " disabled"

    # Las piezas, cada una con su miniatura. El uso solo lo declaraban los
    # mecanismos, y los que hay lo siguen enseñando.
    usos = {p.get("name"): p.get("uso") or "general"
            for p in (_leer(carpeta / "mechanism.json") or {}).get("parts", [])}
    piezas = []
    for stl in piezas_de(carpeta):
        n = stl.stem
        uso = usos.get(n, "general")
        etiqueta = f'<span class="uso">{e(uso)}</span>' if uso != "general" else ""
        piezas.append(f"""<div class="pieza"><div class="foto-pieza">
            <img src="/proyectos/{vid}/piezas/{e(n)}.png" alt="{e(_legible(n))}" loading="lazy"></div>
          <div class="nombre-pieza">{e(_legible(n))} {etiqueta}</div></div>""")
    # Las de una obra ya salen en su nodo, con sus botones.
    seccion_piezas = (f'<section><h2>Piezas</h2><div class="piezas">{"".join(piezas)}</div></section>'
                      if piezas and not es_obra else "")

    cambiar_todo = (f"""<section class="cambiar"><h2>Cambiar algo</h2>
      <form class="cambiar-todo" data-modificar="{raiz}" data-base="{vid}">
        <textarea name="cambio" rows="2" placeholder="Por ejemplo: que la base mida 60 mm de largo"{desactivado}></textarea>
        <div class="pie-cambiar"><span class="nota">{e(motivo_no or "Crea una versión nueva a partir de esta.")}</span>
        <button class="btn pri"{desactivado}>Pedir cambio</button></div></form></section>""" if se_puede_modificar else "")

    # Las instrucciones de una pieza suelta (la de calibración), a la vista:
    # son lo que hay que leer para usarla.
    docs = "".join(f'<section><h2>{e(d["titulo"])}</h2><div class="documento">{d["html"]}</div></section>'
                   for d in documentos_de(carpeta) if d["archivo"] == "calibracion.md")

    tipo, como = tipo_de(carpeta)
    materiales = _lista_de_materiales(_materiales(carpeta)) if tipo != "mecanismo" else ""
    estudio = _estudio_de_movimientos(carpeta, vid, con_visor)
    categoria = categoria_de(workspace, g)
    opciones = "".join(f'<option value="{e(c)}"{" selected" if c == categoria else ""}>{e(c.capitalize())}</option>'
                       for c in CATEGORIAS)
    cuerpo = f"""
  <header class="barra"><a class="volver" href="{"/banco" if del_banco else "/"}">← {"Banco" if del_banco else "Inventos"}</a><span class="estado-puente">{_puente(hay_puente)}</span></header>{_aviso_del_banco(del_banco)}
  <main class="proyecto" data-proyecto="{raiz}" data-version="{vid}">
    <div class="cabeza{" sin-visor" if revisando and not imagen else ""}">
      {visor}
      <div class="ficha">
        <div class="linea"><span class="tipo {tipo}">{e(como)}</span>
        <select class="categoria" data-categoria="{raiz}" aria-label="Categoría">{opciones}</select></div>
        <h1>{e(nombre)}</h1>
        <div class="estado-grande {clase}">{e(frase)}</div>
        {vivo}{explicacion}
        {_impresion(carpeta)}
        {f'<div class="acciones">{acciones}</div>' if acciones else ""}
        {aprobado}
        <p class="suave meta">Versión {v["version"]} de {len(versiones)} · {e(_fecha(v["id"]))}</p>
      </div>
    </div>
    {materiales}{estudio}{arbol}{seccion_piezas}{cambiar_todo}{docs}
    <details class="tecnico" data-version="{vid}"><summary>Detalles técnicos</summary><div class="contenido"></div></details>
  </main>"""
    if con_visor:
        cuerpo += ('\n<script type="importmap">{"imports": {"three": "/estatico/three.module.min.js"}}'
                   f'</script>\n<script type="module">{GUION_VISOR}</script>')
    return _documento(f"{nombre} · Intelliprint", cuerpo, GUION_PROYECTO)


def _conjunto_con_ensamble(carpeta: Path) -> str | None:
    """El último conjunto de la obra (el ensamble final) que ya dejó sus
    mallas para el visor."""
    obra = _leer(carpeta / "obra.json") or {}
    conjuntos = [x["id"] for x in obra.get("nodos", []) if x.get("tipo") == "conjunto"]
    from orchestrator import obra as O
    try:
        orden = O.cargar_obra(carpeta).orden()
    except Exception:
        orden = conjuntos
    for i in reversed([i for i in orden if i in conjuntos]):
        if (carpeta / "nodos" / i / "ensamble.json").is_file():
            return i
    return None


def _kgf_cm(nm: float) -> str:
    """El par como lo dan las hojas de servos. Con dos cifras significativas:
    el tilt del pan-tilt pide 0.0046 kgf·cm y con dos decimales salía «0.00»."""
    v = nm * 100 / 9.80665
    return "0" if v < 5e-5 else f"{v:.2g}" if v < 1 else f"{v:.3g}"


def _gramos(g) -> str:
    if g is None:
        return "—"
    return f"{g / 1000:.2f} kg" if g >= 1000 else f"{g:.0f} g"


def _estudio_de_movimientos(carpeta: Path, vid: str, conjunto: str | None) -> str:
    """Las cinco preguntas de F7.10 (estudio), una tarjeta cada una, con la
    cifra, si va holgada (verde), justa (ámbar) o no llega (rojo), y de
    dónde sale. Del `estudio.json`: calcularlo al vuelo cuesta medio minuto."""
    from orchestrator.estudio import MARGEN_SERVO
    if not conjunto:
        return ""
    est = _leer(carpeta / "nodos" / conjunto / "estudio.json")
    if not est:
        return ""
    tarjetas = []
    c = est["carga_max"]
    material = "".join(
        f'<li>Material de «{e(m["nombre"])}»: '
        + (f'{_gramos(m["carga_max_g"])} <span class="suave">({e(m["detalle"])})</span>'
           if m["carga_max_g"] is not None else f'<span class="suave">{e(m["detalle"])}</span>')
        + '</li>' for m in est.get("material") or [])
    sin_material = "" if "material" in est else '<p class="suave">Sin medir la resistencia del material.</p>'
    tarjetas.append(f"""<div class="tarjeta-estudio"><h3>Carga máxima</h3>
      <p class="cifra">{_gramos(c["g"])}</p>
      <p>{f'la limita el {e(c["limita"])}' if c["g"] is not None else "no se puede decir"},
      puesta {e(est["carga"]["donde"])}.</p>{f'<ul>{material}</ul>' if material else ''}{sin_material}</div>""")

    filas = []
    for s in est["servos"]:
        if s.get("aguanta") is None:
            filas.append(f'<li><span class="pastilla ambar">sin datos</span> {e(s["nombre"])}: '
                         f'no se sabe el par de {e(s["servo"])}</li>')
            continue
        clase = "mal" if not s["aguanta"] else ("ambar" if s["margen"] < 0.3 else "ok")
        filas.append(f'<li><span class="pastilla {clase}">{"aguanta" if s["aguanta"] else "no aguanta"}</span> '
                     f'{e(s["nombre"])} · {e(s["servo"])}: pide {_kgf_cm(s["par_max_Nm"])} kgf·cm '
                     f'(a {s["angulo_peor"]:g}°) de {_kgf_cm(s["par_disponible_Nm"])} '
                     f'<span class="suave">(el {MARGEN_SERVO:.0%} de su par a {s["tension_V"]:g} V)</span></li>')
    tarjetas.append(f'<div class="tarjeta-estudio"><h3>¿Aguanta el servo?</h3><ul>{"".join(filas)}</ul></div>')

    v = est["vuelco"]
    if v["margen_mm"] is None:
        vuelca = '<p class="suave">No se sabe: la base no tiene cara de apoyo.</p>'
    else:
        clase = "ok" if v["atornillada"] or v["margen_mm"] >= 5 else ("ambar" if v["margen_mm"] >= 0 else "mal")
        vuelca = (f'<p><span class="pastilla {clase}">{"atornillada" if v["atornillada"] else ("no vuelca" if v["margen_mm"] >= 0 else "vuelca")}</span> '
                  f'sin carga, el centro de masas queda a {v["margen_mm"]:.1f} mm del borde del apoyo en la peor pose.</p>')
        if v["carga_max_g"] is not None:
            vuelca += (f'<p>Con {_gramos(v["carga_max_g"])} en el punto de carga volcaría'
                       + (", pero va atornillada." if v["atornillada"] else ".") + '</p>')
    tarjetas.append(f'<div class="tarjeta-estudio"><h3>¿Vuelca?</h3>{vuelca}</div>')

    a = est["alcance"]
    # Los estudios de antes del 2026-11-12 no traen el hombro.
    h = a.get("hombro")
    del_hombro = (f'<p>Del eje de «{e(h["nombre"])}», el primer giro que lo levanta, está a '
                  f'<b>{a["del_hombro_mm"]:.0f} mm</b>: eso es lo que mide el brazo.</p>'
                  if h and h["levanta"] else "")
    tarjetas.append(f"""<div class="tarjeta-estudio"><h3>Alcance</h3>
      <p>El punto de carga llega a <b>{a["radio_mm"]:.0f} mm</b> del primer eje.</p>{del_hombro}
      <img class="alcance" src="/proyectos/{vid}/nodos/{e(conjunto)}/alcance.png" alt="Planta y alzado del recorrido del punto de carga" loading="lazy"></div>""")

    tiempos = "".join(
        f'<li>«{e(s["nombre"])}»: {s["recorrido"][1] - s["recorrido"][0]:g}° en {s["tiempo_s"]:.2f} s; '
        f'el punto de carga va a {s["velocidad_punta_mm_s"]:.0f} mm/s</li>'
        for s in est["servos"] if s.get("tiempo_s") is not None)
    tarjetas.append(f"""<div class="tarjeta-estudio"><h3>Velocidades y tiempos</h3>
      <ul>{tiempos or '<li class="suave">Sin datos de velocidad.</li>'}</ul>
      <p class="suave">Con la recta par-velocidad del servo, en el peor par.</p></div>""")

    avisos = "".join(f"<li>{e(x)}</li>" for x in est.get("avisos") or [])
    return f"""<section class="estudio"><h2>Estudio de movimientos</h2>
      <p class="suave">La base apoyada como se imprimió; {est["poses"]} poses cada {est["paso"]:g}°;
      {est["masa_total_g"]:.0f} g en total.</p>
      <div class="tarjetas-estudio">{"".join(tarjetas)}</div>
      {f'<ul class="avisos-estudio suave">{avisos}</ul>' if avisos else ''}</section>"""


def _lista_de_materiales(m: dict | None) -> str:
    """Lo que lleva un ensamble (F7.8 (inventario)): lo que se imprime, todo
    lo que se compra —componentes, tornillos, tuercas— y lo que viene en la
    bolsa de un componente. Una pieza que no compra nada no la lleva: sería
    repetir su propia foto."""
    if not m or not (m["comprado"] or m["incluido"] or len(m["impresas"]) > 1):
        return ""
    impresas = "".join(f'<li>{"✓ " if p["impresa"] else ""}{e(p["nombre"])}</li>'
                       for p in m["impresas"])
    compradas = "".join(f'<li><b>{c["cuantos"]} ×</b> {e(c["nombre"])}</li>' for c in m["comprado"])
    sin_parentesis = re.compile(r"\s*\(.*\)$")
    incluido = "".join(f'<li><b>{c["cuantos"]} ×</b> {e(c["nombre"])} <span class="suave">'
                       f'(con el {e(sin_parentesis.sub("", c["viene_con"]))})</span></li>'
                       for c in m["incluido"])
    return f"""<section class="materiales"><h2>Lo que lleva</h2><div class="columnas">
      <div><h3>Se imprime</h3><ul>{impresas}</ul></div>
      {f'<div><h3>Se compra</h3><ul>{compradas}</ul></div>' if compradas else ''}
      {f'<div><h3>Viene con lo comprado</h3><ul>{incluido}</ul></div>' if incluido else ''}
      </div></section>"""


def _aviso_del_banco(corrida: str) -> str:
    if not corrida:
        return ""
    return (f'<p class="del-banco">Del banco, corrida {e(corrida)}: es una medida del sistema, '
            'no un proyecto tuyo. Se mira y se baja, pero no se toca.</p>')


# --- El banco (F7.6 (animacion)) ---------------------------------------------------


def _clase_de_nota(nota: str) -> str:
    m = re.match(r"\s*(\d+)", nota or "")
    if not m:
        return "suave"
    n = int(m.group(1))
    return "ok" if n == 100 else "ambar" if n >= 60 else "mal"


def banco(corridas: list[dict], hay_puente: bool) -> str:
    """Cada corrida del banco con su nota y la de cada encargo, enlazado a su
    proyecto. La ronda de arreglos del 2026-11-10 no se veía en ninguna
    parte de la web: el banco escribe en `workspace/banco/`."""
    def pastilla(nota: str) -> str:
        return (f' <span class="pastilla {_clase_de_nota(nota)}">{e(nota)}</span>'
                if nota else "")

    filas = []
    for c in corridas:
        encargos = "".join(
            f'<li><a href="/p/{e(x["proyecto"])}">{e(x["nombre"])}</a>{pastilla(x["nota"])}</li>'
            if x["proyecto"] else
            f'<li>{e(x["nombre"])}{pastilla(x["nota"])}</li>'
            for x in c["encargos"])
        # Lo que se ve de una corrida que corre: que corre, y que la nota que
        # hay (si hay alguna) no es la de esta vuelta.
        vivo = ' <span class="pastilla vivo">En marcha</span>' if c.get("en_marcha") else ""
        if c["informe"] is None:
            pie = ("Diseñando: la nota sale al terminar. Abre el encargo para ver por "
                   "dónde va." if c.get("en_marcha") else
                   "Sin informe: la corrida se paró antes de dar su nota.")
        elif c.get("en_marcha"):
            pie = f'{c["informe"]} · reanudándose: la nota es la de la vuelta anterior.'
        else:
            pie = c["informe"]
        filas.append(f'<section class="corrida"><h2>{e(c["id"])}{pastilla(c["nota"])}{vivo}</h2>'
                     f'<p class="suave">{e(pie)}</p>'
                     f'<ul class="encargos">{encargos}</ul></section>')
    vacio = "" if corridas else '<p class="vacio">Todavía no hay ninguna corrida del banco.</p>'
    # Con algo en marcha la página se pone al día sola: no tiene nada que se
    # pueda estar escribiendo, así que recargarla entera no pisa nada.
    cabeza = ('<meta http-equiv="refresh" content="20">'
              if any(c.get("en_marcha") for c in corridas) else "")
    return _documento("Banco · Intelliprint", f"""
  <header class="barra"><a class="volver" href="/">← Inventos</a><span class="estado-puente">{_puente(hay_puente)}</span></header>
  <main class="banco"><h1>El banco</h1>
    <p class="lead">Lo que mide si el sistema mejora: encargos fijos, juzgados sin el propio
    sistema. Cada encargo abre su proyecto para verlo.</p>
    {"".join(filas)}{vacio}</main>""", "", cabeza=cabeza)


def _puente(hay_puente: bool) -> str:
    return ('<span class="ok">● PrusaSlicer conectado</span>' if hay_puente else
            '<span class="suave" title="Arráncalo en el PC: powershell scripts\\start-host-mcps.ps1">'
            '● PrusaSlicer no conectado</span>')


def _documento(titulo: str, cuerpo: str, guion: str, cabeza: str = "") -> str:
    return ('<!doctype html>\n<html lang="es"><head><meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"{cabeza}<title>{e(titulo)}</title>\n<style>{ESTILO}</style></head>\n"
            f'<body>{cuerpo}\n<div id="aviso" role="status"></div>\n'
            f"<script>{GUION_COMUN}{guion}</script>\n</body></html>")


EJEMPLOS = {
    # Uno por tipo: con «una pieza» elegida se enseñaba un sargento, que no
    # es una pieza suelta, y no se sabía qué tipo había que elegir (2026-11-08).
    "obra": (
        "El proyecto entero; se partirá en piezas y se diseñará una cada vez, "
        "con tu visto bueno en cada paso. Por ejemplo:\n\n"
        "Un pan-tilt con dos servos SG90 para una cámara de 40 g: el de abajo "
        "gira, el de arriba inclina, y la base se atornilla a la mesa con dos M3."
    ),
    "pieza": (
        "Qué quieres que haga, con todo lo que sepas. Por ejemplo:\n\n"
        "Un soporte para un servo SG90 que se atornille a una placa con dos "
        "tornillos M3 separados 30 mm. El eje del servo, a 20 mm de la placa.\n\n"
        "Medidas, qué aloja, cómo se sujeta y qué carga aguanta."
    ),
}


ESTILO = """
  :root { --bg:#f4f4f1; --fg:#1b1b19; --suave:#6e6e68; --linea:#e3e3de; --tarjeta:#fff; --foto:#fff;
          --acento:#2463eb; --acento-fg:#fff; --ok:#1f7a4d; --ok-bg:#e3f4ea; --mal:#b3361c; --mal-bg:#fbe9e4;
          --ambar:#8a5a00; --ambar-bg:#fbf0d6; --vivo:#2463eb; --vivo-bg:#e6eefe; --sombra:0 1px 2px rgba(0,0,0,.05),0 4px 16px rgba(0,0,0,.05);
          --fondo-suave:rgba(127,127,127,.12); }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#121212; --fg:#ececea; --suave:#9b9b95; --linea:#2a2a28; --tarjeta:#1c1c1b; --foto:#fff;
            --acento:#6b9cff; --acento-fg:#0b1530; --ok:#6fd19a; --ok-bg:#16291f; --mal:#ff9b80; --mal-bg:#2e1a14;
            --ambar:#f0c060; --ambar-bg:#2b2412; --vivo:#8fb3ff; --vivo-bg:#18223a; --sombra:none; }
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
  a { color:inherit; }
  .suave { color:var(--suave); } .ok { color:var(--ok); } .mal { color:var(--mal); }
  .btn { display:inline-flex; align-items:center; justify-content:center; gap:6px; font:inherit; font-size:14px; font-weight:500;
         padding:9px 16px; border-radius:10px; border:1px solid var(--linea); background:var(--tarjeta); color:var(--fg);
         text-decoration:none; cursor:pointer; white-space:nowrap; }
  .btn:hover { border-color:var(--suave); }
  .btn.pri { background:var(--acento); color:var(--acento-fg); border-color:transparent; }
  .btn:disabled { opacity:.45; cursor:not-allowed; }
  :focus-visible { outline:2px solid var(--acento); outline-offset:2px; }
  .barra { position:sticky; top:0; z-index:5; display:flex; align-items:center; gap:12px; padding:12px max(16px, calc((100% - 1200px)/2));
           background:color-mix(in srgb, var(--bg) 88%, transparent); backdrop-filter:blur(8px); border-bottom:1px solid var(--linea); }
  .marca { font-weight:700; font-size:18px; text-decoration:none; letter-spacing:-.01em; margin-right:auto; }
  .volver { text-decoration:none; font-weight:500; margin-right:auto; }
  #buscar { font:inherit; padding:8px 12px; border-radius:10px; border:1px solid var(--linea); background:var(--tarjeta);
            color:var(--fg); width:min(280px, 40vw); }
  .filtros { display:flex; gap:8px; overflow-x:auto; padding:16px max(16px, calc((100% - 1200px)/2)) 4px; scrollbar-width:none; }
  .filtro { font:inherit; font-size:14px; padding:7px 14px; border-radius:999px; border:1px solid var(--linea);
            background:var(--tarjeta); color:var(--fg); cursor:pointer; white-space:nowrap; }
  .filtro span { color:var(--suave); margin-left:4px; }
  .filtro.activo { background:var(--fg); color:var(--bg); border-color:var(--fg); }
  .filtro.activo span { color:inherit; opacity:.7; }
  .separa { flex:0 0 1px; background:var(--linea); margin:4px 4px; }
  /* El tipo de invento (F7.8 (inventario)), antes que el nombre: lo primero
     que se distingue en el inventario es si es una pieza o un robot. */
  .tipo { font-size:12px; font-weight:600; letter-spacing:.02em; text-transform:uppercase; color:var(--suave); }
  .tipo.robot, .tipo.ensamble { color:var(--acento); }
  .compras { font-size:13px; color:var(--suave); }
  /* El visor 3D (F7.9 (visor)): ocupa el sitio de la foto grande. */
  .visor3d { width:100%; height:100%; display:flex; align-items:center; justify-content:center; }
  .visor3d.listo { cursor:grab; touch-action:none; } .visor3d canvas { width:100%; height:100%; display:block; }
  .mandos { display:flex; flex-direction:column; gap:6px; padding:10px 0 0; width:100%; }
  .mandos label { display:grid; grid-template-columns:minmax(0, 1fr) minmax(120px, 2fr) 3.5em; gap:10px; align-items:center; font-size:13px; }
  .mandos label span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .mandos output { font-variant-numeric:tabular-nums; text-align:right; }
  .mandos .btn { align-self:flex-start; }
  .mandos label.atraves { display:flex; gap:8px; }
  .mandos .choca { color:var(--mal); font-weight:600; font-size:13px; margin:0; min-height:1.2em; }
  .materiales .columnas { display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:16px;
                          background:var(--tarjeta); border:1px solid var(--linea); border-radius:16px; padding:16px 18px; }
  .tarjetas-estudio { display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:12px; }
  .tarjeta-estudio { background:var(--tarjeta); border:1px solid var(--linea); border-radius:12px; padding:12px 14px; }
  .tarjeta-estudio h3 { font-size:13px; text-transform:uppercase; letter-spacing:.03em; color:var(--suave); margin:0 0 6px; }
  .tarjeta-estudio .cifra { font-size:26px; font-weight:700; margin:0; }
  .tarjeta-estudio p { margin:4px 0; } .tarjeta-estudio ul { margin:4px 0; padding-left:18px; } .tarjeta-estudio li { margin:4px 0; }
  .tarjeta-estudio img.alcance { width:100%; height:auto; border-radius:8px; background:#fff; margin-top:6px; }
  .avisos-estudio { font-size:13px; margin:10px 0 0; padding-left:18px; }
  .mandos .par { font-size:12px; color:var(--suave); margin:-4px 0 0; min-height:1.1em; } .mandos .par.mal { color:var(--mal); font-weight:600; }
  .materiales h3 { font-size:13px; text-transform:uppercase; letter-spacing:.03em; color:var(--suave); margin:0 0 8px; }
  .materiales ul { margin:0; padding-left:18px; } .materiales li { margin:3px 0; } .materiales p { margin:0 0 4px; }
  #vivo { padding:12px max(16px, calc((100% - 1200px)/2)) 48px; }
  .rejilla { display:grid; grid-template-columns:repeat(auto-fill, minmax(250px, 1fr)); gap:18px; }
  .tarjeta { display:flex; flex-direction:column; background:var(--tarjeta); border-radius:16px; overflow:hidden;
             box-shadow:var(--sombra); border:1px solid var(--linea); text-decoration:none; transition:transform .12s ease; }
  .tarjeta:hover { transform:translateY(-2px); }
  .tarjeta[hidden] { display:none; }
  .foto { aspect-ratio:4/3; background:var(--foto); display:flex; align-items:center; justify-content:center; overflow:hidden; }
  .foto img { width:100%; height:100%; object-fit:contain; }
  /* En la galería el hueco lleva el color de la tarjeta, no `--foto`, que es
     blanco también en el tema oscuro: cada tarjeta era un rectángulo blanco
     hasta que llegaba su imagen. La imagen no se toca. */
  .tarjeta .foto { background:var(--tarjeta); }
  .sin-foto { color:#8a8f94; font-size:14px; }
  .tarjeta[data-estado="en marcha"] .sin-foto { animation:latir 1.6s ease-in-out infinite; }
  @keyframes latir { 50% { opacity:.4; } }
  .pie-tarjeta { padding:12px 14px 14px; display:flex; flex-direction:column; gap:8px; }
  .nombre { font-weight:600; line-height:1.3; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
  .linea { display:flex; gap:8px; align-items:center; flex-wrap:wrap; font-size:13px; }
  .pastilla { font-size:12px; font-weight:600; padding:3px 9px; border-radius:999px; background:var(--linea); }
  .pastilla.ok { background:var(--ok-bg); color:var(--ok); } .pastilla.mal { background:var(--mal-bg); color:var(--mal); }
  .pastilla.ambar { background:var(--ambar-bg); color:var(--ambar); } .pastilla.vivo { background:var(--vivo-bg); color:var(--vivo); }
  .vacio { color:var(--suave); text-align:center; padding:48px 0; }
  .estado-puente { font-size:13px; }
  footer.estado-puente { padding:0 max(16px, calc((100% - 1200px)/2)) 32px; }
  dialog { border:0; border-radius:18px; padding:20px; width:min(640px, calc(100vw - 32px)); background:var(--tarjeta); color:var(--fg);
           box-shadow:0 20px 60px rgba(0,0,0,.25); }
  dialog::backdrop { background:rgba(0,0,0,.35); }
  .cabeza-dialogo { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; }
  .cabeza-dialogo h2 { margin:0; font-size:20px; }
  .cerrar { border:0; background:none; font-size:18px; cursor:pointer; color:var(--suave); }
  textarea, input[name=cambio] { width:100%; font:inherit; font-size:15px; padding:11px 13px; border-radius:12px;
             border:1px solid var(--linea); background:var(--bg); color:var(--fg); resize:vertical; }
  .partir { display:block; font-size:14px; margin-top:10px; color:var(--suave); }
  select { font:inherit; font-size:14px; padding:6px 8px; border-radius:8px; border:1px solid var(--linea); background:var(--tarjeta); color:var(--fg); max-width:100%; }
  .pie-dialogo, .pie-cambiar { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-top:12px; flex-wrap:wrap; }
  .nota { font-size:13px; color:var(--suave); }

  .proyecto { max-width:1200px; margin:0 auto; padding:24px 16px 64px; }
  .banco { max-width:900px; margin:0 auto; padding:24px 16px 64px; }
  .banco h1 { margin:0 0 4px; } .banco > .lead { color:var(--suave); margin:0 0 20px; }
  .corrida { background:var(--tarjeta); border:1px solid var(--linea); border-radius:14px; padding:14px 16px; margin:0 0 12px; box-shadow:var(--sombra); }
  .corrida h2 { font-size:17px; margin:0; display:flex; gap:10px; align-items:baseline; flex-wrap:wrap; }
  .corrida > p { margin:2px 0 8px; font-size:13px; }
  .encargos { list-style:none; margin:0; padding:0; display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:4px 16px; }
  .encargos li { display:flex; justify-content:space-between; gap:8px; padding:3px 0; border-bottom:1px solid var(--linea); }
  .encargos a { text-decoration:none; color:var(--acento); }
  .del-banco { max-width:1200px; margin:12px auto 0; padding:8px 14px; border-radius:10px; background:var(--ambar-bg); color:var(--ambar); }
  .cabeza { display:grid; grid-template-columns:minmax(0,1.25fr) minmax(0,1fr); gap:32px; align-items:start; }
  .foto.grande { border-radius:18px; aspect-ratio:4/3; }
  .tira { display:flex; gap:8px; margin-top:12px; overflow-x:auto; }
  .version { flex:0 0 auto; width:84px; text-decoration:none; font-size:12px; text-align:center; border-radius:10px; padding:4px;
             border:2px solid transparent; }
  .version img, .version i { display:block; width:100%; aspect-ratio:4/3; object-fit:contain; background:var(--foto); border-radius:7px; }
  .version[aria-current] { border-color:var(--acento); }
  .version span { display:inline-flex; align-items:center; gap:4px; margin-top:4px; }
  .punto { width:8px; height:8px; border-radius:50%; background:var(--suave); display:inline-block; }
  .punto.ok { background:var(--ok); } .punto.mal { background:var(--mal); } .punto.ambar { background:var(--ambar); } .punto.vivo { background:var(--vivo); }
  .ficha h1 { font-size:28px; line-height:1.2; margin:10px 0 8px; letter-spacing:-.01em; }
  .categoria { font-size:13px; }
  .estado-grande { display:inline-block; font-weight:600; padding:5px 12px; border-radius:999px; background:var(--linea); }
  .estado-grande.ok { background:var(--ok-bg); color:var(--ok); } .estado-grande.mal { background:var(--mal-bg); color:var(--mal); }
  .estado-grande.ambar { background:var(--ambar-bg); color:var(--ambar); } .estado-grande.suave { color:var(--suave); }
  .aviso { margin-top:16px; padding:12px 14px; border-radius:12px; background:var(--tarjeta); border:1px solid var(--linea); font-size:14px; }
  .aviso p, .aviso ul { margin:6px 0 0; } .aviso ul { padding-left:18px; }
  .aviso.ambar { background:var(--ambar-bg); border-color:transparent; } .aviso.mal { background:var(--mal-bg); border-color:transparent; }
  .aviso.vivo { background:var(--vivo-bg); border-color:transparent; }
  .acciones { display:flex; gap:10px; margin-top:20px; flex-wrap:wrap; }
  .cabeza.sin-visor { grid-template-columns:minmax(0,860px); }
  .revision { margin-top:18px; font-size:15px; line-height:1.5; }
  .revision .lead { background:var(--ambar-bg); padding:10px 14px; border-radius:10px; margin:0; }
  .revision h3 { font-size:12px; text-transform:uppercase; letter-spacing:.07em; color:var(--suave); margin:26px 0 8px; }
  .revision .idea { font-size:17px; margin:0; }
  .preguntas { border:1px solid var(--ambar); border-radius:12px; padding:10px 14px; margin-top:18px; }
  .preguntas ol { margin:6px 0 0; padding-left:20px; }
  .nota-grupo { font-size:13px; color:var(--suave); margin:-2px 0 6px; }
  .medidas { width:100%; border-collapse:collapse; table-layout:fixed; }
  .medidas td { padding:8px 12px 8px 0; border-bottom:1px solid var(--linea); vertical-align:top; }
  .medidas td:last-child { padding-right:0; }
  .medidas .valor { width:190px; font-weight:600; font-variant-numeric:tabular-nums; }
  .medidas .fuente { width:130px; font-size:13px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .medidas .fuente a { color:var(--acento); }
  .medidas q { display:block; font-size:12.5px; color:var(--suave); margin-top:2px; overflow-wrap:anywhere; }
  .razonamiento { margin-top:22px; }
  .razonamiento summary { cursor:pointer; color:var(--acento); font-size:14px; }
  .razonamiento h4 { margin:14px 0 4px; font-size:14px; }
  .razonamiento p, .razonamiento ul { margin:0; font-size:14px; } .razonamiento ul { padding-left:18px; }
  .revision .visto-bueno { margin-top:24px; padding:14px; border-radius:12px; background:var(--tarjeta); border:1px solid var(--linea); }
  .revision .visto-bueno label { display:block; font-size:14px; margin-bottom:8px; }
  @media (max-width:560px) {
    .medidas tr { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,40%); border-bottom:1px solid var(--linea); padding:6px 0; }
    .medidas .valor { text-align:right; }
    .medidas td { border:0; padding:2px 8px 2px 0; width:auto !important; } .medidas .fuente { grid-column:1 / -1; }
  }
  .meta { font-size:13px; margin-top:14px; }
  section { margin-top:40px; }
  section h2 { font-size:18px; margin:0 0 14px; }
  .piezas { display:grid; grid-template-columns:repeat(auto-fill, minmax(200px, 1fr)); gap:14px; }
  .pieza { background:var(--tarjeta); border:1px solid var(--linea); border-radius:14px; overflow:hidden; display:flex; flex-direction:column; }
  .foto-pieza { aspect-ratio:4/3; background:var(--foto); }
  .foto-pieza img { width:100%; height:100%; object-fit:contain; }
  .nombre-pieza { padding:10px 12px 0; font-weight:600; }
  .uso { font-size:11px; font-weight:600; color:var(--suave); border:1px solid var(--linea); border-radius:6px; padding:1px 6px; margin-left:4px; }
  .cambiar-pieza { display:flex; gap:6px; padding:10px 12px 12px; }
  .cambiar-pieza input, .cambiar-pieza textarea { padding:8px 10px; font-size:14px; border-radius:9px; }
  .cambiar-pieza textarea { flex:1; min-width:0; resize:vertical; font:inherit; }
  .cambiar-pieza:has(textarea) { align-items:flex-end; }
  .corregida { font-size:14px; padding:8px 10px; border-radius:9px; background:var(--fondo-suave); }
  .cambiar-pieza .btn { padding:8px 12px; }
  .cambiar { max-width:760px; }
  .documento { background:var(--tarjeta); border:1px solid var(--linea); border-radius:14px; padding:6px 18px 14px; font-size:14px; }
  .documento table { border-collapse:collapse; } .documento td, .documento th { padding:4px 10px; border-bottom:1px solid var(--linea); }
  .documento pre { white-space:pre-wrap; background:var(--bg); padding:8px 10px; border-radius:8px; }
  .tecnico { margin-top:48px; border-top:1px solid var(--linea); padding-top:16px; color:var(--suave); font-size:14px; }
  .tecnico summary { cursor:pointer; }
  .tecnico .contenido { color:var(--fg); }
  .tecnico pre { white-space:pre-wrap; font:12px/1.4 ui-monospace,Consolas,monospace; background:var(--tarjeta); padding:8px 10px; border-radius:8px; }
  .tecnico table { border-collapse:collapse; font-size:13px; } .tecnico td, .tecnico th { padding:4px 8px; border-bottom:1px solid var(--linea); text-align:left; }
  #aviso { position:fixed; left:50%; bottom:20px; transform:translateX(-50%); max-width:min(92vw,560px); background:var(--fg); color:var(--bg);
           padding:11px 16px; border-radius:12px; font-size:14px; display:none; z-index:20; }
  @media (max-width:820px) {
    .cabeza { grid-template-columns:1fr; gap:20px; }
    .ficha h1 { font-size:24px; }
    .rejilla { grid-template-columns:repeat(auto-fill, minmax(160px, 1fr)); gap:12px; }
    .acciones .btn { flex:1 1 160px; }
    /* En un móvil la barra se parte: el buscador baja a su propia fila. Sin
       esto «＋ Nuevo diseño» quedaba cortado y la página se desplazaba a lo
       ancho (panel estrecho, 2026-11-10). */
    .barra { flex-wrap:wrap; row-gap:8px; position:static; }
    #buscar { width:auto; flex:1 1 100%; min-width:0; order:5; }
    .barra .btn.pri { padding:9px 12px; }
  }
  /* Un hueco sin imagen no es un rectángulo blanco: en modo oscuro deslumbraba. */
  .foto.vacia, .version i { background:var(--tarjeta); border:1px dashed var(--linea); }
  .impresion { display:flex; flex-wrap:wrap; gap:8px; list-style:none; padding:0; margin:16px 0 0; }
  .impresion li { font-size:14px; font-weight:500; padding:5px 11px; border-radius:999px;
                  background:var(--tarjeta); border:1px solid var(--linea); font-variant-numeric:tabular-nums; }
  /* La obra (F7.3 (arbol)): el nodo que toca ocupa toda la fila, que es donde
     se lee su concepto o se decide si vale. */
  .piezas.arbol { grid-template-columns:repeat(auto-fill, minmax(260px, 1fr)); }
  .nodo { padding-bottom:12px; }
  .nodo[aria-current] { grid-column:1 / -1; border-color:var(--acento); }
  /* A toda la fila, la foto 4:3 medía más que la pantalla. */
  .nodo[aria-current] .foto-pieza { aspect-ratio:auto; height:280px; }
  .nodo > p, .nodo > ul, .nodo > .acciones, .nodo > .aviso, .nodo > .revision, .nodo > .impresion { margin:8px 12px 0; }
  .nodo .acciones { margin-top:12px; }
  .estado-nodo { display:inline-block; font-size:12px; font-weight:600; padding:2px 9px; border-radius:999px; background:var(--linea); margin-left:4px; }
  .estado-nodo.ok { background:var(--ok-bg); color:var(--ok); } .estado-nodo.mal { background:var(--mal-bg); color:var(--mal); }
  .estado-nodo.ambar { background:var(--ambar-bg); color:var(--ambar); } .estado-nodo.vivo { background:var(--vivo-bg); }
  .estado-nodo.suave { color:var(--suave); }
  .que-hace { font-size:14px; }
  .desglose { padding-left:22px; margin:18px 0 0; } .desglose > li { margin-bottom:12px; }
  .desglose .interfaz { margin:4px 0 0; padding-left:18px; }
  .interfaz { font-size:13px; color:var(--suave); padding-left:18px; }
  .impresa { font-size:14px; color:var(--ok); font-weight:600; }
  .visto-bueno textarea { display:block; width:100%; margin-top:8px; }
  .aprobado { margin-top:20px; border-top:1px solid var(--linea); padding-top:12px; }
  .aprobado > summary { cursor:pointer; color:var(--acento); font-size:14px; }
  .aprobado .revision { margin-top:4px; }
  /* Con el dedo, 44 px: «← Proyectos» medía 23 en el móvil. WCAG 2.2 pide 24
     como mínimo (2.5.8); 44 es lo que recomiendan Apple y la WCAG AAA (2.5.5). */
  @media (pointer:coarse) {
    .btn, .filtro, .volver, select, .version, .cerrar { min-height:44px; }
    .volver { display:inline-flex; align-items:center; }
  }
  /* Quien pide menos movimiento al sistema no ve latir ni saltar nada (WCAG 2.3.3). */
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation:none !important; transition:none !important; }
    .tarjeta:hover { transform:none; }
  }
"""

GUION_COMUN = r"""
  const aviso = document.getElementById("aviso");
  function avisar(texto) {
    aviso.textContent = texto; aviso.style.display = "block";
    clearTimeout(avisar.t); avisar.t = setTimeout(() => aviso.style.display = "none", 6000);
  }
  // Todo lo que escribió un modelo pasa por aquí: es dato, no HTML.
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const detalle = d => Array.isArray(d.detail) ? d.detail.map(x => x.msg).join("; ") : d.detail;
  async function enviar(url, cuerpo) {
    const r = await fetch(url, {method: "POST", headers: {"Content-Type": "application/json"},
                                body: cuerpo ? JSON.stringify(cuerpo) : undefined});
    let d = {}; try { d = await r.json(); } catch (e) {}
    return [r.ok, d];
  }
"""

GUION_GALERIA = r"""
  let filtro = "todas";
  function aplicarFiltro() {
    const q = document.querySelector("#buscar").value.trim().toLowerCase();
    document.querySelectorAll(".tarjeta").forEach(t => {
      const archivado = !!t.dataset.archivado;
      const [clave, valor] = filtro.split(":");
      const pasa = filtro === "archivo" ? archivado : !archivado && (filtro === "todas" || t.dataset[clave] === valor);
      t.hidden = !(pasa && (!q || t.dataset.nombre.includes(q)));
    });
  }
  document.querySelectorAll(".filtro").forEach(b => b.addEventListener("click", () => {
    filtro = b.dataset.filtro;
    document.querySelectorAll(".filtro").forEach(x => x.classList.toggle("activo", x === b));
    aplicarFiltro();
  }));
  document.querySelector("#buscar").addEventListener("input", aplicarFiltro);
  const tipo = document.querySelector("#tipo");
  tipo.addEventListener("change", () => {
    document.querySelector("#peticion").placeholder = tipo.selectedOptions[0].dataset.ejemplo;
  });
  const dialogo = document.querySelector("#nuevo");
  document.querySelector("#abrir-nuevo").addEventListener("click", () => { dialogo.showModal(); document.querySelector("#peticion").focus(); });
  document.querySelector("#disenar").addEventListener("click", async () => {
    const caja = document.querySelector("#peticion"), b = document.querySelector("#disenar");
    if (!caja.value.trim()) { avisar("Escribe primero qué quieres que diseñe."); caja.focus(); return; }
    b.disabled = true; b.textContent = "Lanzando…";
    const [ok, d] = await enviar("/api/disenar", {peticion: caja.value, tipo: document.querySelector("#tipo").value});
    if (ok) { location.href = "/p/" + encodeURIComponent(d.id); return; }
    avisar(detalle(d) || "No se pudo lanzar."); b.disabled = false; b.textContent = "Diseñar";
  });
  // Mientras algo trabaja, la galería se pone al día sola. Solo #vivo: el
  // diálogo queda fuera para no borrar lo que estás escribiendo.
  setInterval(async () => {
    if (!document.querySelector('.tarjeta[data-estado="en marcha"]')) return;
    try {
      const doc = new DOMParser().parseFromString(await (await fetch("/")).text(), "text/html");
      document.querySelector("#vivo").replaceWith(doc.querySelector("#vivo"));
      aplicarFiltro();
    } catch (e) { /* sin red un momento: otra vuelta */ }
  }, 15000);
  aplicarFiltro();
"""

GUION_VISOR = r"""
// El ensamble en 3D (F7.9 (visor)). Las mallas vienen de la verificación del
// conjunto; las poses, de /poses, que las calcula Python con la cinemática con
// la que se barrieron los choques: aquí solo se dibuja.
import * as THREE from "three";
import { OrbitControls } from "/estatico/OrbitControls.js";

const caja = document.querySelector(".visor3d"), mandos = document.querySelector(".mandos");
const base = caja.dataset.visor, ROJO = new THREE.Color("#e02424");

async function arrancar() {
  const r = await fetch(base + "/ensamble.json");
  if (!r.ok) return;
  const datos = await r.json();
  const lienzo = document.createElement("canvas");
  let render;
  try { render = new THREE.WebGLRenderer({canvas: lienzo, antialias: true, alpha: true}); }
  catch (e) { return; }               // sin WebGL: se queda el GIF
  render.setPixelRatio(Math.min(devicePixelRatio, 2));
  const escena = new THREE.Scene();
  escena.add(new THREE.HemisphereLight(0xffffff, 0x8a8f94, 1.6));
  const sol = new THREE.DirectionalLight(0xffffff, 1.8); sol.position.set(1, -2, 3); escena.add(sol);

  // Un grupo por pieza; lo comprado que monta va dentro del suyo y se mueve con él.
  const grupos = {}, mallas = {};
  for (const [s, x] of Object.entries(datos.solidos)) {
    const g = grupos[x.pieza] ??= Object.assign(new THREE.Group(), {matrixAutoUpdate: false});
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(x.v, 3));
    geo.setIndex(x.t); geo.computeVertexNormals();
    const color = new THREE.Color(x.color);
    const m = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({color, roughness: .75, metalness: .05, flatShading: true}));
    m.userData.color = color; mallas[s] = m; g.add(m);
  }
  Object.values(grupos).forEach(g => escena.add(g));

  // La tornillería (F7.8 (inventario)): lo mismo que dice «Lo que lleva»,
  // cada tornillo con la pieza donde apoya su cabeza y cada tuerca con la suya.
  // Poco metálico: sin un entorno que reflejar, el metal de three se ve negro.
  const acero = new THREE.MeshStandardMaterial({color: 0xd5dbe2, roughness: .35, metalness: .2});
  const ARRIBA = new THREE.Vector3(0, 1, 0);
  function cilindro(rPunta, rCabeza, alto, lados, en, eje, centro) {
    const m = new THREE.Mesh(new THREE.CylinderGeometry(rPunta, rCabeza, alto, lados), acero);
    const e = new THREE.Vector3(...eje).normalize();
    m.quaternion.setFromUnitVectors(ARRIBA, e);       // +y del cilindro: hacia la punta
    m.position.set(...en).addScaledVector(e, centro);
    return m;
  }
  const tornillos = await fetch(base + "/tornillos").then(r => r.ok ? r.json() : []).catch(() => []);
  for (const t of tornillos) {
    const g = grupos[t.pieza]; if (!g) continue;
    g.add(cilindro(t.d / 2, t.d / 2, t.largo, 16, t.cabeza, t.eje, t.largo / 2));
    if (t.avellanado) {                                // la cabeza, enrasada en su cono
      const h = (t.avellanado - t.d) / 2;
      g.add(cilindro(t.d / 2, t.avellanado / 2, h, 24, t.cabeza, t.eje, h / 2));
    } else {                                           // Allen: alta como el diámetro
      g.add(cilindro(t.cabeza_d / 2, t.cabeza_d / 2, t.d, 24, t.cabeza, t.eje, -t.d / 2));
    }
    for (const n of t.tuercas) {
      const r = n.entrecaras / Math.sqrt(3);
      grupos[n.pieza]?.add(cilindro(r, r, n.alto, 6, n.en, n.eje, n.alto / 2));
    }
  }

  // Z hacia arriba, como en FreeCAD y en la impresora.
  const camara = new THREE.PerspectiveCamera(35, 1, 1, 20000);
  camara.up.set(0, 0, 1);
  const mandar = new OrbitControls(camara, lienzo);
  mandar.enableDamping = true;

  function encuadrar() {
    const b = new THREE.Box3().setFromObject(escena), c = b.getCenter(new THREE.Vector3());
    const r = b.getSize(new THREE.Vector3()).length() / 2 || 50;
    camara.position.copy(c).add(new THREE.Vector3(1.3, -1.9, 1.2).normalize().multiplyScalar(r * 3.2));
    camara.near = r / 100; camara.far = r * 50; camara.updateProjectionMatrix();
    mandar.target.copy(c); mandar.update();
  }
  function medir() {
    const w = caja.clientWidth, h = caja.clientHeight || w * 3 / 4;
    render.setSize(w, h, false); camara.aspect = w / h; camara.updateProjectionMatrix();
  }

  const angulos = {}, rotulos = {};
  let pidiendo = null, otra = false;
  async function poner() {
    if (pidiendo) { otra = true; return; }
    const q = new URLSearchParams(Object.entries(angulos).map(([k, v]) => [k, String(v)]));
    pidiendo = fetch(base + "/poses?" + q).then(r => r.json());
    try {
      const d = await pidiendo;
      for (const [p, m] of Object.entries(d.poses))
        if (grupos[p]) { grupos[p].matrix.set(...m); grupos[p].matrixWorldNeedsUpdate = true; }
      const rojos = new Set(d.rojos);
      for (const [s, m] of Object.entries(mallas)) m.material.color.copy(rojos.has(s) ? ROJO : m.userData.color);
      const choca = [...new Set(d.rojos.map(s => datos.solidos[s]?.pieza))].map(p => datos.piezas[p]?.nombre);
      aviso.textContent = choca.length ? "Choca aquí: " + choca.join(" ↔ ") : "";
      // F7.10 (estudio): lo que pide la gravedad a cada servo en esta pose.
      const est = d.estudio;
      for (const [p, el] of Object.entries(pares)) {
        const x = est?.pares?.[p];
        el.textContent = !x ? "" : `par por gravedad ${+(x.Nm * 100 / 9.80665).toPrecision(2)} kgf·cm`
          + (x.uso == null ? "" : ` · ${Math.round(x.uso * 100)} % de lo que puede`);
        el.className = "par" + (x?.uso > 1 ? " mal" : "");
      }
      vuelco.textContent = est?.vuelco_mm == null ? "" : (est.vuelco_mm >= 0
        ? `Centro de masas a ${est.vuelco_mm.toFixed(1)} mm del borde del apoyo`
        : `Vuelca: el centro de masas sale ${(-est.vuelco_mm).toFixed(1)} mm del apoyo`);
      vuelco.className = "par" + (est?.vuelco_mm < 0 ? " mal" : "");
    } catch (e) { /* sin red un momento */ }
    pidiendo = null;
    if (otra) { otra = false; poner(); }
  }

  // Un deslizador por articulación, en la rejilla del barrido: entre dos de
  // sus puntos no se comprobó nada.
  const aviso = document.createElement("p"); aviso.className = "choca";
  const vuelco = document.createElement("p"); vuelco.className = "par";
  const pares = {};
  for (const a of datos.articulaciones) {
    angulos[a.pieza] = 0;
    const fila = document.createElement("label");
    const nombre = document.createElement("span"); nombre.textContent = a.nombre;
    const valor = document.createElement("output"); valor.textContent = "0°"; rotulos[a.pieza] = valor;
    const barra = Object.assign(document.createElement("input"),
      {type: "range", min: a.recorrido[0], max: a.recorrido[1], step: a.paso, value: 0});
    barra.dataset.pieza = a.pieza;
    barra.addEventListener("input", () => { angulos[a.pieza] = +barra.value; valor.textContent = barra.value + "°"; poner(); });
    fila.append(nombre, barra, valor); mandos.append(fila);
    pares[a.pieza] = Object.assign(document.createElement("p"), {className: "par"});
    mandos.append(pares[a.pieza]);
  }
  if (datos.articulaciones.length) {
    const tocar = Object.assign(document.createElement("button"), {className: "btn", type: "button", textContent: "▶ Mover"});
    let moviendo = null;
    tocar.addEventListener("click", () => {
      if (moviendo) { clearInterval(moviendo); moviendo = null; tocar.textContent = "▶ Mover"; return; }
      // Cada articulación por turno: a un extremo, al otro y de vuelta a 0.
      const pasos = [];
      for (const a of datos.articulaciones) {
        const ida = []; for (let v = 0; v >= a.recorrido[0]; v -= a.paso) ida.push(v);
        const vuelta = []; for (let v = a.recorrido[0]; v <= a.recorrido[1]; v += a.paso) vuelta.push(v);
        const fin = []; for (let v = a.recorrido[1]; v >= 0; v -= a.paso) fin.push(v);
        for (const v of [...ida, ...vuelta, ...fin]) pasos.push([a.pieza, v]);
      }
      let k = 0; tocar.textContent = "■ Parar";
      moviendo = setInterval(() => {
        const [p, v] = pasos[k++ % pasos.length];
        angulos[p] = v; rotulos[p].textContent = v + "°";
        mandos.querySelector(`input[data-pieza="${CSS.escape(p)}"]`).value = v; poner();
      }, 140);
    });
    mandos.append(tocar);
  }
  // Los tornillos van por dentro de las piezas: viéndolas a través se ve
  // qué une a qué.
  if (tornillos.length) {
    const fila = document.createElement("label"); fila.className = "atraves";
    const marca = Object.assign(document.createElement("input"), {type: "checkbox"});
    marca.addEventListener("change", () => {
      for (const m of Object.values(mallas)) {
        m.material.transparent = marca.checked; m.material.opacity = marca.checked ? .3 : 1;
        m.material.depthWrite = !marca.checked; m.material.needsUpdate = true;
      }
    });
    const texto = document.createElement("span");
    texto.textContent = `Ver a través (${tornillos.length} tornillos)`;
    fila.append(marca, texto); mandos.append(fila);
  }
  mandos.append(vuelco, aviso);

  caja.replaceChildren(lienzo);
  caja.classList.add("listo"); mandos.hidden = !datos.articulaciones.length && !tornillos.length;
  await poner(); medir(); encuadrar();
  new ResizeObserver(medir).observe(caja);
  (function bucle() { mandar.update(); render.render(escena, camara); requestAnimationFrame(bucle); })();
}
arrancar();
"""

GUION_PROYECTO = r"""
  const pagina = document.querySelector(".proyecto");
  document.querySelectorAll("[data-abrir]").forEach(b => b.addEventListener("click", async () => {
    b.disabled = true; const antes = b.textContent; b.textContent = "Abriendo…";
    const nodo = b.dataset.nodo ? "?nodo=" + encodeURIComponent(b.dataset.nodo) : "";
    const [ok, d] = await enviar("/proyectos/" + encodeURIComponent(b.dataset.abrir) + "/abrir" + nodo);
    avisar(ok ? "PrusaSlicer abierto con " + d.abiertas + " piezas" : (detalle(d) || "No se pudo abrir"));
    b.disabled = false; b.textContent = antes;
  }));
  // La obra (F7.3 (arbol)): cada botón de un nodo llama a su ruta y recarga.
  const obra = (el, accion) => "/api/proyectos/" + encodeURIComponent(el.dataset.proyectoObra) +
    "/nodos/" + encodeURIComponent(el.dataset[accion]) + "/" + accion;
  document.querySelectorAll("[data-lista]").forEach(b => b.addEventListener("click", async () => {
    b.disabled = true; b.textContent = "Fichándola…";
    const [ok, d] = await enviar(obra(b, "lista"), {});
    if (ok) { location.reload(); return; }
    avisar(detalle(d) || "No se pudo."); b.disabled = false; b.textContent = "Está bien, la siguiente";
  }));
  document.querySelectorAll("[data-seguir]").forEach(b => b.addEventListener("click", async () => {
    const antes = b.textContent; b.disabled = true; b.textContent = "Lanzando…";
    const [ok, d] = await enviar("/api/proyectos/" + encodeURIComponent(b.dataset.seguir) + "/seguir", {});
    if (ok) { location.reload(); return; }
    avisar(detalle(d) || "No se pudo."); b.disabled = false; b.textContent = antes;
  }));
  document.querySelectorAll("form[data-impresa], form[data-rehacer]").forEach(f => f.addEventListener("submit", async ev => {
    ev.preventDefault();
    const accion = f.dataset.impresa ? "impresa" : "rehacer";
    const caja = f.querySelector("input, textarea"), b = f.querySelector("button");
    if (accion === "rehacer" && !caja.value.trim() && !confirm("Sin decir qué cambiar, se rediseña desde cero. ¿Seguro?")) return;
    b.disabled = true;
    const [ok, d] = await enviar(obra(f, accion), accion === "impresa" ? {nota: caja.value} : {cambio: caja.value});
    if (ok) { location.reload(); return; }
    avisar(detalle(d) || "No se pudo."); b.disabled = false;
  }));
  document.querySelectorAll("form[data-modificar]").forEach(f => f.addEventListener("submit", async ev => {
    ev.preventDefault();
    const caja = f.querySelector("[name=cambio]"), b = f.querySelector("button");
    if (!caja.value.trim()) { avisar("Escribe primero qué quieres cambiar."); caja.focus(); return; }
    b.disabled = true; const antes = b.textContent; b.textContent = "Lanzando…";
    const [ok, d] = await enviar("/api/proyectos/" + encodeURIComponent(f.dataset.base) + "/modificar",
                                 {peticion: caja.value});
    if (ok) { location.href = "/p/" + encodeURIComponent(f.dataset.modificar); return; }
    avisar(detalle(d) || "No se pudo lanzar."); b.disabled = false; b.textContent = antes;
  }));
  document.querySelectorAll("form[data-aprobar]").forEach(f => f.addEventListener("submit", async ev => {
    ev.preventDefault();
    const caja = f.querySelector("[name=respuestas]");
    const contestar = ev.submitter && ev.submitter.hasAttribute("data-contestar");
    if (contestar && !caja.value.trim()) { avisar("Escribe primero tu respuesta."); caja.focus(); return; }
    // Aprobar con algo escrito lo perdería: lo escrito es una corrección.
    if (!contestar && caja.value.trim()) { avisar("Has escrito algo: pulsa «Contestar» para que lo tenga en cuenta."); return; }
    f.querySelectorAll("button").forEach(b => b.disabled = true);
    const [ok, d] = await enviar("/api/proyectos/" + encodeURIComponent(f.dataset.aprobar) + "/aprobar",
                                 {respuestas: contestar ? caja.value : ""});
    if (ok) { location.reload(); return; }
    avisar(detalle(d) || "No se pudo."); f.querySelectorAll("button").forEach(b => b.disabled = false);
  }));
  document.querySelector("select[data-categoria]").addEventListener("change", async ev => {
    const [ok, d] = await enviar("/api/proyectos/" + encodeURIComponent(ev.target.dataset.categoria) + "/categoria",
                                 {categoria: ev.target.value});
    avisar(ok ? "Movido a «" + ev.target.value + "»" : (detalle(d) || "No se pudo cambiar"));
  });

  // Lo técnico, solo si se abre: las rondas, lo medido y el informe entero.
  const tecnico = document.querySelector(".tecnico");
  tecnico.addEventListener("toggle", async () => {
    if (!tecnico.open || tecnico.dataset.cargado) return;
    tecnico.dataset.cargado = "1";
    const caja = tecnico.querySelector(".contenido");
    caja.textContent = "Cargando…";
    try {
      const d = await (await fetch("/api/proyectos/" + encodeURIComponent(tecnico.dataset.version))).json();
      const num = v => v === null || v === undefined ? "—" : Number(v).toFixed(2);
      let h = "";
      if (d.requisitos) h += "<h3>Movimientos medidos</h3><table><tr><th>Qué</th><th>Pedido</th><th>Medido</th><th></th></tr>" +
        d.requisitos.filas.map(f => `<tr><td>${esc(f.descripcion)}</td><td>${num(f.esperado)} ± ${num(f.tolerancia)}</td><td>${num(f.medido)}</td><td>${f.cumple ? "✓" : f.cumple === false ? "✗" : "?"}</td></tr>`).join("") + "</table>";
      h += (d.documentos || []).filter(x => x.archivo !== "calibracion.md").map(x => `<h3>${esc(x.titulo)}</h3><div class="documento">${x.html}</div>`).join("");
      if (d.rondas && d.rondas.length) h += "<h3>Rondas</h3>" + [...d.rondas].reverse().map(r =>
        `<p><b>Ronda ${r.ronda}</b> ${esc(r.titulo || "")}${r.resuelta ? " · ✓" : ""}</p>${r.feedback ? `<pre>${esc(r.feedback)}</pre>` : ""}`).join("");
      if (d.coste) h += `<p>Coste: ${num(d.coste.usd)} de ${num(d.coste.tope_usd)} USD en ${d.coste.llamadas} llamadas.</p>`;
      if (d.peticion) h += `<h3>Petición completa</h3><pre>${esc(d.peticion)}</pre>`;
      caja.innerHTML = h || "<p>No hay nada más que contar de esta versión.</p>";
    } catch (e) { caja.textContent = "No se pudo cargar: " + e; }
  });

  // Cancelar el diseño en marcha (F9.12 (pantalla)). Delegado en la página: el
  // bloque #en-marcha se cambia entero cada 10 s, y un manejador puesto en el
  // botón se iría con el primero.
  let cancelando = false;
  pagina.addEventListener("click", async ev => {
    const b = ev.target.closest("[data-cancelar]");
    if (!b || cancelando) return;
    if (!confirm("Se para el diseño; lo gastado hasta ahora no se recupera. ¿Cancelarlo?")) return;
    cancelando = true; b.disabled = true; const antes = b.textContent; b.textContent = "Cancelando…";
    const [ok, d] = await enviar("/api/proyectos/" + encodeURIComponent(b.dataset.cancelar) + "/cancelar");
    if (ok) { location.reload(); return; }
    // P. ej. lo lanzó Crafty desde su contenedor: la ruta dice desde dónde se para.
    avisar(detalle(d) || "No se pudo cancelar."); cancelando = false; b.disabled = false; b.textContent = antes;
  });

  // Mientras se diseña, la línea de progreso se pone al día; al terminar,
  // la página se recarga, salvo que estés escribiendo un cambio.
  const enMarcha = document.querySelector("#en-marcha");
  if (enMarcha) setInterval(async () => {
    try {
      const doc = new DOMParser().parseFromString(await (await fetch(location.href)).text(), "text/html");
      if (cancelando) return;   // el botón está diciendo «Cancelando…»: no se le cambia debajo
      const nuevo = doc.querySelector("#en-marcha");
      const escribiendo = [...document.querySelectorAll("[name=cambio]")].some(x => x.value.trim());
      if (nuevo) document.querySelector("#en-marcha").replaceWith(nuevo);
      else if (!escribiendo) location.reload();
    } catch (e) { /* otra vuelta */ }
  }, 10000);
"""
