"""La página de un proyecto, revisada con heurísticas de usabilidad (F5.5 (web)).

Del análisis de UX del 2026-11-08 sobre el workspace real. El usuario quiere
la web para prototipar robots con rapidez (va a montar una empresa de
robótica infantil), así que cuenta lo que hace falta para pasar de una idea
a una pieza impresa sin dudar:

- Lo que se va a gastar al imprimir no salía en ningún sitio, aunque el
  laminado lo calcula: gramos, horas y si lleva soportes.
- Lo aprobado desaparecía al aprobarlo, y es contra lo que se juzga la pieza.
- «Imprimir en PrusaSlicer» no imprime: abre PrusaSlicer en el PC. Desde el
  móvil se entiende otra cosa.
- Mientras se diseñaba, «Descargar» bajaba un zip a medias de 7 KB, y no se
  veía cuánto llevaba.
- El diálogo «Nuevo diseño» ponía de ejemplo un sargento (un mecanismo) con
  «una pieza» elegida, y su cuadro de texto no tenía etiqueta.
- Las piezas se llamaban como su carpeta: «soporte_de_rodamiento_608zz_p».
- En el móvil, «← Proyectos» medía 23 px de alto.

Lo esperado sale de cómo se construye cada carpeta, no de lo que pinte la web.
"""

import datetime as dt
import json
import re

import yaml

from orchestrator.web.paginas import ESTILO
from tests.test_web_galeria import _con_trabajos, _web
from tests.test_web_piezas_sueltas import _pieza

IDEA = "Placa de 60 × 60 × 6 con el taladro central en lágrima"


def _con_laminado(carpeta, gramos=12.3, segundos=4980, soportes=False):
    (carpeta / "fabrication").mkdir(exist_ok=True)
    (carpeta / "fabrication" / "slicing_report.json").write_text(json.dumps(
        {"plate": 1, "filament_mm": 4100, "grams": gramos, "time_s": segundos,
         "needs_supports": soportes}), encoding="utf-8")
    (carpeta / "pieza_report.json").write_text(json.dumps(
        {"titulo": "t", "resuelto": True, "bbox_mm": [60, 50.04, 10], "gramos": gramos}),
        encoding="utf-8")


def _con_concepto(carpeta):
    (carpeta / "concepto.json").write_text(json.dumps(
        {"concepto": {"idea": IDEA, "orientacion": "tumbada"}}), encoding="utf-8")
    (carpeta / "spec.yaml").write_text(yaml.safe_dump({"requisitos": [
        {"id": "R1", "texto": "placa de 60 mm", "valor": 60, "unidad": "mm",
         "origen": "usuario"}]}, allow_unicode=True), encoding="utf-8")


# --- Lo que cuesta imprimirla ---------------------------------------------------


def test_la_pieza_dice_lo_que_cuesta_imprimirla(tmp_path):
    _con_laminado(_pieza(tmp_path, "2026-11-06-soporte"))

    html = _web(tmp_path).get("/p/2026-11-06-soporte").text

    # 4980 s son 1 h 23 min; la caja, redondeada al milímetro.
    for dato in ("12 g", "1 h 23 min", "sin soportes", "60 × 50 × 10 mm"):
        assert dato in html, dato


def test_si_lleva_soportes_lo_avisa(tmp_path):
    _con_laminado(_pieza(tmp_path, "2026-11-06-soporte"), segundos=1500, soportes=True)

    html = _web(tmp_path).get("/p/2026-11-06-soporte").text

    assert "con soportes" in html
    assert "25 min" in html


def test_sin_laminado_no_se_inventa_ninguna_cifra(tmp_path):
    _pieza(tmp_path, "2026-11-06-soporte")

    html = _web(tmp_path).get("/p/2026-11-06-soporte").text

    assert 'class="impresion"' not in html


def test_sin_laminado_se_ve_su_tamano_y_donde_se_sabe_el_resto(tmp_path):
    """El diseño ya no lamina (2026-11-09): no se sabe en qué impresora se
    va a imprimir. La caja sí es de la pieza; gramos y tiempo los da
    PrusaSlicer al abrirla, y la web lo dice en vez de callar."""
    carpeta = _pieza(tmp_path, "2026-11-06-soporte")
    (carpeta / "pieza_report.json").write_text(json.dumps(
        {"titulo": "t", "resuelto": True, "bbox_mm": [60, 50.04, 10]}), encoding="utf-8")

    html = _web(tmp_path).get("/p/2026-11-06-soporte").text

    assert "60 × 50 × 10 mm" in html
    assert "gramos y tiempo, al abrirla en PrusaSlicer" in html
    assert "sin soportes" not in html


