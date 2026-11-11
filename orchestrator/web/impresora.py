"""La página «Impresora»: lo que el usuario midió, con sus fotos (F2.21 (impresora)).

El usuario configura y calibra su impresora él mismo y quiere que lo medido
entre en el diseño (2026-11-09). Aquí ve con qué valores se diseña, de dónde
sale cada uno (medido, con fecha y foto, o el valor por defecto sin medir) y
apunta medidas nuevas.

Las fotos llegan en base64 dentro de un JSON y no como formulario: así no
hace falta `python-multipart` en la imagen. Su nombre lo pone el servidor
(`medidas_impresora.registrar`); el del navegador es texto ajeno.
"""

import base64
import binascii
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from orchestrator.calibracion import BARRA, HOLGURAS_MM, M3_INSERTO_MM, M3_ROSCA_Y_PASANTE_MM
from orchestrator.impresion import perfil_activo
from orchestrator.medidas_impresora import (
    MAX_FOTOS, MedidaInvalida, carpeta, registrar, registros)
from orchestrator.web.paginas import _documento, e

# Lo que el diseño usa y la persona puede medir: (clave en el perfil, nombre, unidad).
VALORES = [
    ("fits.press_mm", "Holgura a presión", "mm"),
    ("fits.slide_mm", "Holgura deslizante", "mm"),
    ("fits.clearance_mm", "Holgura para girar libre", "mm"),
    ("holes.M3_through_mm", "Agujero M3 pasante", "mm"),
    ("holes.M3_selftap_mm", "Agujero M3 de rosca directa", "mm"),
    ("holes.M3_insert_mm", "Agujero del inserto M3", "mm"),
    ("resistencia.xy_MPa", "Resistencia a lo largo del filamento", "MPa"),
    ("resistencia.z_MPa", "Resistencia entre capas", "MPa"),
]


class Foto(BaseModel):
    nombre: str = Field(max_length=200)
    datos: str
    """El archivo en base64."""


class Medida(BaseModel):
    tipo: str
    valores: dict
    nota: str = Field(default="", max_length=1000)
    fotos: list[Foto] = Field(default=[], max_length=MAX_FOTOS)


def _valor(datos: dict, clave: str):
    seccion, nombre = clave.split(".")
    return (datos.get(seccion) or {}).get(nombre)


def _cifra(valor, unidad: str) -> str:
    if valor is None:
        return "—"
    return f"{valor:.2f} mm" if unidad == "mm" else f"{valor:.1f} MPa"


def _miniaturas(r: dict) -> str:
    return "".join(f'<a href="/impresora/fotos/{e(f)}" target="_blank"><img src="/impresora/fotos/{e(f)}" '
                   f'alt="Foto de la medida del {e(r["fecha"])}" loading="lazy"></a>' for f in r["fotos"])


def _resumen(r: dict) -> str:
    v = r["valores"]
    if r["tipo"] == "tolerancias":
        return (f"Holguras: presión {v['press_mm']:.2f}, deslizante {v['slide_mm']:.2f}, "
                f"libre {v['clearance_mm']:.2f}. M3: pasante {v['m3_through_mm']:.2f}, "
                f"rosca {v['m3_selftap_mm']:.2f}, inserto {v['m3_insert_mm']:.2f}")
    if r["tipo"] == "resistencia":
        como = "tumbada" if v["orientacion"] == "xy" else "de pie"
        return f"Barra {como}: rompió con {v['carga_kg']:g} kg → {v['MPa']:.1f} MPa"
    return f"Prueba tuya: {v['titulo']}"


def _opciones(nombre: str, valores, seleccion: float | None, formato: str) -> str:
    """Si el valor de ahora no es ninguna opción de la pieza, no se elige
    ninguna: con 0.35 de holgura libre se enseñaba +0.0, la primera, y se
    podía guardar sin haberla elegido."""
    hay = seleccion is not None and any(abs(v - seleccion) < 1e-9 for v in valores)
    opciones = "".join(
        f'<option value="{v:.2f}"{" selected" if hay and abs(v - seleccion) < 1e-9 else ""}>'
        f'{formato.format(v)}</option>' for v in valores)
    vacia = "" if hay else '<option value="" selected disabled>elige</option>'
    return f'<select name="{nombre}" required>{vacia}{opciones}</select>'


