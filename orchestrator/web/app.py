"""Interfaz web: pedir un diseño, ver los proyectos con sus versiones,
pedir modificaciones, bajarlos en zip y abrirlos en PrusaSlicer (F5.5 (web)).

Corre dentro del contenedor y se abre desde el navegador del PC. Es el
subconjunto de F5.5 (web) que hacía falta ya —encontrar un proyecto, llevárselo,
mirarlo en PrusaSlicer—; los botones de los gates llegan con ellos.

El identificador de un proyecto viene de la URL, es decir, lo escribe
quien quiera. Se trata como texto ajeno: un nombre, nunca una ruta.

    docker compose up -d web      ->  http://localhost:8080
"""

import html
import json
import io
import os
import zipfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field, field_validator

from orchestrator.impresion import perfil_activo
from orchestrator.proyecto_3mf import Pieza, escribir_3mf
from orchestrator.slicing import UsoDesconocido, ajustes_de_uso
from orchestrator.hostpaths import RutaFueraDelWorkspace, a_ruta_del_host
from orchestrator.jobs import JobStore
from orchestrator.registry import estado_de, indice
from orchestrator.web.documentos import documentos_de
from orchestrator.web.estadisticas import estadisticas
from orchestrator.web.versiones import (
    SECCIONES, agrupar, componer_modificacion, marca_de, raices)

# SECCIONES: dónde buscar. `archivo/` también: archivar no es borrar, y un
# intento fallido es la única prueba de por qué algo no funcionó.



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


def empaquetar(carpeta: Path) -> bytes:
    """El proyecto en un zip, dentro de una carpeta con su nombre.

    Sin el `.git` interno (F1.15 (versionado)): es el historial del sistema,
    no el diseño, y solo engorda la descarga.
    """
    carpeta = Path(carpeta)
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(carpeta.rglob("*")):
            relativa = f.relative_to(carpeta)
            if ".git" in relativa.parts or not f.is_file():
                continue
            z.write(f, f"{carpeta.name}/{relativa.as_posix()}")
    return memoria.getvalue()


def piezas_de(carpeta: Path) -> list[Path]:
    """Las STL que construyó el sistema. Las dos rutas del diseño —pieza
    única y mecanismo— las dejan en parts/<nombre>/<nombre>.stl."""
    return sorted(Path(carpeta).glob("parts/*/*.stl"))


