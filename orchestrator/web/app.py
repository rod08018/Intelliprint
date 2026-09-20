"""Interfaz web: ver los proyectos, bajarlos en zip y abrirlos en
PrusaSlicer (F5.5 (web)).

Corre dentro del contenedor y se abre desde el navegador del PC. Es el
subconjunto de F5.5 (web) que hacía falta ya —encontrar un proyecto, llevárselo,
mirarlo en PrusaSlicer—; los botones de los gates llegan con ellos.

El identificador de un proyecto viene de la URL, es decir, lo escribe
quien quiera. Se trata como texto ajeno: un nombre, nunca una ruta.

    docker compose up -d web      ->  http://localhost:8080
"""

import html
import io
import os
import zipfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response

from orchestrator.hostpaths import RutaFueraDelWorkspace, a_ruta_del_host
from orchestrator.registry import indice

SECCIONES = ("projects", "archivo")
"""Dónde buscar. `archivo/` también: archivar no es borrar, y un intento
fallido es la única prueba de por qué algo no funcionó."""

PERFIL = "ankermake_m5_petg.ini"


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


def _listar(workspace: Path) -> list[dict]:
    filas = []
    for seccion in SECCIONES:
        carpeta = Path(workspace) / seccion
        if not carpeta.is_dir():
            continue
        for fila in indice(carpeta):
            fila = {k: v for k, v in fila.items() if k != "carpeta"}
            fila["seccion"] = seccion
            fila["piezas"] = len(piezas_de(carpeta / fila["id"]))
            filas.append(fila)
    return filas


def crear_app(workspace: Path, puente=None, host_workspace: str = "") -> FastAPI:
    """La aplicación. `puente` es la URL del MCP del host, o en los tests el
    propio servidor; None si no hay puente configurado."""
    app = FastAPI(title="Intelliprint", docs_url=None, redoc_url=None)
    workspace = Path(workspace)

    def _proyecto(id: str) -> Path:
        try:
            return resolver_proyecto(id, workspace)
        except ProyectoDesconocido:
            raise HTTPException(404, f"no hay ningún proyecto llamado {id!r}")

    @app.get("/api/proyectos")
    def proyectos() -> list[dict]:
        return _listar(workspace)

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
        try:
            stls = [a_ruta_del_host(p.as_posix(), workspace.as_posix(), host_workspace)
                    for p in piezas]
        except RutaFueraDelWorkspace as e:
            raise HTTPException(500, str(e))
        try:
            respuesta = ClienteMCP(puente, timeout=60).llamar(
                "abrir_en_prusaslicer", stls=stls, perfil=PERFIL)
        except PuenteInalcanzable as e:
            raise HTTPException(
                503, f"el puente del PC no contesta ({e}). ¿Está arrancado? "
                "powershell scripts\\start-host-mcps.ps1")
        except LlamadaFallida as e:
            raise HTTPException(502, str(e))
        if not respuesta.get("ok"):
            raise HTTPException(502, respuesta.get("error") or "PrusaSlicer no se abrió")
        return respuesta

    @app.get("/", response_class=HTMLResponse)
    def portada() -> str:
        return _pagina(_listar(workspace), hay_puente=puente is not None)

    return app


# --- La página ---------------------------------------------------------------

ICONOS = {"aprobado": "✅", "antiguo": "📦", "fallido": "❌",
          "en marcha": "⏳", "incompleto": "⚠️"}


def _fila(f: dict, hay_puente: bool) -> str:
    e = html.escape
    id_ = e(f["id"])
    detalle = e(f.get("motivo") or f.get("peticion") or f.get("titulo") or "")
    sin_piezas = f["piezas"] == 0
    abrir_titulo = ("Sin piezas construidas" if sin_piezas else
                    "Arranca el puente en el PC primero" if not hay_puente else
                    f"Abre las {f['piezas']} piezas en tu PrusaSlicer con el perfil de la M5")
    desactivado = "disabled" if sin_piezas or not hay_puente else ""
    return f"""
      <tr>
        <td class="estado" title="{e(f['estado'])}">{ICONOS.get(f['estado'], '·')}</td>
        <td><div class="id">{id_}</div><div class="det">{detalle}</div></td>
        <td class="num">{f['piezas']}</td>
        <td class="num">{f['rondas']}</td>
        <td class="num">{f['usd']:.2f}</td>
        <td class="acc">
          <a class="btn" href="/proyectos/{id_}.zip" download>Descargar .zip</a>
          <button class="btn pri" data-id="{id_}" title="{e(abrir_titulo)}" {desactivado}>Slice in PrusaSlicer</button>
        </td>
      </tr>"""


def _tabla(filas: list[dict], hay_puente: bool, vacio: str) -> str:
    if not filas:
        return f'<p class="vacio">{vacio}</p>'
    cuerpo = "".join(_fila(f, hay_puente) for f in filas)
    return f"""
    <div class="marco"><table>
      <thead><tr><th></th><th>Proyecto</th><th class="num">Piezas</th>
        <th class="num">Rondas</th><th class="num">USD</th><th></th></tr></thead>
      <tbody>{cuerpo}</tbody>
    </table></div>"""