def pagina(workspace: Path, raiz: Path) -> str:
    activo = perfil_activo(raiz, workspace=workspace)
    perfil = activo.impresora.id
    filas = []
    for clave, nombre, unidad in VALORES:
        r = activo.medido.get(clave)
        origen = (f'<span class="ok">medido el {e(r["fecha"])}</span>' if r else
                  '<span class="suave">sin medir: valor por defecto</span>')
        filas.append(f"<tr><td>{e(nombre)}</td><td><b>{_cifra(_valor(activo.datos, clave), unidad)}"
                     f"</b></td><td>{origen}</td></tr>")
    calibrado = ('<span class="ok">● Holguras medidas por ti</span>' if activo.impresora.calibrated
                 else '<span class="mal">● Holguras sin medir</span>')

    def fila_holgura(nombre: str, etiqueta: str, defecto) -> str:
        return f'<label>{etiqueta} {_opciones(nombre, HOLGURAS_MM, defecto, "+{:.1f} mm")}</label>'

    def apunte(r: dict) -> str:
        nota_r = f'<div class="nota">{e(r["nota"])}</div>' if r.get("nota") else ""
        return (f'<li><div><b>{e(r["fecha"])}</b> · {e(_resumen(r))}{nota_r}</div>'
                f'<div class="fotos">{_miniaturas(r)}</div></li>')

    datos = activo.datos
    historial = ("".join(apunte(r) for r in reversed(registros(workspace, perfil)))
                 or '<li class="suave">Aún no has apuntado nada.</li>')
    fotos = ('<label>Fotos <input type="file" name="fotos" accept="image/jpeg,image/png,image/webp" '
             f'multiple></label><span class="nota">Hasta {MAX_FOTOS}, de 10 MB como mucho.</span>')
    nota = '<label>Nota <textarea name="nota" rows="2" placeholder="Lo que quieras recordar"></textarea></label>'

    cuerpo = f"""
  <header class="barra"><a class="volver" href="/">← Inventos</a></header>
  <main class="impresora">
    <h1>Impresora</h1>
    <p><b>{e(perfil)}</b> · {e(activo.material)} · {calibrado}</p>
    <p class="nota">Con estos valores se diseña. Lo que mides aquí manda sobre el perfil de
      <code>config/printers/</code>, que no se toca.</p>
    <table class="valores"><thead><tr><th>Qué</th><th>Valor</th><th>De dónde sale</th></tr></thead>
      <tbody>{"".join(filas)}</tbody></table>

    <section>
      <h2>Apuntar holguras</h2>
      <p class="nota">Con la pieza de calibración: <code>intelliprint calibrar pieza</code>.
        Prueba el eje de 5 mm en cada agujero del peine y los tornillos en la placa M3.
        Cada valor es el primero que cumple.</p>
      <form class="medida" data-tipo="tolerancias">
        {fila_holgura("press_mm", "A presión (entra empujando y se queda)", _valor(datos, "fits.press_mm"))}
        {fila_holgura("slide_mm", "Deslizante (entra y gira con poco juego)", _valor(datos, "fits.slide_mm"))}
        {fila_holgura("clearance_mm", "Gira libre (como un pivote)", _valor(datos, "fits.clearance_mm"))}
        <label>M3 pasante (pasa sin tocar) {_opciones("m3_through_mm", M3_ROSCA_Y_PASANTE_MM, _valor(datos, "holes.M3_through_mm"), "Ø {:.1f}")}</label>
        <label>M3 rosca directa (rosca firme sin partir) {_opciones("m3_selftap_mm", M3_ROSCA_Y_PASANTE_MM, _valor(datos, "holes.M3_selftap_mm"), "Ø {:.1f}")}</label>
        <label>Inserto M3 (recto, sin grietas ni girar) {_opciones("m3_insert_mm", M3_INSERTO_MM, _valor(datos, "holes.M3_insert_mm"), "Ø {:.1f}")}</label>
        {fotos}{nota}
        <button class="btn pri">Guardar holguras</button>
      </form>
    </section>

    <section>
      <h2>Apuntar resistencia</h2>
      <p class="nota">Con las barras de flexión: <code>intelliprint calibrar barra</code>. Sujeta el bloque
        al borde de la mesa, cuelga un cubo del agujero (a {BARRA['brazo_mm']:g} mm) y échale agua
        hasta que la barra rompa. Pesa el cubo con lo que tenía.</p>
      <form class="medida" data-tipo="resistencia">
        <label>Barra <select name="orientacion"><option value="xy">tumbada (a lo largo del filamento)</option>
          <option value="z">de pie (entre capas)</option></select></label>
        <label>Rompió con <input type="number" name="carga_kg" min="0.01" step="0.01" required> kg</label>
        {fotos}{nota}
        <button class="btn pri">Guardar resistencia</button>
      </form>
    </section>

    <section>
      <h2>Guardar una prueba tuya</h2>
      <p class="nota">Una prueba de Printables o tuya (voladizos, puentes, estrés…). Se guarda con la
        foto como referencia; no cambia ningún valor del diseño.</p>
      <form class="medida" data-tipo="referencia">
        <label>Qué prueba es <input type="text" name="titulo" maxlength="120" required
          placeholder="Torre de voladizos de Printables"></label>
        {fotos}{nota}
        <button class="btn pri">Guardar prueba</button>
      </form>
    </section>

    <section>
      <h2>Historial</h2>
      <ul class="historial">{historial}</ul>
    </section>
  </main>"""
    return _documento("Impresora · Intelliprint", cuerpo + f"<style>{ESTILO}</style>", GUION)