def usos_de(carpeta: Path) -> dict[str, str]:
    """El uso que el diseñador declaró para cada pieza (F3.16 (usos)). Se lee
    el JSON a pelo: un mechanism.json anterior a los usos no lo trae, y no
    por eso deja de valer. Sin uso, «general»."""
    try:
        spec = json.loads((Path(carpeta) / "mechanism.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {p["name"]: p.get("uso") or "general" for p in spec.get("parts", []) if "name" in p}


def piezas_con_uso(carpeta: Path) -> list[dict]:
    usos = usos_de(carpeta)
    return [{"nombre": stl.stem, "uso": usos.get(stl.stem, "general")} for stl in piezas_de(carpeta)]


def _listar(workspace: Path) -> list[dict]:
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


class Modificacion(BaseModel):
    peticion: str = Field(max_length=20_000)

    @field_validator("peticion")
    @classmethod
    def _con_texto(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("escribe qué quieres que diseñe o que cambie")
        return v.strip()


class Pedido(Modificacion):
    basado_en: str | None = None


def _en_marcha(workspace: Path) -> str | None:
    """Un proyecto que sigue trabajando, lo lanzara quien lo lanzara.

    No basta con preguntar al JobStore de la web: Crafty lanza los suyos
    desde el contenedor del MCP, y este no los conoce. Lo que ven los dos
    es el workspace."""
    carpeta = Path(workspace) / "projects"
    if not carpeta.is_dir():
        return None
    for fila in indice(carpeta):
        if fila["estado"] == "en marcha":
            return fila["id"]
    return None


def crear_app(workspace: Path, puente=None, host_workspace: str = "",
              trabajos: JobStore | None = None, raiz: Path = Path(".")) -> FastAPI:
    """La aplicación. `puente` es la URL del MCP del host, o en los tests el
    propio servidor; None si no hay puente configurado. `trabajos` lanza los
    diseños que se piden desde la página; None si esta web no puede. `raiz`
    es donde está config/, para leer el perfil activo."""
    app = FastAPI(title="Intelliprint", docs_url=None, redoc_url=None)
    perfil = perfil_activo(raiz).laminado
    app.state.trabajos = trabajos
    workspace = Path(workspace)

    def _proyecto(id: str) -> Path:
        try:
            return resolver_proyecto(id, workspace)
        except ProyectoDesconocido:
            raise HTTPException(404, f"no hay ningún proyecto llamado {id!r}")

    @app.post("/api/disenar")
    def disenar(pedido: Pedido) -> dict:
        if trabajos is None:
            raise HTTPException(503, "esta web no tiene con qué lanzar diseños")
        referencias = [_proyecto(pedido.basado_en).name] if pedido.basado_en else []
        otro = trabajos.current() or _en_marcha(workspace)
        if otro:
            raise HTTPException(
                409, f"ya hay un proyecto en marcha ({otro}); espera a que termine")
        try:
            return {"id": trabajos.start(pedido.peticion, referencias=referencias)}
        except RuntimeError as e:
            raise HTTPException(409, str(e))

    @app.post("/api/proyectos/{id}/modificar")
    def modificar(id: str, pedido: Modificacion) -> dict:
        """Una versión nueva del proyecto de `id`, partiendo de `id`.

        Antes, cambiar algo era pedir un diseño nuevo «partiendo de» otro, y
        cada intento salía como un proyecto más en la lista."""
        if trabajos is None:
            raise HTTPException(503, "esta web no tiene con qué lanzar diseños")
        base = _proyecto(id)
        otro = trabajos.current() or _en_marcha(workspace)
        if otro:
            raise HTTPException(
                409, f"ya hay un proyecto en marcha ({otro}); espera a que termine")
        raiz = raices(workspace).get(base.name, base.name)
        original = ((base / "request.md").read_text(encoding="utf-8", errors="ignore")
                    if (base / "request.md").is_file() else "")
        # Sin mechanism.json el cargador de referencias rechaza el id y el
        # trabajo moriría al arrancar; la petición ya lleva lo que se pidió.
        referencias = [base.name] if (base / "mechanism.json").is_file() else []
        try:
            nueva = trabajos.start(
                componer_modificacion(original, base.name, pedido.peticion),
                referencias=referencias,
                proyecto={"proyecto": raiz, "basado_en": base.name,
                          "modificacion": pedido.peticion})
        except RuntimeError as e:
            raise HTTPException(409, str(e))
        return {"id": nueva, "proyecto": raiz}

    @app.get("/api/proyectos")
    def proyectos() -> list[dict]:
        return agrupar(_listar(workspace), workspace)

    @app.get("/api/proyectos/{id}")
    def detalle(id: str) -> dict:
        """Una VERSIÓN: el id es el de su carpeta."""
        carpeta = _proyecto(id)
        en_marcha = estado_de(carpeta)["estado"] == "en marcha"
        peticion = ((carpeta / "request.md").read_text(encoding="utf-8", errors="ignore").strip()
                    if (carpeta / "request.md").is_file() else "")
        return {"id": carpeta.name, "peticion": peticion,
                "modificacion": marca_de(carpeta).get("modificacion"),
                "piezas": piezas_con_uso(carpeta),
                "es_mecanismo": (carpeta / "mechanism.json").is_file(),
                "vista": bool(piezas_de(carpeta)),
                "documentos": documentos_de(carpeta),
                **estadisticas(carpeta, en_marcha=en_marcha)}

    @app.get("/proyectos/{id}/vista.png")
    def vista(id: str) -> FileResponse:
        """Las piezas dibujadas, para lo que no tiene animación. Se guarda en
        el proyecto y solo se redibuja si alguna STL es más nueva."""
        carpeta = _proyecto(id)
        piezas = piezas_de(carpeta)
        if not piezas:
            raise HTTPException(404, "este proyecto no tiene piezas construidas")
        png = carpeta / "vista.png"
        if not png.is_file() or png.stat().st_mtime < max(p.stat().st_mtime for p in piezas):
            from orchestrator.vista import dibujar_piezas
            try:
                dibujar_piezas(piezas, png)
            except ValueError as e:
                raise HTTPException(409, str(e))
        return FileResponse(png, media_type="image/png")

    @app.get("/proyectos/{id}/animation.gif")
    def animacion(id: str) -> FileResponse:
        gif = _proyecto(id) / "animation.gif"
        if not gif.is_file():
            raise HTTPException(404, "este proyecto todavía no tiene animación")
        return FileResponse(gif, media_type="image/gif")

    @app.get("/proyectos/{id}.zip")
    def bajar(id: str) -> Response:
        carpeta = _proyecto(id)
        return Response(
            empaquetar(carpeta), media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{carpeta.name}.zip"'},
        )

    @app.post("/proyectos/{id}/abrir")
    def abrir(id: str) -> dict:
        carpeta = _proyecto(id)
        piezas = piezas_de(carpeta)
        if not piezas:
            raise HTTPException(409, "este proyecto no tiene ninguna pieza construida")
        if puente is None:
            raise HTTPException(
                503, "no hay puente con el PrusaSlicer del PC. Arráncalo en el "
                "host con: powershell scripts\\start-host-mcps.ps1")

        from orchestrator.mcp.client import ClienteMCP, LlamadaFallida, PuenteInalcanzable
        # Un proyecto .3mf con cada pieza y los ajustes de su uso: con las
        # STL sueltas, el gatillo que aguanta un resorte se laminaría como
        # la tapa (F3.16 (usos)).
        catalogo = Path(raiz) / "config" / "slicing"
        usos = usos_de(carpeta)
        try:
            proyecto = escribir_3mf(
                [Pieza(p.stem, p, ajustes_de_uso(usos.get(p.stem, "general"), catalogo))
                 for p in piezas],
                catalogo / perfil, carpeta / "imprimir" / f"{carpeta.name}.3mf")
        except (UsoDesconocido, ValueError) as e:
            raise HTTPException(409, f"no se pudo preparar el proyecto para PrusaSlicer: {e}")
        try:
            stls = [a_ruta_del_host(proyecto.as_posix(), workspace.as_posix(), host_workspace)]
        except RutaFueraDelWorkspace as e:
            raise HTTPException(500, str(e))
        try:
            respuesta = ClienteMCP(puente, timeout=60).llamar(
                "abrir_en_prusaslicer", stls=stls, perfil=perfil)
        except PuenteInalcanzable as e:
            raise HTTPException(
                503, f"el puente del PC no contesta ({e}). ¿Está arrancado? "
                "powershell scripts\\start-host-mcps.ps1")
        except LlamadaFallida as e:
            raise HTTPException(502, str(e))
        if not respuesta.get("ok"):
            raise HTTPException(502, respuesta.get("error") or "PrusaSlicer no se abrió")
        return {**respuesta, "abiertas": len(piezas)}

    @app.get("/", response_class=HTMLResponse)
    def portada() -> str:
        return _pagina(agrupar(_listar(workspace), workspace), hay_puente=puente is not None,
                       puede_pedir=trabajos is not None)

    return app


# --- La página ---------------------------------------------------------------
#
# Lo que se enseña de cada proyecto es aritmética del código —rondas, coste,
# requisitos medidos contra lo pedido— más el informe del revisor, que se
# cuenta aparte y nunca como aprobación (ADR-003). Todo el texto que escribió
# un modelo (títulos, planes, motivos) se escapa: es dato, no HTML.

ICONOS = {"aprobado": "✅", "con reparos": "🟠", "antiguo": "📦", "fallido": "❌",
          "en marcha": "⏳", "incompleto": "⚠️"}


def _requisitos_celda(r: dict | None) -> str:
    if not r:
        return '<span class="suave">—</span>'
    titulo = f"medidos en la ronda {r['de_la_ronda']}"
    if r.get("sin_medir"):
        titulo += f"; {r['sin_medir']} sin poder medir"
    if r.get("provisional"):
        # Ninguna ronda llegó a barrer el recorrido: lo medido no está
        # comprobado. En verde parecería terminado, y no lo está.
        titulo += ("; PROVISIONAL: ninguna ronda ha llegado todavía a barrer el recorrido "
                   "completo, así que no está comprobado")
        return (f'<span class="chip suave" title="{html.escape(titulo)}">'
                f'{r["cumplen"]}/{r["total"]}?</span>')
    clase = "ok" if r["cumplen"] == r["total"] else ("mal" if r["cumplen"] == 0 else "ambar")
    return (f'<span class="chip {clase}" title="{html.escape(titulo)}">'
            f'{r["cumplen"]}/{r["total"]}</span>')


def _revisor_celda(r: dict | None) -> str:
    if not r:
        return '<span class="suave">—</span>'
    return (f'<span class="ok" title="cumple">✓{r["cumple"]}</span> '
            f'<span class="mal" title="no cumple">✗{r["no_cumple"]}</span> '
            f'<span class="suave" title="no verificable: nadie lo comprueba">?{r["no_verificable"]}</span>')


def _coste_celda(c: dict | None) -> str:
    if not c:
        return '<span class="suave">—</span>'
    fraccion = min(c["fraccion"] or 0, 1)
    clase = "mal" if fraccion >= 0.9 else ("ambar" if fraccion >= 0.6 else "")
    return (f'<div class="num">{c["usd"]:.2f} <span class="suave">/ {c["tope_usd"]:.2f}</span></div>'
            f'<div class="barra" title="{c["tokens_salida"]:,} tokens de salida en {c["llamadas"]} llamadas">'
            f'<i class="{clase}" style="width:{fraccion * 100:.0f}%"></i></div>')


def _corto(texto: str, n: int) -> str:
    texto = " ".join((texto or "").split())
    return texto if len(texto) <= n else texto[:n] + "…"


def _opcion(v: dict, mejor: str) -> str:
    partes = [f"v{v['version']}", f"{ICONOS.get(v['estado'], '·')} {v['estado']}"]
    if v.get("ronda"):
        partes.append(f"ronda {v['ronda']}")
    if v.get("coste"):
        partes.append(f"{v['coste']['usd']:.2f} USD")
    if v.get("modificacion"):
        partes.append("cambio: " + _corto(v["modificacion"], 50))
    if v["id"] == mejor:
        partes.append("★ la mejor")
    elegida = " selected" if v["id"] == mejor else ""
    return (f'<option value="{html.escape(v["id"])}"{elegida} data-piezas="{v["piezas"]}">'
            f'{html.escape(" · ".join(partes))}</option>')


def _fila(g: dict, hay_puente: bool, puede_modificar: bool = False) -> str:
    """Un PROYECTO: lo de su mejor versión en la fila; en el panel, el
    selector de versiones y dónde pedir una modificación."""
    e = html.escape
    id_ = e(g["id"])
    versiones = g["versiones"]
    f = next(v for v in versiones if v["id"] == g["mejor"])
    mejor = e(f["id"])
    detalle = e(f.get("motivo") or (f["titulo"] if f["titulo"] != g["titulo"] else ""))
    sin_piezas = f["piezas"] == 0
    abrir_titulo = ("Sin piezas construidas" if sin_piezas else
                    "Arranca el puente en el PC primero" if not hay_puente else
                    f"Abre las {f['piezas']} piezas en tu PrusaSlicer con el perfil de la M5")
    desactivado = "disabled" if sin_piezas or not hay_puente else ""
    ronda = f.get("ronda") or 0
    linea = f"ronda {ronda} · {f['piezas']} piezas" if ronda else f"{f['piezas']} piezas"
    if len(versiones) > 1:
        linea = f"v{f['version']} de {len(versiones)}, la mejor · {linea}"
    ultima = versiones[-1]
    otra = ""
    if ultima["id"] != f["id"] and ultima["estado"] != "en marcha":
        # La fila enseña la mejor, no la última: sin esto, una modificación
        # que falló parecería no haberse hecho nunca.
        otra = (f'<div class="det">La más reciente, v{ultima["version"]}, quedó '
                f'{e(ultima["estado"])}: está en el selector de versiones.</div>')
    vivo = ""
    if g.get("en_marcha"):
        v = next(v for v in versiones if v["id"] == g["en_marcha"])
        que = e(v.get("ultima_etapa") or "arrancando")
        colgado = " · lleva un rato sin moverse" if v.get("parece_colgado") else ""
        cual = f"v{v['version']}: " if len(versiones) > 1 else ""
        vivo = f'<div class="vivo">● {cual}{que}{colgado}</div>'
    # Qué impide terminar, en una línea. Los requisitos son solo una de las
    # cosas que tienen que cumplirse: sin esto, «2/2» parecía «terminado».
    falla = ""
    if f.get("fallo") and f["estado"] in ("en marcha", "fallido"):
        otros = f" (y {f['fallos'] - 1} más)" if f.get("fallos", 1) > 1 else ""
        falla = (f'<div class="falla" title="{e(f["fallo"])}">✗ ronda {ronda}: '
                 f'{e(f["fallo"][:140])}{"…" if len(f["fallo"]) > 140 else ""}{otros}</div>')
    # Sin animación (no es un mecanismo), la vista de las piezas.
    miniatura = (f'<img class="mini" src="/proyectos/{mejor}/animation.gif" alt="" loading="lazy">'
                 if f.get("animacion") else
                 f'<img class="mini" src="/proyectos/{mejor}/vista.png" alt="" loading="lazy">'
                 if f["piezas"] else '<div class="mini vacia"></div>')
    estado = "en marcha" if g.get("en_marcha") else f["estado"]
    opciones = "".join(_opcion(v, f["id"]) for v in reversed(versiones))
    total = (f" · {g['usd_total']:.2f} USD entre todas" if len(versiones) > 1 and g.get("usd_total")
             else "")
    mod_desactivado = "" if puede_modificar else "disabled"
    modificar = (_cuadro_modificar(id_, len(versiones), mod_desactivado)
                 if any(v.get("es_mecanismo") for v in versiones) else "")
    return f"""
      <tr class="fila" data-id="{id_}" data-estado="{e(estado)}">
        <td class="estado" title="{e(f['estado'])}">{ICONOS.get(f['estado'], '·')}</td>
        <td class="col-mini">{miniatura}</td>
        <td><div class="id">{e(g["titulo"])}</div><div class="det">{detalle}</div>
            <div class="det">{linea}</div>{otra}{falla}{vivo}</td>
        <td class="num">{_requisitos_celda(f.get("requisitos"))}</td>
        <td class="num rev">{_revisor_celda(f.get("revisor"))}</td>
        <td class="coste">{_coste_celda(f.get("coste"))}</td>
        <td class="acc">
          <a class="btn" data-zip href="/proyectos/{mejor}.zip" download>Descargar .zip</a>
          <button class="btn pri" data-abrir="{mejor}" title="{e(abrir_titulo)}" {desactivado}>Slice in PrusaSlicer</button>
        </td>
      </tr>
      <tr class="panel" data-panel="{id_}" hidden><td colspan="7">
        <div class="versiones">
          <label>Versión <select data-versiones="{id_}">{opciones}</select></label>
          <span class="suave">{len(versiones)} {"versión" if len(versiones) == 1 else "versiones"}{total} · proyecto <code>{id_}</code></span>
        </div>
        {modificar}<div class="contenido"></div>
      </td></tr>"""


def _cuadro_modificar(id_: str, n: int, mod_desactivado: str) -> str:
    """Solo para mecanismos: una modificación relanza el DISEÑO del
    mecanismo con la petición del proyecto. Con la de una pieza de
    calibración, el diseñador inventaría un mecanismo (2026-10-24)."""
    return f"""<div class="modificar">
          <textarea data-modificar="{id_}" rows="3" placeholder="Qué quieres cambiar de la versión elegida. Por ejemplo: que la rueda tenga 16 dientes y la base 5 mm más gruesa."></textarea>
          <div class="pie"><span>Crea la v{n + 1} de este proyecto a partir de la versión elegida: su diseño y su petición, más el cambio.</span>
            <button class="btn pri" data-lanzar="{id_}" {mod_desactivado}>Pedir modificación</button></div>
        </div>
        """


def _tabla(filas: list[dict], hay_puente: bool, vacio: str, puede_modificar: bool = False) -> str:
    if not filas:
        return f'<p class="vacio">{vacio}</p>'
    cuerpo = "".join(_fila(f, hay_puente, puede_modificar) for f in filas)
    return f"""
    <div class="marco"><table>
      <thead><tr><th></th><th></th><th>Proyecto</th>
        <th class="num" title="Requisitos medidos por el código que cumplen lo pedido">Requisitos</th>
        <th class="num" title="Informe del revisor: no es una aprobación">Revisor</th>
        <th>Coste</th><th></th></tr></thead>
      <tbody>{cuerpo}</tbody>
    </table></div>"""


_ESTILO = """
  :root { --bg:#f7f7f5; --fg:#1d1d1b; --suave:#6b6b66; --linea:#e2e2dd; --fondo2:#f0f0ec;
          --tarjeta:#fff; --acento:#2f5d8a; --acento-fg:#fff; --ok:#2e7d4f; --mal:#a3432b; --ambar:#9a6a00; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#161615; --fg:#ececea; --suave:#9a9a94; --linea:#2c2c2a; --fondo2:#1b1b1a;
            --tarjeta:#1f1f1e; --acento:#6b9bd1; --acento-fg:#0e1620; --ok:#6cc08b; --mal:#e08a70; --ambar:#e0b454; }
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--fg);
         font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; }
  main { max-width:1200px; margin:0 auto; padding:28px 16px 60px; }
  h1 { font-size:22px; margin:0 0 4px; }
  h2 { font-size:13px; margin:32px 0 10px; color:var(--suave); font-weight:600;
       text-transform:uppercase; letter-spacing:.05em; }
  h3 { font-size:13px; margin:18px 0 8px; color:var(--suave); font-weight:600; }
  .cabecera { font-size:13px; margin-bottom:8px; display:flex; gap:16px; flex-wrap:wrap; }
  .ok { color:var(--ok); } .mal { color:var(--mal); } .ambar { color:var(--ambar); } .suave { color:var(--suave); }
  code { font-size:12px; background:var(--linea); padding:1px 5px; border-radius:4px; }
  .marco { overflow-x:auto; background:var(--tarjeta); border:1px solid var(--linea); border-radius:10px; }
  table { width:100%; border-collapse:collapse; }
  th, td { padding:10px 12px; text-align:left; border-bottom:1px solid var(--linea); vertical-align:top; }
  tbody tr:last-child td { border-bottom:0; }
  th { font-size:12px; color:var(--suave); font-weight:600; white-space:nowrap; }
  .num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
  .fila { cursor:pointer; }
  .fila:hover td { background:var(--fondo2); }
  .estado { width:28px; }
  .col-mini { width:64px; padding-right:0; }
  .mini { width:56px; height:42px; object-fit:cover; border-radius:6px; border:1px solid var(--linea); display:block; }
  .mini.vacia { background:var(--fondo2); }
  .id { font-weight:600; overflow-wrap:anywhere; }
  .det { font-size:13px; color:var(--suave); margin-top:2px; }
  .vivo { font-size:13px; color:var(--acento); margin-top:4px; }
  .falla { font-size:13px; color:var(--mal); margin-top:4px; }
  .chip { font-weight:600; }
  .rev span { margin-left:4px; }
  .coste { min-width:110px; }
  .barra { height:4px; background:var(--linea); border-radius:2px; margin-top:6px; overflow:hidden; }
  .barra i { display:block; height:100%; background:var(--acento); }
  .barra i.ambar { background:var(--ambar); } .barra i.mal { background:var(--mal); }
  .acc { white-space:nowrap; text-align:right; }
  .btn { display:inline-block; font:inherit; font-size:13px; padding:6px 11px; margin-left:6px;
         border-radius:7px; border:1px solid var(--linea); background:var(--tarjeta);
         color:var(--fg); text-decoration:none; cursor:pointer; }
  .btn:hover { border-color:var(--suave); }
  .btn.pri { background:var(--acento); color:var(--acento-fg); border-color:var(--acento); }
  .btn:disabled { opacity:.4; cursor:not-allowed; }
  .panel > td { background:var(--fondo2); padding:16px 18px 20px; }
  .detalle { display:grid; grid-template-columns:minmax(0,340px) minmax(0,1fr); gap:24px; }
  .detalle .gif { width:100%; border-radius:8px; border:1px solid var(--linea); background:var(--tarjeta); }
  .sin-gif { padding:40px 12px; text-align:center; color:var(--suave); border:1px dashed var(--linea); border-radius:8px; }
  .detalle table { background:var(--tarjeta); border:1px solid var(--linea); border-radius:8px; font-size:13px; }
  .detalle th, .detalle td { padding:6px 10px; }
  .rondas { list-style:none; margin:0; padding:0; }
  .rondas li { background:var(--tarjeta); border:1px solid var(--linea); border-radius:8px; padding:10px 12px; margin-bottom:8px; font-size:13px; }
  .rondas b { font-size:14px; }
  .rondas pre { white-space:pre-wrap; font:12px/1.4 ui-monospace,Consolas,monospace; margin:6px 0 0; color:var(--fg); }
  .plan { margin-top:6px; }
  .plan summary { cursor:pointer; list-style:none; }
  .plan summary::-webkit-details-marker { display:none; }
  .plan summary::before { content:"▸ "; color:var(--suave); }
  .plan[open] summary::before { content:"▾ "; }
  .plan[open] .resumen { display:none; }
  .resumen { color:var(--fg); }
  .resumen.mal { color:var(--mal); }
  .plan > div { margin-left:14px; }
  .etiqueta { font-size:11px; text-transform:uppercase; letter-spacing:.04em; color:var(--suave); margin-top:6px; }
  .vacio { color:var(--suave); }
  .documento { background:var(--tarjeta); border:1px solid var(--linea); border-radius:8px; padding:4px 14px 10px;
               font-size:13px; margin-bottom:12px; }
  .documento h3, .documento h4, .documento h5 { margin:12px 0 6px; font-size:13px; }
  .documento ul { padding-left:18px; margin:6px 0; }
  .documento p { margin:6px 0; }
  .documento pre { white-space:pre-wrap; font:12px/1.4 ui-monospace,Consolas,monospace;
                   background:var(--fondo2); padding:8px 10px; border-radius:6px; }
  .pedir textarea, .modificar textarea { width:100%; font:inherit; font-size:14px; padding:10px 12px; resize:vertical;
                    background:var(--tarjeta); color:var(--fg); border:1px solid var(--linea); border-radius:10px; }
  .pedir textarea:focus, .modificar textarea:focus { outline:2px solid var(--acento); outline-offset:-1px; }
  .pedir .pie, .modificar .pie { display:flex; gap:12px; align-items:center; justify-content:space-between;
                flex-wrap:wrap; margin-top:8px; font-size:13px; color:var(--suave); }
  .pedir select, .versiones select { font:inherit; max-width:min(70vw,520px); margin-left:4px; padding:4px 6px;
                  background:var(--tarjeta); color:var(--fg); border:1px solid var(--linea); border-radius:7px; }
  .pedir .btn, .modificar .btn { margin-left:0; padding:8px 18px; font-size:14px; }
  .versiones { display:flex; gap:12px; align-items:center; flex-wrap:wrap; font-size:13px; margin-bottom:12px; }
  .versiones label { font-weight:600; }
  .modificar { margin-bottom:18px; }
  .modificar textarea { font-size:13px; }
  .pedido { background:var(--tarjeta); border:1px solid var(--linea); border-left:3px solid var(--acento);
            border-radius:8px; padding:8px 12px; font-size:13px; margin-bottom:10px; white-space:pre-wrap; }
  #aviso { position:fixed; left:50%; bottom:20px; transform:translateX(-50%); max-width:min(92vw,640px);
           background:var(--fg); color:var(--bg); padding:10px 16px; border-radius:8px;
           font-size:14px; display:none; }
  @media (max-width:760px) {
    .detalle { grid-template-columns:1fr; }
    .col-mini, th:nth-child(2) { display:none; }
    .acc .btn { display:block; margin:6px 0 0; text-align:center; }
  }
"""

# Sin plantillas de cadena: el JavaScript lleva llaves y comillas, y meterlo
# en un f-string obliga a doblarlas todas.
_GUION = r"""
  const aviso = document.getElementById("aviso");
  function avisar(texto) {
    aviso.textContent = texto; aviso.style.display = "block";
    clearTimeout(avisar.t); avisar.t = setTimeout(() => aviso.style.display = "none", 6000);
  }
  // Todo lo que escribió un modelo pasa por aquí: es dato, no HTML.
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const corto = (s, n = 110) => { s = String(s ?? "").replace(/\s+/g, " ").trim(); return s.length > n ? s.slice(0, n) + "…" : s; };
  const num = (v, d = 2) => v === null || v === undefined ? "—" : Number(v).toFixed(d);

  function pintarDetalle(d) {
    const gif = d.animacion
      ? `<img class="gif" src="/proyectos/${encodeURIComponent(d.id)}/animation.gif?t=${Date.now()}" alt="Animación del ciclo">`
      : d.vista && !d.es_mecanismo
      ? `<img class="gif" src="/proyectos/${encodeURIComponent(d.id)}/vista.png" alt="Las piezas">`
      : d.es_mecanismo
      ? `<div class="sin-gif">Todavía no hay animación.<br>Se genera al montar el mecanismo.</div>`
      : `<div class="sin-gif">Todavía no hay piezas construidas.</div>`;
    let req = "<p class='vacio'>Ninguna ronda ha medido requisitos todavía.</p>";
    if (d.requisitos) {
      const filas = d.requisitos.filas.map(f => {
        const estado = f.cumple === true ? "<span class='ok'>cumple</span>"
          : f.cumple === false ? "<span class='mal'>no cumple</span>"
          : `<span class='suave' title="${esc(f.nota)}">sin medir</span>`;
        return `<tr><td>${esc(f.descripcion)}</td><td class="num">${num(f.esperado)} ± ${num(f.tolerancia)}</td>
          <td class="num">${num(f.medido)}</td><td class="num">${f.desviacion === null ? "—" : (f.desviacion > 0 ? "+" : "") + num(f.desviacion)}</td><td>${estado}</td></tr>`;
      }).join("");
      req = `<table><thead><tr><th>Requisito</th><th class="num">Pedido</th><th class="num">Medido</th>
        <th class="num">Desviación</th><th></th></tr></thead><tbody>${filas}</tbody></table>
        <div class="det">Medidos por el código en la ronda ${d.requisitos.de_la_ronda}.${d.requisitos.provisional
          ? " <b class='ambar'>Provisional:</b> ninguna ronda ha llegado a barrer el recorrido completo, así que no está comprobado." : ""}</div>
        <div class="det">Los requisitos son solo una parte: para terminar, además, las piezas tienen que poder dibujarse,
          apoyarse, no chocar en todo el recorrido, seguir en contacto donde se declaró, y topes y bloqueos tienen que funcionar.</div>`;
    }
    const ultima = [...d.rondas].reverse().find(r => r.verificado) || {};
    let verif = "";
    if (ultima.verificado) {
      const v = ultima.verificado;
      verif = `<div class="det">Comprobado con la geometría real: ${v.contactos} contactos · ${v.topes} topes ·
        ${v.bloqueos} bloqueos · ${v.apoyos} apoyos por contacto.</div>`;
      if ((ultima.impuesto_por_formula || []).length)
        verif += `<div class="det ambar">Se mueve porque su fórmula lo dice (nadie comprueba que lo cause el mecanismo):
          ${ultima.impuesto_por_formula.map(esc).join(", ")}</div>`;
    }
    const ultimaRonda = d.rondas.length ? d.rondas[d.rondas.length - 1].ronda : null;
    const rondas = [...d.rondas].reverse().map(r => {
      let cuerpo = "";
      if (r.en_curso) cuerpo += `<div class="vivo">● en curso</div>`;
      // Los planes del modelo son largos: una línea y el resto al pulsar.
      if (r.plan) cuerpo += `<details class="plan"><summary><span class="etiqueta">Qué dijo que iba a cambiar</span>
        <span class="resumen">${esc(corto(r.plan.cambio))}</span></summary>
        <div class="etiqueta">Por qué</div><div>${esc(r.plan.causa)}</div>
        <div class="etiqueta">Qué cambia</div><div>${esc(r.plan.cambio)}</div>
        ${r.plan.espera ? `<div class="etiqueta">Qué espera que pase</div><div>${esc(r.plan.espera)}</div>` : ""}</details>`;
      if (r.barrido) cuerpo += `<div class="det">Barrido: ${r.barrido.posiciones} posiciones, ${r.barrido.choques} choques${
        r.barrido.peor_hueco_mm !== null && r.barrido.peor_hueco_mm !== undefined ? ` (peor hueco ${num(r.barrido.peor_hueco_mm)} mm)` : ""}.</div>`;
      (r.ajustes || []).forEach(a => cuerpo += `<div class="det">⚙ ${esc(a)}</div>`);
      if (r.rechazados) cuerpo += `<div class="det">${r.rechazados} propuestas rechazadas por el validador antes de esta.</div>`;
      if (r.sin_datos) cuerpo += `<div class="det">Sin datos de esta ronda: se hizo antes de que se guardaran.</div>`;
      else if (!r.en_curso) cuerpo += r.resuelta
        ? `<div class="ok">✓ sin fallos</div>`
        : `<details class="plan" ${r.ronda === ultimaRonda ? "open" : ""}><summary><span class="etiqueta">Lo que falló</span>
            <span class="resumen mal">${esc(corto(r.feedback))}</span></summary><pre>${esc(r.feedback)}</pre></details>`;
      return `<li><b>Ronda ${r.ronda}</b> <span class="suave">${esc(r.titulo)}</span>${cuerpo}</li>`;
    }).join("") || "<li class='vacio'>Este proyecto no guarda historia de rondas (es anterior a que existiera).</li>";
    // Lo que acompaña a las piezas: cómo usarlas, por qué se detuvo, el revisor.
    const docs = (d.documentos || []).map(x => `<h3>${esc(x.titulo)}</h3><div class="documento">${x.html}</div>`).join("");
    const pedido = (d.modificacion ? `<div class="pedido"><div class="etiqueta">Cambio pedido en esta versión</div>${esc(d.modificacion)}</div>` : "")
      + (d.peticion ? `<details class="plan"><summary><span class="etiqueta">Petición completa que recibió el diseñador</span></summary><pre>${esc(d.peticion)}</pre></details>` : "");
    // Cómo se lamina cada pieza: lo que no es «general» lleva más (o menos) material.
    const piezas = (d.piezas || []).length ? `<div class="det">Piezas: ${d.piezas.map(p =>
      esc(p.nombre) + (p.uso !== "general" ? ` <b>(${esc(p.uso)})</b>` : "")).join(", ")}</div>` : "";
    // Una pieza que no es un mecanismo no se diseñó por rondas ni mide
    // requisitos con la cinemática: esas secciones solo confundían.
    const diseno = d.es_mecanismo || d.rondas.length
      ? `<h3>Precisión: lo pedido frente a lo medido</h3>${req}<h3>Rondas</h3><ul class="rondas">${rondas}</ul>` : "";
    return `<div class="detalle"><div>${gif}${verif}${piezas}</div><div>${docs}${pedido}${diseno}</div></div>`;
  }

  // sessionStorage puede no estar (ventana privada estricta): sin él se
  // pierde qué tenías abierto al recargar, nada más.
  const leer = (k, d) => { try { return JSON.parse(sessionStorage.getItem(k)) ?? d; } catch (e) { return d; } };
  const guardar = (k, v) => { try { sessionStorage.setItem(k, JSON.stringify(v)); } catch (e) {} };
  const abiertos = new Set(leer("abiertos", []));
  const guardarAbiertos = () => guardar("abiertos", [...abiertos]);
  // La versión que elegiste en cada proyecto. Sin elegir, la mejor: la que
  // la página trae marcada.
  const elegidas = new Map(Object.entries(leer("elegidas", {})));
  const guardarElegidas = () => guardar("elegidas", Object.fromEntries(elegidas));
  const hayPuente = !!document.body.dataset.puente;
  const borradores = new Map();

  const filaDe = id => document.querySelector(`tr.fila[data-id="${CSS.escape(id)}"]`);
  const panelDe = id => document.querySelector(`tr[data-panel="${CSS.escape(id)}"]`);

  // Los botones de la fila bajan y abren la versión que estás viendo.
  function aplicarVersion(id) {
    const panel = panelDe(id), fila = filaDe(id);
    const sel = panel.querySelector("select[data-versiones]");
    if (elegidas.has(id) && [...sel.options].some(o => o.value === elegidas.get(id))) sel.value = elegidas.get(id);
    const opcion = sel.selectedOptions[0];
    const piezas = Number(opcion.dataset.piezas);
    fila.querySelector("a[data-zip]").href = "/proyectos/" + encodeURIComponent(sel.value) + ".zip";
    const b = fila.querySelector("button[data-abrir]");
    b.dataset.abrir = sel.value;
    b.disabled = !piezas || !hayPuente;
    b.title = !piezas ? "Sin piezas construidas" : !hayPuente ? "Arranca el puente en el PC primero"
      : `Abre las ${piezas} piezas de esta versión en tu PrusaSlicer con el perfil de la M5`;
    return sel.value;
  }

  async function abrirPanel(id) {
    const panel = panelDe(id);
    if (!panel) return;
    panel.hidden = false;
    const version = aplicarVersion(id);
    const caja = panel.querySelector(".contenido");
    if (!caja.innerHTML) caja.innerHTML = "<span class='suave'>Cargando…</span>";
    try {
      const r = await fetch("/api/proyectos/" + encodeURIComponent(version));
      caja.innerHTML = r.ok ? pintarDetalle(await r.json()) : "<span class='mal'>No se pudo cargar.</span>";
    } catch (e) { caja.innerHTML = "<span class='mal'>No se pudo cargar: " + esc(e) + "</span>"; }
  }

  function enganchar() {
    document.querySelectorAll("tr.fila").forEach(fila => fila.addEventListener("click", ev => {
      if (ev.target.closest("a, button")) return;
      const id = fila.dataset.id;
      const panel = panelDe(id);
      if (panel.hidden) { abiertos.add(id); abrirPanel(id); }
      else { abiertos.delete(id); panel.hidden = true; }
      guardarAbiertos();
    }));
    document.querySelectorAll("select[data-versiones]").forEach(sel => sel.addEventListener("change", () => {
      elegidas.set(sel.dataset.versiones, sel.value); guardarElegidas();
      abrirPanel(sel.dataset.versiones);
    }));
    document.querySelectorAll("button[data-lanzar]").forEach(b => b.addEventListener("click", async () => {
      const id = b.dataset.lanzar;
      const caja = document.querySelector(`textarea[data-modificar="${CSS.escape(id)}"]`);
      const base = panelDe(id).querySelector("select[data-versiones]").value;
      if (!caja.value.trim()) { avisar("Escribe primero qué quieres cambiar."); caja.focus(); return; }
      b.disabled = true; const antes = b.textContent; b.textContent = "Lanzando...";
      try {
        const r = await fetch("/api/proyectos/" + encodeURIComponent(base) + "/modificar", {method: "POST",
          headers: {"Content-Type": "application/json"}, body: JSON.stringify({peticion: caja.value})});
        const d = await r.json();
        if (r.ok) {
          caja.value = ""; borradores.delete(id);
          // Se queda mirando la versión nueva, que es la que está trabajando.
          elegidas.set(id, d.id); guardarElegidas();
          avisar("En marcha la versión nueva de este proyecto. Tarda unos minutos; se actualiza sola.");
          abiertos.add(id); guardarAbiertos();
          await refrescar(true);
        } else {
          avisar(Array.isArray(d.detail) ? d.detail.map(x => x.msg).join("; ") : d.detail);
          b.disabled = false;
        }
      } catch (e) { avisar("No se pudo contactar con el servidor: " + e); b.disabled = false; }
      b.textContent = antes;
    }));
    // Lo que tenías a medio escribir en un cuadro de modificación vuelve
    // tras cada refresco: el cuadro está dentro de lo que se reemplaza.
    document.querySelectorAll("textarea[data-modificar]").forEach(t => {
      if (borradores.has(t.dataset.modificar)) t.value = borradores.get(t.dataset.modificar);
      t.addEventListener("input", () => borradores.set(t.dataset.modificar, t.value));
    });
    document.querySelectorAll("button[data-abrir]").forEach(b => b.addEventListener("click", async () => {
      b.disabled = true; const antes = b.textContent; b.textContent = "Abriendo...";
      try {
        const r = await fetch("/proyectos/" + encodeURIComponent(b.dataset.abrir) + "/abrir", {method: "POST"});
        const d = await r.json();
        avisar(r.ok ? "PrusaSlicer abierto con " + d.abiertas + " piezas y el perfil " + d.perfil : d.detail);
      } catch (e) { avisar("No se pudo contactar con el servidor: " + e); }
      b.disabled = false; b.textContent = antes;
    }));
    abiertos.forEach(abrirPanel);
  }

  // Mientras algo trabaja, la página se pone al día sola. Se reemplaza el
  // contenido, no se recarga: así no se pierde lo que tienes abierto. Solo
  // #vivo: el formulario queda fuera para no borrar lo que estás escribiendo.
  const trabajando = () => !!document.querySelector('tr.fila[data-estado="en marcha"]');
  async function refrescar(forzar = false) {
    if (!forzar && !trabajando()) return;
    try {
      const html = await (await fetch("/")).text();
      const doc = new DOMParser().parseFromString(html, "text/html");
      const foco = document.activeElement?.dataset?.modificar;
      document.querySelector("#vivo").replaceWith(doc.querySelector("#vivo"));
      // El botón y la nota sí se ponen al día: dicen si se puede pedir ya.
      document.querySelector("#disenar").disabled = doc.querySelector("#disenar").disabled;
      document.querySelector("#nota-pedir").textContent = doc.querySelector("#nota-pedir").textContent;
      enganchar();
      if (foco) document.querySelector(`textarea[data-modificar="${CSS.escape(foco)}"]`)?.focus();
    } catch (e) { /* sin red un momento: se reintenta en la siguiente vuelta */ }
  }

  document.querySelector("#disenar").addEventListener("click", async () => {
    const caja = document.querySelector("#peticion");
    const b = document.querySelector("#disenar");
    if (!caja.value.trim()) { avisar("Escribe primero qué quieres que diseñe."); caja.focus(); return; }
    b.disabled = true; const antes = b.textContent; b.textContent = "Lanzando...";
    try {
      const r = await fetch("/api/disenar", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({peticion: caja.value, basado_en: document.querySelector("#basado_en").value || null})});
      const d = await r.json();
      if (r.ok) {
        caja.value = "";
        avisar("En marcha: " + d.id + ". Tarda unos minutos; la lista se actualiza sola.");
        await refrescar(true);
        abiertos.add(d.id); guardarAbiertos(); abrirPanel(d.id);
      } else {
        // Un 422 trae la lista de errores de validación, no una frase.
        avisar(Array.isArray(d.detail) ? d.detail.map(x => x.msg).join("; ") : d.detail);
        b.disabled = false;
      }
    } catch (e) { avisar("No se pudo contactar con el servidor: " + e); b.disabled = false; }
    b.textContent = antes;
  });
  enganchar();
  setInterval(refrescar, 15000);
"""


_EJEMPLO = (
    "Qué quieres que haga, con todo lo que sepas. Por ejemplo:\n\n"
    "Un trinquete con rueda de 12 dientes y 40 mm de diámetro que solo gire "
    "en un sentido. La palanca avanza la rueda un diente por pulsación.\n\n"
    "PIEZAS: cada una con sus medidas.\n"
    "MOVIMIENTO: qué se mueve, cuánto y con qué holgura.\n"
    "FABRICACIÓN: sin soportes, voladizos de 45° como mucho.\n"
    "PRIORIDAD: qué sacrificar si algo no se puede."
)


def _formulario(filas: list[dict], puede_pedir: bool, ocupado: bool) -> str:
    e = html.escape
    # Un diseño NUEVO que se inspira en otro proyecto, desde su mejor versión.
    # Cambiar ese mismo proyecto es una modificación, y se pide desde su panel.
    opciones = "".join(f'<option value="{e(f["mejor"])}">{e(_corto(f["titulo"], 70))}</option>'
                       for f in filas)
    desactivado = "" if puede_pedir and not ocupado else "disabled"
    nota = ("Esta web no tiene con qué lanzar diseños." if not puede_pedir else
            "Hay un proyecto trabajando: espera a que termine." if ocupado else
            "Tarda varios minutos y cuesta dinero (tope de 5 USD por proyecto). "
            "Lo verás aparecer abajo, en Proyectos.")
    return f"""
  <section class="pedir">
    <h2>Nuevo diseño</h2>
    <textarea id="peticion" rows="10" placeholder="{e(_EJEMPLO)}"></textarea>
    <div class="pie">
      <label>Partir de <select id="basado_en"><option value="">nada, empezar de cero</option>{opciones}</select></label>
      <button class="btn pri" id="disenar" {desactivado}>Diseñar</button>
    </div>
    <div class="det" id="nota-pedir">{e(nota)}</div>
  </section>"""


def _pagina(filas: list[dict], hay_puente: bool, puede_pedir: bool = False) -> str:
    activos = [f for f in filas if f["seccion"] == "projects"]
    archivados = [f for f in filas if f["seccion"] == "archivo"]
    en_marcha = sum(1 for f in activos if f.get("en_marcha"))
    puede_modificar = puede_pedir and not en_marcha
    puente = ('<span class="ok">● puente con PrusaSlicer configurado</span>' if hay_puente
              else '<span class="mal">● sin puente con PrusaSlicer — arráncalo en el PC: '
                   '<code>powershell scripts\\start-host-mcps.ps1</code></span>')
    marcha = (f'<span class="vivo">● {en_marcha} trabajando · se actualiza sola</span>'
              if en_marcha else "")
    return (
        '<!doctype html>\n<html lang="es"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>Intelliprint</title>\n<style>{_ESTILO}</style></head>\n"
        f'<body data-puente="{"1" if hay_puente else ""}"><main>\n  <h1>Intelliprint</h1>\n'
        f"{_formulario(filas, puede_pedir, ocupado=en_marcha > 0)}\n"
        # Lo que se refresca solo va aparte: si el formulario estuviera
        # dentro, cada vuelta borraría lo que estás escribiendo. Los cuadros
        # de modificación sí van dentro, y el guion guarda lo escrito.
        '  <div id="vivo">\n'
        f'  <div class="cabecera">{puente}{marcha}</div>\n'
        f"  <h2>Proyectos</h2>\n  {_tabla(activos, hay_puente, 'Todavía no hay proyectos.', puede_modificar)}\n"
        f"  <h2>Archivo</h2>\n  {_tabla(archivados, hay_puente, 'Nada archivado.', puede_modificar)}\n"
        f'  </div>\n</main>\n<div id="aviso"></div>\n<script>{_GUION}</script>\n</body></html>'
    )


def main() -> None:
    """Arranque dentro del contenedor."""
    import uvicorn

    workspace = Path(os.environ.get("INTELLIPRINT_WORKSPACE") or "workspace")
    app = crear_app(
        workspace,
        puente=os.environ.get("PRUSASLICER_BRIDGE") or None,
        host_workspace=os.environ.get("HOST_WORKSPACE", ""),
        # La misma orden que lanza Crafty (mcp_server._store).
        trabajos=JobStore(workspace / "projects", ["intelliprint", "mecanismo"]),
    )
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("WEB_PORT", "8080")))


if __name__ == "__main__":
    main()
