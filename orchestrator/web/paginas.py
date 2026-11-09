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


def galeria(grupos: list[dict], workspace: Path, hay_puente: bool, puede_pedir: bool) -> str:
    tarjetas, cuenta = [], {}
    # Lo que está trabajando, arriba; luego lo último.
    for g in sorted(grupos, key=lambda g: not g.get("en_marcha")):
        v = next(x for x in g["versiones"] if x["id"] == g["mejor"])
        estado = "en marcha" if g.get("en_marcha") else v["estado"]
        frase, clase = ESTADOS.get(estado, (estado, "suave"))
        categoria = categoria_de(workspace, g)
        archivado = g["seccion"] == "archivo"
        if not archivado:
            cuenta[categoria] = cuenta.get(categoria, 0) + 1
        nombre = nombre_de(workspace, g)
        imagen = _imagen(v)
        foto = (f'<img src="{e(imagen)}" alt="" loading="lazy">' if imagen else
                '<span class="sin-foto">Diseñando…</span>' if estado == "en marcha" else
                '<span class="sin-foto">Sin piezas</span>')
        versiones = len(g["versiones"])
        detalle = " · ".join(x for x in (_fecha(g["versiones"][-1]["id"]),
                                         f"{versiones} versiones" if versiones > 1 else "") if x)
        tarjetas.append(f"""
      <a class="tarjeta" href="/p/{e(g['id'])}" data-id="{e(g['id'])}" data-estado="{e(estado)}"
         data-categoria="{e(categoria)}" data-nombre="{e(nombre.lower())}"{' data-archivado="1"' if archivado else ''}>
        <div class="foto">{foto}</div>
        <div class="pie-tarjeta">
          <div class="nombre">{e(nombre)}</div>
          <div class="linea"><span class="pastilla {clase}">{e(frase)}</span><span class="suave">{e(detalle)}</span></div>
        </div>
      </a>""")
    archivados = sum(1 for g in grupos if g["seccion"] == "archivo")
    filtros = [f'<button class="filtro activo" data-filtro="todas">Todos <span>{sum(cuenta.values())}</span></button>']
    for c in CATEGORIAS:
        if cuenta.get(c):
            filtros.append(f'<button class="filtro" data-filtro="{e(c)}">{e(c.capitalize())} <span>{cuenta[c]}</span></button>')
    if archivados:
        filtros.append(f'<button class="filtro" data-filtro="archivo">Archivo <span>{archivados}</span></button>')
    vacio = ('<p class="vacio">Todavía no hay proyectos. Pide el primero con «Nuevo diseño», '
             'o por Telegram a Crafty.</p>') if not grupos else ""
    ocupado = any(g.get("en_marcha") for g in grupos)
    opciones = "".join(f'<option value="{e(g["mejor"])}">{e(_recortar(nombre_de(workspace, g), 60))}</option>'
                       for g in grupos)
    # Lo que tarda y cuesta va siempre: con algo en marcha desaparecía, y es
    # justo cuando la persona decide si esperar o volver luego.
    coste = "Tarda de 5 a 60 minutos y cuesta hasta 5 USD."
    nota = ("Esta web no tiene con qué lanzar diseños." if not puede_pedir else
            f"{coste} Hay un diseño en marcha: espera a que termine." if ocupado else
            f"{coste} Lo verás aparecer en la galería.")
    return _documento("Intelliprint", f"""
  <header class="barra">
    <a class="marca" href="/">Intelliprint</a>
    <input id="buscar" type="search" placeholder="Buscar" aria-label="Buscar proyectos">
    <button class="btn pri" id="abrir-nuevo">＋ Nuevo diseño</button>
  </header>
  <dialog id="nuevo">
    <form method="dialog" class="cabeza-dialogo"><h2>Nuevo diseño</h2><button class="cerrar" aria-label="Cerrar">✕</button></form>
    <label class="partir">Qué es <select id="tipo"><option value="pieza" data-ejemplo="{e(EJEMPLOS['pieza'])}">una pieza (soporte, gancho, adaptador…)</option><option value="mecanismo" data-ejemplo="{e(EJEMPLOS['mecanismo'])}">un mecanismo (piezas que se mueven)</option><option value="obra" data-ejemplo="{e(EJEMPLOS['obra'])}">un proyecto de varias piezas, pieza a pieza</option></select></label>
    <label for="peticion" class="partir">Qué quieres</label>
    <textarea id="peticion" rows="9" placeholder="{e(EJEMPLOS['pieza'])}"></textarea>
    <label class="partir">Partir de <select id="basado_en"><option value="">nada, empezar de cero</option>{opciones}</select></label>
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


def _componente(x: dict) -> str:
    """Un componente que aloja la pieza (F6.11 (biblioteca)): su tamaño, cómo
    entra, cómo se sujeta y de qué planos salen sus medidas."""
    from orchestrator.componentes import cargar, envolvente

    from orchestrator.schemas.concepto import AJUSTES

    # Antes iba en una línea: «entra Se introduce a presión… .; se sujeta:
    # A presión…» (proyecto del 608ZZ, 2026-11-06).
    ajuste = AJUSTES.get(x.get("ajuste") or "slide", "")
    como = (f'<br>Cómo entra: {e(x.get("como_entra", ""))}'
            f'<br>Cómo se sujeta: {e(x.get("como_se_sujeta", ""))}'
            f'<br>Ajuste: {e(ajuste)} <small>(la holgura sale del perfil de la impresora)</small>')
    try:
        f = cargar(str(x.get("id")))
    except (KeyError, ValueError):
        return (f'<tr><td>{e(str(x.get("id")))} (no hay ficha){como}</td>'
                '<td class="valor"></td><td class="fuente"></td></tr>')
    a, b = envolvente(f)
    tamano = " × ".join(f"{round(y - z, 3):g}" for z, y in zip(a, b)) + " mm"
    urls = list(dict.fromkeys(fuente.url for fuente in f.fuentes))
    fuentes = ", ".join(f'<a href="{e(u)}" target="_blank" rel="noopener">{e(_dominio(u))}</a>'
                        for u in urls)
    medido = "medido con calibre" if f.verificado else "sin verificar con calibre"
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
    partes.append(f'<h3>La idea</h3><p class="idea">{e(c["idea"])}</p>')
    if c.get("preguntas") and not aprobado:
        partes.append('<div class="preguntas"><b>Antes, contéstame</b><ol>'
                      + "".join(f"<li>{e(p)}</li>" for p in c["preguntas"]) + "</ol></div>")

    componentes = [x for x in c.get("componentes") or [] if isinstance(x, dict)]
    if componentes:
        partes.append('<h3>Lo que aloja</h3><p class="nota-grupo">Su forma sale de la '
                      'ficha de la biblioteca; al dibujar se mete en la pieza para ver si '
                      'cabe y si entra. Mide el tuyo: las unidades varían.</p>'
                      '<table class="medidas"><tbody>'
                      + "".join(_componente(x) for x in componentes) + "</tbody></table>")

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
    laminado no se pone nada: una cifra estimada aquí parecería medida."""
    lamina = _leer(carpeta / "fabrication" / "slicing_report.json")
    if not lamina:
        return ""
    datos = [f"{lamina['grams']:.0f} g", _duracion(lamina["time_s"]),
             "con soportes" if lamina.get("needs_supports") else "sin soportes"]
    caja = (_leer(carpeta / "pieza_report.json") or {}).get("bbox_mm") or []
    if len(caja) == 3:
        datos.append(" × ".join(f"{round(x):g}" for x in caja) + " mm")
    return ('<ul class="impresion" aria-label="Lo que cuesta imprimirla">'
            + "".join(f"<li>{e(d)}</li>" for d in datos) + "</ul>")


def _legible(nombre: str) -> str:
    """«soporte_de_rodamiento» → «Soporte de rodamiento». El nombre de la
    carpeta es para el sistema; la persona lee castellano."""
    texto = nombre.replace("_", " ").strip()
    return texto[:1].upper() + texto[1:]


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
    "sin verificar": ("Conjunto: su verificación aún no existe", "suave"),
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
    arriba = (f'<div class="aviso ambar"><b>Siguiente: {e(ob.nodo(siguiente).nombre)}</b></div>'
              if siguiente else '<div class="aviso"><b>Todas las piezas están listas.</b></div>')
    tarjetas = []
    for i in ob.orden():
        n, estado = ob.nodo(i), estados[i]
        dir_nodo = carpeta / O.NODOS / i
        if estado == "bloqueado":
            espera = [ob.nodo(d).nombre for d in n.depende_de if estados[d] != "lista"]
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
            partes.append(f'<p class="corregida"><b>{rotulo}:</b> {e(retoque["cambio"])}</p>')
        for stl in piezas_de(dir_nodo):
            partes.insert(0, f'<div class="foto-pieza"><img src="/proyectos/{vid}/piezas/'
                             f'{e(stl.stem)}.png" alt="{e(n.nombre)}" loading="lazy"></div>')
        if estado == "concepto por aprobar":
            partes.append(_revision_del_concepto(dir_nodo, _visto_bueno(vid, bloqueo)))
        if estado == "con fallos":
            motivo = (_leer(dir_nodo / "pieza_report.json") or {}).get("motivo", "")
            partes.append(f'<div class="aviso mal"><b>Qué falla</b>'
                          f'<p>{e(_recortar(motivo, 400))}</p></div>')
        if estado in ("diseñada", "con fallos"):
            partes.append(_impresion(dir_nodo))
            sin_puente = "" if hay_puente else " disabled"
            partes.append(
                f'<div class="acciones"><button class="btn pri" data-lista="{e(i)}" '
                f'data-proyecto-obra="{vid}"{bloqueo}>Está bien, la siguiente</button>'
                f'<button class="btn" data-abrir="{vid}" data-nodo="{e(i)}"{sin_puente}>'
                'Abrir en PrusaSlicer</button></div>')
        marca = O.lista(carpeta, i)
        if marca:
            if marca.get("impresa"):
                nota = f": {e(marca['nota'])}" if marca.get("nota") else ""
                partes.append(f'<p class="impresa">✓ Impresa y probada{nota}</p>')
            else:
                partes.append(
                    f'<form class="cambiar-pieza" data-impresa="{e(i)}" data-proyecto-obra="{vid}">'
                    f'<input name="nota" placeholder="Cómo entró (opcional)" '
                    f'aria-label="Nota de la prueba de {e(n.nombre)}">'
                    '<button class="btn">Impresa y probada</button></form>')
        if marca or estado in ("diseñada", "con fallos"):
            # El aviso antes de pulsar: lo diseñado contra esta pieza se rehace con ella.
            arrastra = [ob.nodo(d).nombre for d in ob.dependientes(i)
                        if (carpeta / O.NODOS / d).exists()]
            aviso = f" (se rehace también {', '.join(arrastra)})" if arrastra else ""
            partes.append(
                f'<form class="cambiar-pieza" data-rehacer="{e(i)}" data-proyecto-obra="{vid}">'
                # Un textarea: el cambio de la brida del pan-tilt eran tres
                # frases, y en una línea no se leía lo que se escribía.
                f'<textarea name="cambio" rows="3" placeholder="Qué cambiar de esta pieza; '
                f'se corrige la que hay, no se rediseña" '
                f'aria-label="Qué cambiar de {e(n.nombre)}{e(aviso)}"{bloqueo}></textarea>'
                f'<button class="btn"{bloqueo}>Corregir</button></form>'
                + (f'<p class="nota-grupo">Cambiarla deshace también {e(", ".join(arrastra))}: '
                   'se diseñó contra esta.</p>' if arrastra else ""))
        actual = ' aria-current="step"' if i == siguiente else ""
        tarjetas.append(f'<div class="pieza nodo"{actual}>{"".join(partes)}</div>')
    return arriba, (f'<section><h2>Las piezas, una a una</h2>'
                    f'<div class="piezas arbol">{"".join(tarjetas)}</div></section>')


# --- La página de un proyecto -------------------------------------------------------


def proyecto(g: dict, elegida: str | None, workspace: Path, hay_puente: bool,
             puede_pedir: bool, ocupado: bool) -> str:
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
        explicacion = (f'<div class="aviso mal"><b>Por qué no salió</b><p>{e(_recortar(motivo, 220))}</p>'
                       '<p class="suave">Puedes pedir un cambio abajo, o ver los detalles técnicos.</p></div>')
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
        vivo = (f'<div class="aviso vivo" id="en-marcha" data-version="{e(corriendo["id"])}">'
                f'<b>Diseñando la versión {corriendo["version"]}</b>'
                f'<p>{e(_progreso(corriendo) + _lleva(_carpeta(workspace, corriendo)))}. '
                'Esta página se actualiza sola.</p></div>')

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
    visor = (f'<div class="visor"><div class="foto grande{vacia}">{foto}</div>{nav_tira}</div>'
             if imagen or not revisando else
             (f'<div class="visor">{nav_tira}</div>' if len(versiones) > 1 else ""))

    es_mecanismo = (carpeta / "mechanism.json").is_file()
    # El servidor ya sabía rehacer una pieza suelta (`lanzar_modificacion`),
    # pero la página solo ponía el formulario en los mecanismos: a un soporte
    # no había por dónde pedirle un cambio (2026-11-08).
    # Por aprobar ya tiene su formulario, «Contestar»: dos sitios donde
    # escribir una corrección y no se sabría cuál vale.
    se_puede_modificar = es_mecanismo or (
        (carpeta / "pieza.json").is_file() and v["estado"] != "por aprobar")
    se_puede_cambiar = puede_pedir and not ocupado
    motivo_no = ("" if se_puede_cambiar else
                 "Hay un diseño en marcha: espera a que termine." if ocupado else
                 "Esta web no puede lanzar diseños.")
    desactivado = "" if se_puede_cambiar else " disabled"

    # Las piezas, cada una con su miniatura y su «cambiar».
    usos = {p.get("name"): p.get("uso") or "general"
            for p in (_leer(carpeta / "mechanism.json") or {}).get("parts", [])}
    piezas = []
    for stl in piezas_de(carpeta):
        n = stl.stem
        uso = usos.get(n, "general")
        etiqueta = f'<span class="uso">{e(uso)}</span>' if uso != "general" else ""
        cambiar = (f"""<form class="cambiar-pieza" data-pieza="{e(n)}" data-modificar="{raiz}" data-base="{vid}">
            <input name="cambio" placeholder="Qué cambiar" aria-label="Qué cambiar de {e(n)}"{desactivado}>
            <button class="btn"{desactivado}>Cambiar</button></form>""" if es_mecanismo else "")
        piezas.append(f"""<div class="pieza"><div class="foto-pieza">
            <img src="/proyectos/{vid}/piezas/{e(n)}.png" alt="{e(_legible(n))}" loading="lazy"></div>
          <div class="nombre-pieza">{e(_legible(n))} {etiqueta}</div>{cambiar}</div>""")
    # Las de una obra ya salen en su nodo, con sus botones.
    seccion_piezas = (f'<section><h2>Piezas</h2><div class="piezas">{"".join(piezas)}</div></section>'
                      if piezas and not es_obra else "")

    cambiar_todo = (f"""<section class="cambiar"><h2>Cambiar algo</h2>
      <form class="cambiar-todo" data-modificar="{raiz}" data-base="{vid}">
        <textarea name="cambio" rows="2" placeholder="Por ejemplo: que la boca abra hasta 60 mm"{desactivado}></textarea>
        <div class="pie-cambiar"><span class="nota">{e(motivo_no or ("Crea una versión nueva a partir de esta. Si es de una sola pieza, cámbiala en su tarjeta: es más rápido." if es_mecanismo else "Crea una versión nueva a partir de esta."))}</span>
        <button class="btn pri"{desactivado}>Pedir cambio</button></div></form></section>""" if se_puede_modificar else "")

    # Las instrucciones de una pieza suelta (la de calibración), a la vista:
    # son lo que hay que leer para usarla.
    docs = "".join(f'<section><h2>{e(d["titulo"])}</h2><div class="documento">{d["html"]}</div></section>'
                   for d in documentos_de(carpeta) if d["archivo"] == "calibracion.md")

    categoria = categoria_de(workspace, g)
    opciones = "".join(f'<option value="{e(c)}"{" selected" if c == categoria else ""}>{e(c.capitalize())}</option>'
                       for c in CATEGORIAS)
    cuerpo = f"""
  <header class="barra"><a class="volver" href="/">← Proyectos</a><span class="estado-puente">{_puente(hay_puente)}</span></header>
  <main class="proyecto" data-proyecto="{raiz}" data-version="{vid}">
    <div class="cabeza{" sin-visor" if revisando and not imagen else ""}">
      {visor}
      <div class="ficha">
        <select class="categoria" data-categoria="{raiz}" aria-label="Categoría">{opciones}</select>
        <h1>{e(nombre)}</h1>
        <div class="estado-grande {clase}">{e(frase)}</div>
        {vivo}{explicacion}
        {_impresion(carpeta)}
        {f'<div class="acciones">{acciones}</div>' if acciones else ""}
        {aprobado}
        <p class="suave meta">Versión {v["version"]} de {len(versiones)} · {e(_fecha(v["id"]))}</p>
      </div>
    </div>
    {arbol}{seccion_piezas}{cambiar_todo}{docs}
    <details class="tecnico" data-version="{vid}"><summary>Detalles técnicos</summary><div class="contenido"></div></details>
  </main>"""
    return _documento(f"{nombre} · Intelliprint", cuerpo, GUION_PROYECTO)


def _puente(hay_puente: bool) -> str:
    return ('<span class="ok">● PrusaSlicer conectado</span>' if hay_puente else
            '<span class="suave" title="Arráncalo en el PC: powershell scripts\\start-host-mcps.ps1">'
            '● PrusaSlicer no conectado</span>')


def _documento(titulo: str, cuerpo: str, guion: str) -> str:
    return ('<!doctype html>\n<html lang="es"><head><meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{e(titulo)}</title>\n<style>{ESTILO}</style></head>\n"
            f'<body>{cuerpo}\n<div id="aviso" role="status"></div>\n'
            f"<script>{GUION_COMUN}{guion}</script>\n</body></html>")


EJEMPLOS = {
    # Uno por tipo: con «una pieza» elegida se enseñaba un sargento, que es
    # un mecanismo, y no se sabía qué tipo había que elegir (2026-11-08).
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
    "mecanismo": (
        "Qué quieres que haga, con todo lo que sepas. Por ejemplo:\n\n"
        "Un sargento de banco para piezas de hasta 40 mm, con tornillo M8 de ferretería. "
        "La mordaza móvil desliza sobre dos guías.\n\n"
        "Medidas, qué se mueve y cuánto, y qué sacrificar si algo no se puede."
    ),
}


ESTILO = """
  :root { --bg:#f4f4f1; --fg:#1b1b19; --suave:#6e6e68; --linea:#e3e3de; --tarjeta:#fff; --foto:#fff;
          --acento:#2463eb; --acento-fg:#fff; --ok:#1f7a4d; --ok-bg:#e3f4ea; --mal:#b3361c; --mal-bg:#fbe9e4;
          --ambar:#8a5a00; --ambar-bg:#fbf0d6; --vivo:#2463eb; --vivo-bg:#e6eefe; --sombra:0 1px 2px rgba(0,0,0,.05),0 4px 16px rgba(0,0,0,.05); }
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
  #vivo { padding:12px max(16px, calc((100% - 1200px)/2)) 48px; }
  .rejilla { display:grid; grid-template-columns:repeat(auto-fill, minmax(250px, 1fr)); gap:18px; }
  .tarjeta { display:flex; flex-direction:column; background:var(--tarjeta); border-radius:16px; overflow:hidden;
             box-shadow:var(--sombra); border:1px solid var(--linea); text-decoration:none; transition:transform .12s ease; }
  .tarjeta:hover { transform:translateY(-2px); }
  .tarjeta[hidden] { display:none; }
  .foto { aspect-ratio:4/3; background:var(--foto); display:flex; align-items:center; justify-content:center; overflow:hidden; }
  .foto img { width:100%; height:100%; object-fit:contain; }
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
  .corregida { font-size:14px; padding:8px 10px; border-radius:9px; background:var(--fondo-suave, rgba(127,127,127,.12)); }
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
    #buscar { width:auto; flex:1; min-width:0; }
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
      const pasa = filtro === "archivo" ? archivado : !archivado && (filtro === "todas" || t.dataset.categoria === filtro);
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
    const [ok, d] = await enviar("/api/disenar", {peticion: caja.value, tipo: document.querySelector("#tipo").value, basado_en: document.querySelector("#basado_en").value || null});
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
                                 {peticion: caja.value, pieza: f.dataset.pieza || ""});
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

  // Mientras se diseña, la línea de progreso se pone al día; al terminar,
  // la página se recarga, salvo que estés escribiendo un cambio.
  const enMarcha = document.querySelector("#en-marcha");
  if (enMarcha) setInterval(async () => {
    try {
      const doc = new DOMParser().parseFromString(await (await fetch(location.href)).text(), "text/html");
      const nuevo = doc.querySelector("#en-marcha");
      const escribiendo = [...document.querySelectorAll("[name=cambio]")].some(x => x.value.trim());
      if (nuevo) document.querySelector("#en-marcha").replaceWith(nuevo);
      else if (!escribiendo) location.reload();
    } catch (e) { /* otra vuelta */ }
  }, 10000);
"""