def rutas(app: FastAPI, workspace: Path, raiz: Path) -> None:
    workspace = Path(workspace)

    def _perfil() -> str:
        return perfil_activo(raiz).impresora.id

    @app.get("/impresora", response_class=HTMLResponse)
    def ver() -> str:
        return pagina(workspace, raiz)

    @app.post("/api/impresora/medidas")
    def apuntar(medida: Medida) -> dict:
        fotos = []
        for f in medida.fotos:
            try:
                fotos.append((f.nombre, base64.b64decode(f.datos, validate=True)))
            except (binascii.Error, ValueError):
                raise HTTPException(422, f"la foto {f.nombre!r} no llegó entera")
        try:
            r = registrar(workspace, _perfil(), medida.tipo, medida.valores, fotos,
                          nota=medida.nota)
        except MedidaInvalida as ex:
            raise HTTPException(422, str(ex))
        return {"ok": True, "registro": r}

    @app.get("/impresora/fotos/{nombre}")
    def foto(nombre: str) -> FileResponse:
        # Solo nombres como los que pone `registrar`: nunca una ruta.
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}-\d{3}-\d+\.(jpg|png|webp)", nombre):
            raise HTTPException(404, "no hay ninguna foto con ese nombre")
        ruta = carpeta(workspace, _perfil()) / "fotos" / nombre
        if not ruta.is_file():
            raise HTTPException(404, "no hay ninguna foto con ese nombre")
        return FileResponse(ruta)


ESTILO = """
  .impresora { max-width:900px; margin:0 auto; padding:16px; }
  .impresora h1 { font-size:28px; margin:10px 0 4px; }
  .impresora section { margin-top:28px; }
  .valores { width:100%; border-collapse:collapse; margin-top:10px; }
  .valores th, .valores td { text-align:left; padding:7px 8px; border-bottom:1px solid var(--linea); }
  .valores th { font-size:13px; color:var(--suave); font-weight:500; }
  .medida { display:grid; gap:10px; background:var(--tarjeta); border:1px solid var(--linea);
            border-radius:12px; padding:14px; }
  .medida label { display:flex; flex-wrap:wrap; align-items:center; gap:8px; }
  .medida input[type=text], .medida input[type=number] { font:inherit; padding:7px 9px; border-radius:8px;
            border:1px solid var(--linea); background:var(--bg); color:var(--fg); }
  .medida input[type=text] { flex:1; min-width:200px; }
  .medida textarea { width:100%; font:inherit; padding:8px 10px; border-radius:9px; border:1px solid var(--linea);
            background:var(--bg); color:var(--fg); }
  .medida .btn { justify-self:start; }
  .historial { list-style:none; padding:0; margin:0; display:grid; gap:10px; }
  .historial li { display:flex; flex-wrap:wrap; justify-content:space-between; gap:10px; padding:10px 0;
            border-bottom:1px solid var(--linea); }
  .historial .fotos { display:flex; gap:6px; flex-wrap:wrap; }
  .historial img { width:72px; height:72px; object-fit:cover; border-radius:8px; border:1px solid var(--linea); }
  @media (max-width: 600px) { .valores td:nth-child(3) { font-size:13px; } }
"""

GUION = r"""
  const leer = f => new Promise((ok, mal) => {
    const r = new FileReader();
    r.onload = () => ok({nombre: f.name, datos: String(r.result).split(",")[1]});
    r.onerror = () => mal(r.error);
    r.readAsDataURL(f);
  });
  document.querySelectorAll("form.medida").forEach(form => form.addEventListener("submit", async ev => {
    ev.preventDefault();
    const boton = form.querySelector("button");
    boton.disabled = true;
    try {
      const valores = {};
      form.querySelectorAll("select, input:not([type=file])").forEach(c => { valores[c.name] = c.value; });
      const fotos = await Promise.all([...form.querySelector("input[type=file]").files].map(leer));
      const [ok, d] = await enviar("/api/impresora/medidas", {
        tipo: form.dataset.tipo, valores, fotos, nota: form.querySelector("textarea").value});
      if (!ok) { avisar("No se guardó: " + detalle(d)); return; }
      location.reload();
    } catch (err) {
      avisar("No se pudo leer una foto: " + err);
    } finally {
      boton.disabled = false;
    }
  }));
"""
