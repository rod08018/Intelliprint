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
from fastapi.responses import FileResponse, HTMLResponse, Response

from orchestrator.hostpaths import RutaFueraDelWorkspace, a_ruta_del_host
from orchestrator.registry import estado_de, indice
from orchestrator.web.estadisticas import estadisticas

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

    @app.get("/api/proyectos/{id}")
    def detalle(id: str) -> dict:
        carpeta = _proyecto(id)
        en_marcha = estado_de(carpeta)["estado"] == "en marcha"
        return {"id": carpeta.name, **estadisticas(carpeta, en_marcha=en_marcha)}

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
#
# Lo que se enseña de cada proyecto es aritmética del código —rondas, coste,
# requisitos medidos contra lo pedido— más el informe del revisor, que se
# cuenta aparte y nunca como aprobación (ADR-003). Todo el texto que escribió
# un modelo (títulos, planes, motivos) se escapa: es dato, no HTML.

ICONOS = {"aprobado": "✅", "antiguo": "📦", "fallido": "❌",
          "en marcha": "⏳", "incompleto": "⚠️"}


def _requisitos_celda(r: dict | None) -> str:
    if not r:
        return '<span class="suave">—</span>'
    clase = "ok" if r["cumplen"] == r["total"] else ("mal" if r["cumplen"] == 0 else "ambar")
    titulo = f"medidos en la ronda {r['de_la_ronda']}"
    if r.get("sin_medir"):
        titulo += f"; {r['sin_medir']} sin poder medir"
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


def _fila(f: dict, hay_puente: bool) -> str:
    e = html.escape
    id_ = e(f["id"])
    detalle = e(f.get("motivo") or f.get("peticion") or f.get("titulo") or "")
    sin_piezas = f["piezas"] == 0
    abrir_titulo = ("Sin piezas construidas" if sin_piezas else
                    "Arranca el puente en el PC primero" if not hay_puente else
                    f"Abre las {f['piezas']} piezas en tu PrusaSlicer con el perfil de la M5")
    desactivado = "disabled" if sin_piezas or not hay_puente else ""
    ronda = f.get("ronda") or 0
    linea = f"ronda {ronda} · {f['piezas']} piezas" if ronda else f"{f['piezas']} piezas"
    vivo = ""
    if f["estado"] == "en marcha":
        que = e(f.get("ultima_etapa") or "arrancando")
        colgado = " · lleva un rato sin moverse" if f.get("parece_colgado") else ""
        vivo = f'<div class="vivo">● {que}{colgado}</div>'
    miniatura = (f'<img class="mini" src="/proyectos/{id_}/animation.gif" alt="" loading="lazy">'
                 if f.get("animacion") else '<div class="mini vacia"></div>')
    return f"""
      <tr class="fila" data-id="{id_}" data-estado="{e(f['estado'])}">
        <td class="estado" title="{e(f['estado'])}">{ICONOS.get(f['estado'], '·')}</td>
        <td class="col-mini">{miniatura}</td>
        <td><div class="id">{id_}</div><div class="det">{detalle}</div>
            <div class="det">{linea}</div>{vivo}</td>
        <td class="num">{_requisitos_celda(f.get("requisitos"))}</td>
        <td class="num rev">{_revisor_celda(f.get("revisor"))}</td>
        <td class="coste">{_coste_celda(f.get("coste"))}</td>
        <td class="acc">
          <a class="btn" href="/proyectos/{id_}.zip" download>Descargar .zip</a>
          <button class="btn pri" data-abrir="{id_}" title="{e(abrir_titulo)}" {desactivado}>Slice in PrusaSlicer</button>
        </td>
      </tr>
      <tr class="panel" data-panel="{id_}" hidden><td colspan="7"><div class="contenido"></div></td></tr>"""


def _tabla(filas: list[dict], hay_puente: bool, vacio: str) -> str:
    if not filas:
        return f'<p class="vacio">{vacio}</p>'
    cuerpo = "".join(_fila(f, hay_puente) for f in filas)
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
  .id { font-weight:600; word-break:break-all; }
  .det { font-size:13px; color:var(--suave); margin-top:2px; }
  .vivo { font-size:13px; color:var(--acento); margin-top:4px; }
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
_GUION = """
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
      : `<div class="sin-gif">Todavía no hay animación.<br>Se genera al montar el mecanismo.</div>`;
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
        <div class="det">Medidos por el código en la ronda ${d.requisitos.de_la_ronda}.</div>`;
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
    return `<div class="detalle"><div>${gif}${verif}</div><div>
      <h3>Precisión: lo pedido frente a lo medido</h3>${req}
      <h3>Rondas</h3><ul class="rondas">${rondas}</ul></div></div>`;
  }

  const abiertos = new Set(JSON.parse(sessionStorage.getItem("abiertos") || "[]"));
  const guardarAbiertos = () => sessionStorage.setItem("abiertos", JSON.stringify([...abiertos]));

  async function abrirPanel(id) {
    const panel = document.querySelector(`tr[data-panel="${CSS.escape(id)}"]`);
    if (!panel) return;
    panel.hidden = false;
    const caja = panel.querySelector(".contenido");
    if (!caja.innerHTML) caja.innerHTML = "<span class='suave'>Cargando…</span>";
    try {
      const r = await fetch("/api/proyectos/" + encodeURIComponent(id));
      caja.innerHTML = r.ok ? pintarDetalle(await r.json()) : "<span class='mal'>No se pudo cargar.</span>";
    } catch (e) { caja.innerHTML = "<span class='mal'>No se pudo cargar: " + esc(e) + "</span>"; }
  }

  function enganchar() {
    document.querySelectorAll("tr.fila").forEach(fila => fila.addEventListener("click", ev => {
      if (ev.target.closest("a, button")) return;
      const id = fila.dataset.id;
      const panel = document.querySelector(`tr[data-panel="${CSS.escape(id)}"]`);
      if (panel.hidden) { abiertos.add(id); abrirPanel(id); }
      else { abiertos.delete(id); panel.hidden = true; }
      guardarAbiertos();
    }));
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
  // contenido, no se recarga: así no se pierde lo que tienes abierto.
  async function refrescar() {
    if (!document.querySelector('tr.fila[data-estado="en marcha"]')) return;
    try {
      const html = await (await fetch("/")).text();
      const nuevo = new DOMParser().parseFromString(html, "text/html").querySelector("main");
      document.querySelector("main").replaceWith(nuevo);
      enganchar();
    } catch (e) { /* sin red un momento: se reintenta en la siguiente vuelta */ }
  }
  enganchar();
  setInterval(refrescar, 15000);
"""


def _pagina(filas: list[dict], hay_puente: bool) -> str:
    activos = [f for f in filas if f["seccion"] == "projects"]
    archivados = [f for f in filas if f["seccion"] == "archivo"]
    en_marcha = sum(1 for f in activos if f["estado"] == "en marcha")
    puente = ('<span class="ok">● puente con PrusaSlicer configurado</span>' if hay_puente
              else '<span class="mal">● sin puente con PrusaSlicer — arráncalo en el PC: '
                   '<code>powershell scripts\\start-host-mcps.ps1</code></span>')
    marcha = (f'<span class="vivo">● {en_marcha} trabajando · se actualiza sola</span>'
              if en_marcha else "")
    return (
        '<!doctype html>\n<html lang="es"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>Intelliprint</title>\n<style>{_ESTILO}</style></head>\n"
        "<body><main>\n  <h1>Intelliprint</h1>\n"
        f'  <div class="cabecera">{puente}{marcha}</div>\n'
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