_ESTILO = """
  :root { --bg:#f7f7f5; --fg:#1d1d1b; --suave:#6b6b66; --linea:#e2e2dd;
          --tarjeta:#fff; --acento:#2f5d8a; --acento-fg:#fff; --ok:#2e7d4f; --mal:#a3432b; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#161615; --fg:#ececea; --suave:#9a9a94; --linea:#2c2c2a;
            --tarjeta:#1f1f1e; --acento:#6b9bd1; --acento-fg:#0e1620; --ok:#6cc08b; --mal:#e08a70; }
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--fg);
         font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; }
  main { max-width:1100px; margin:0 auto; padding:28px 16px 60px; }
  h1 { font-size:22px; margin:0 0 4px; }
  h2 { font-size:13px; margin:32px 0 10px; color:var(--suave); font-weight:600;
       text-transform:uppercase; letter-spacing:.05em; }
  .puente { font-size:13px; margin-bottom:8px; }
  .ok { color:var(--ok); } .mal { color:var(--mal); }
  code { font-size:12px; background:var(--linea); padding:1px 5px; border-radius:4px; }
  .marco { overflow-x:auto; background:var(--tarjeta); border:1px solid var(--linea); border-radius:10px; }
  table { width:100%; border-collapse:collapse; }
  th, td { padding:10px 12px; text-align:left; border-bottom:1px solid var(--linea); vertical-align:top; }
  tr:last-child td { border-bottom:0; }
  th { font-size:12px; color:var(--suave); font-weight:600; }
  .num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
  .estado { width:28px; }
  .id { font-weight:600; word-break:break-all; }
  .det { font-size:13px; color:var(--suave); margin-top:2px; }
  .acc { white-space:nowrap; text-align:right; }
  .btn { display:inline-block; font:inherit; font-size:13px; padding:6px 11px; margin-left:6px;
         border-radius:7px; border:1px solid var(--linea); background:var(--tarjeta);
         color:var(--fg); text-decoration:none; cursor:pointer; }
  .btn:hover { border-color:var(--suave); }
  .btn.pri { background:var(--acento); color:var(--acento-fg); border-color:var(--acento); }
  .btn:disabled { opacity:.4; cursor:not-allowed; }
  .vacio { color:var(--suave); }
  #aviso { position:fixed; left:50%; bottom:20px; transform:translateX(-50%); max-width:min(92vw,640px);
           background:var(--fg); color:var(--bg); padding:10px 16px; border-radius:8px;
           font-size:14px; display:none; }
  @media (max-width:640px) { .acc .btn { display:block; margin:6px 0 0; text-align:center; } }
"""

# Sin plantillas de cadena: el JavaScript lleva llaves y comillas, y
# meterlo en un f-string obliga a doblarlas todas.
_GUION = """
  const aviso = document.getElementById("aviso");
  function avisar(texto) {
    aviso.textContent = texto; aviso.style.display = "block";
    clearTimeout(avisar.t); avisar.t = setTimeout(() => aviso.style.display = "none", 6000);
  }
  document.querySelectorAll("button[data-id]").forEach(b => b.addEventListener("click", async () => {
    b.disabled = true; const antes = b.textContent; b.textContent = "Abriendo...";
    try {
      const r = await fetch("/proyectos/" + encodeURIComponent(b.dataset.id) + "/abrir", {method: "POST"});
      const d = await r.json();
      avisar(r.ok ? "PrusaSlicer abierto con " + d.abiertas + " piezas y el perfil " + d.perfil : d.detail);
    } catch (e) { avisar("No se pudo contactar con el servidor: " + e); }
    b.disabled = false; b.textContent = antes;
  }));
"""


def _pagina(filas: list[dict], hay_puente: bool) -> str:
    activos = [f for f in filas if f["seccion"] == "projects"]
    archivados = [f for f in filas if f["seccion"] == "archivo"]
    puente = ('<span class="ok">● puente con PrusaSlicer configurado</span>' if hay_puente
              else '<span class="mal">● sin puente con PrusaSlicer — arráncalo en el PC: '
                   '<code>powershell scripts\\start-host-mcps.ps1</code></span>')
    return (
        '<!doctype html>\n<html lang="es"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>Intelliprint</title>\n<style>{_ESTILO}</style></head>\n"
        "<body><main>\n  <h1>Intelliprint</h1>\n"
        f'  <div class="puente">{puente}</div>\n'
        f"  <h2>Proyectos</h2>\n  {_tabla(activos, hay_puente, 'Todavía no hay proyectos.')}\n"
        f"  <h2>Archivo</h2>\n  {_tabla(archivados, hay_puente, 'Nada archivado.')}\n"
        f'</main>\n<div id="aviso"></div>\n<script>{_GUION}</script>\n</body></html>'
    )


def main() -> None:
    """Arranque dentro del contenedor."""
    import uvicorn

    workspace = Path(os.environ.get("INTELLIPRINT_WORKSPACE") or "workspace")
    app = crear_app(
        workspace,
        puente=os.environ.get("PRUSASLICER_BRIDGE") or None,
        host_workspace=os.environ.get("HOST_WORKSPACE", ""),
    )
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("WEB_PORT", "8080")))


if __name__ == "__main__":
    main()