# --- Lo que se aprobó -------------------------------------------------------------


def test_lo_aprobado_sigue_a_la_vista_despues_de_aprobarlo(tmp_path):
    carpeta = _pieza(tmp_path, "2026-11-06-soporte")
    _con_concepto(carpeta)

    html = _web(tmp_path).get("/p/2026-11-06-soporte").text

    assert '<details class="aprobado">' in html
    assert "taladro central en lágrima" in html
    # Ya no se le pide que lo apruebe.
    assert "Si lo apruebas" not in html
    assert "Aprobar y diseñar" not in html


# --- Un botón que dice lo que hace -------------------------------------------------


def test_el_boton_dice_que_abre_prusaslicer_en_el_pc(tmp_path):
    _pieza(tmp_path, "2026-11-06-soporte")

    html = _web(tmp_path).get("/p/2026-11-06-soporte").text

    assert "Abrir en PrusaSlicer" in html
    assert "Imprimir en PrusaSlicer" not in html


# --- Mientras diseña --------------------------------------------------------------


def _en_marcha(carpeta, minutos):
    """Un proceso vivo en otro contenedor: lo dice su latido."""
    (carpeta / "rounds.json").unlink(missing_ok=True)
    (carpeta / "pieza_report.json").unlink(missing_ok=True)
    inicio = dt.datetime.now() - dt.timedelta(minutes=minutos)
    (carpeta / "job.json").write_text(json.dumps(
        {"pid": 999999, "inicio": inicio.isoformat(), "comando": ["intelliprint", "pieza"]}),
        encoding="utf-8")
    (carpeta / "latido").write_text("", encoding="utf-8")


def test_mientras_disena_no_ofrece_lo_que_aun_no_existe(tmp_path):
    _en_marcha(_pieza(tmp_path, "2026-11-09-soporte"), minutos=12)

    html = _web(tmp_path).get("/p/2026-11-09-soporte").text

    assert "Diseñando la versión 1" in html
    assert "data-abrir=" not in html
    assert ".zip" not in html


def test_mientras_disena_dice_cuanto_lleva(tmp_path):
    _en_marcha(_pieza(tmp_path, "2026-11-09-soporte"), minutos=12)

    html = _web(tmp_path).get("/p/2026-11-09-soporte").text

    assert "lleva 12 min" in html


def test_sin_imagen_el_hueco_no_es_un_rectangulo_blanco(tmp_path):
    carpeta = _pieza(tmp_path, "2026-11-09-soporte")
    _en_marcha(carpeta, minutos=1)
    for stl in carpeta.rglob("*.stl"):
        stl.unlink()

    html = _web(tmp_path).get("/p/2026-11-09-soporte").text

    assert 'class="foto grande vacia"' in html
    assert ".foto.vacia" in ESTILO


# --- Pedir un diseño nuevo --------------------------------------------------------


def test_el_cuadro_de_la_peticion_tiene_etiqueta(tmp_path):
    html = _con_trabajos(tmp_path).get("/").text

    assert '<label for="peticion"' in html


def test_el_ejemplo_corresponde_al_tipo_elegido(tmp_path):
    from orchestrator.web.paginas import EJEMPLOS

    html = _con_trabajos(tmp_path).get("/").text

    # «una pieza» va elegida: su ejemplo es el que se ve al abrir.
    assert "sargento" not in EJEMPLOS["pieza"].lower()
    # Uno por cada tipo que se puede pedir, y ninguno de más.
    assert set(EJEMPLOS) == {"pieza", "obra"}
    placeholder = html.split('id="peticion"', 1)[1].split(">", 1)[0]
    assert "sargento" not in placeholder.lower()


def test_lo_que_tarda_y_cuesta_se_ve_aunque_haya_algo_en_marcha(tmp_path):
    _en_marcha(_pieza(tmp_path, "2026-11-09-soporte"), minutos=3)

    html = _con_trabajos(tmp_path).get("/").text

    assert "cuesta hasta 5 USD" in html
    assert "espera a que termine" in html


# --- Legible y tocable ------------------------------------------------------------


def test_las_piezas_se_llaman_en_castellano_y_no_como_su_carpeta(tmp_path):
    _pieza(tmp_path, "2026-11-06-soporte")
    carpeta = tmp_path / "projects" / "2026-11-06-soporte"
    (carpeta / "parts" / "soporte").rename(carpeta / "parts" / "soporte_de_rodamiento")
    for f in (carpeta / "parts" / "soporte_de_rodamiento").iterdir():
        f.rename(f.with_name(f.name.replace("soporte", "soporte_de_rodamiento", 1)))

    html = _web(tmp_path).get("/p/2026-11-06-soporte").text

    assert '<div class="nombre-pieza">Soporte de rodamiento' in html


def test_lo_que_se_toca_mide_al_menos_44_px_y_el_movimiento_se_puede_quitar():
    # WCAG 2.2 pide 24 px como mínimo (2.5.8); 44 es lo que recomiendan
    # Apple y la propia WCAG en AAA (2.5.5) para el dedo.
    assert "min-height:44px" in ESTILO
    assert "@media (prefers-reduced-motion: reduce)" in ESTILO


def test_el_proyecto_de_varias_piezas_se_llama_backlog(tmp_path):
    """El usuario no entendía «obra» (2026-11-09): pidió «backlog», y así se
    llama. Desde F9.13 (limpieza) la opción dice además para qué es —por ahí
    entra ahora lo que se mueve—. «Obra» es solo el valor interno."""
    html = _web(tmp_path).get("/").text
    (opcion,) = re.findall(r'<option value="obra"[^>]*>([^<]*)</option>', html)
    assert opcion == "un backlog: un robot o un conjunto, pieza a pieza"


# --- Rótulos, colores y palabras (F9.13 (limpieza)) --------------------------------


def test_el_enlace_de_vuelta_dice_inventos_en_las_tres_paginas(tmp_path):
    """La portada es el inventario de inventos: él la llama «plataforma de
    administración de inventos». El proyecto volvía a «← Inventos» y el banco
    y la impresora a «← Proyectos», que es el mismo sitio con otro nombre."""
    _pieza(tmp_path, "2026-11-06-soporte")
    web = _web(tmp_path)

    for pagina in ("/p/2026-11-06-soporte", "/banco", "/impresora"):
        enlaces = re.findall(r'<a class="volver" href="/">([^<]*)</a>', web.get(pagina).text)
        assert enlaces == ["← Inventos"], pagina


def test_toda_variable_de_color_que_se_usa_esta_definida():
    """`var(--fondo-suave, …)` se usaba sin definir en `:root`: tiraba
    siempre de la reserva, y una variable que no existe no se ve al leer la
    paleta. Las que se usan, definidas; y ninguna con reserva."""
    paleta = ESTILO.split(":root {", 1)[1].split("}", 1)[0]
    definidas = set(re.findall(r"(--[\w-]+):", paleta))

    usadas = set(re.findall(r"var\((--[\w-]+)", ESTILO))

    assert usadas - definidas == set()
    assert "--fondo-suave:rgba(127,127,127,.12)" in paleta
    assert re.findall(r"var\(--[\w-]+\s*,", ESTILO) == []


def _regla(selector):
    """Las declaraciones de la regla de `selector` en la hoja de estilos."""
    return re.search(r"(?m)^\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", ESTILO).group(1)


def test_la_foto_de_una_tarjeta_no_destella_en_blanco_mientras_carga():
    """En el tema oscuro, cada tarjeta de la galería era un rectángulo
    blanco hasta que llegaba su imagen: el hueco tenía `--foto`, que es
    blanco en los dos temas. El hueco lleva un color del tema; la imagen no
    se toca."""
    (variable,) = re.findall(r"background:var\((--[\w-]+)\)", _regla(".tarjeta .foto"))
    oscuro = ESTILO.split("@media (prefers-color-scheme: dark)", 1)[1].split("}", 1)[0]

    (color,) = re.findall(re.escape(variable) + r":(#[0-9a-fA-F]+)", oscuro)

    # Oscuro de verdad: ninguno de sus tres canales pasa de un cuarto.
    canales = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    assert len(color) == 7 and max(canales) < 64, color


def test_sin_con_que_disenar_un_backlog_el_error_dice_backlog(tmp_path):
    """«esta web no tiene con qué diseñar «obra»»: `obra` es el valor
    interno del selector, y el usuario lo llama backlog."""
    r = _con_trabajos(tmp_path).post("/api/disenar", json={"tipo": "obra", "peticion": "un robot"})

    assert r.status_code == 503
    assert "un backlog" in r.json()["detail"]
    assert "obra" not in r.json()["detail"]
