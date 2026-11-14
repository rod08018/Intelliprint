"""La web como app: galería por categorías y una página por proyecto
(F5.5 (web)).

Lo que el usuario dijo de la anterior (2026-10-26): «es horrible», «saca
como 40 mil líneas de que cumple y que no, a un usuario le vale pito», y
un solo sargento salía como dos proyectos. Quiere ver sus proyectos
ordenados por categorías, entrar en uno, y cambiarle una pieza con una
frase. Lo esperado en estos tests sale de cómo se construye cada
workspace, no de lo que pinte la web.
"""

import json
import re
import os
import sys

import pytest
from fastapi.testclient import TestClient

from orchestrator.web.app import crear_app
from tests.test_slicing import _cubo_stl

HOST = r"C:\repo\workspace"


def _version(ws, nombre, peticion="Un sargento de banco", feedback="", revision=None,
             mecanismo=None, piezas=(), seccion="projects"):
    carpeta = ws / seccion / nombre
    carpeta.mkdir(parents=True)
    (carpeta / "request.md").write_text(peticion + "\n", encoding="utf-8")
    (carpeta / "rounds.json").write_text(
        json.dumps([{"number": 1, "title": "t", "feedback": feedback}]), encoding="utf-8")
    if mecanismo is not None:
        (carpeta / "mechanism.json").write_text(json.dumps(mecanismo), encoding="utf-8")
    if revision is not None:
        (carpeta / "review.json").write_text(json.dumps(revision), encoding="utf-8")
    for pieza in piezas:
        (carpeta / "parts" / pieza).mkdir(parents=True)
        _cubo_stl(carpeta / "parts" / pieza / f"{pieza}.stl", 20)
    viejo = 1_700_000_000
    for f in [carpeta, *carpeta.rglob("*")]:
        os.utime(f, (viejo, viejo))
    return carpeta


def _revision(no_cumple=0, cumple=1, para_el_usuario=None):
    items = ([{"requirement": f"Requisito largo número {i} con sus medidas", "verdict": "no_cumple",
               "comment": "c"} for i in range(no_cumple)]
             + [{"requirement": "otro", "verdict": "cumple", "comment": "c"}] * cumple)
    r = {"items": items, "summary": "s"}
    if para_el_usuario is not None:
        r["para_el_usuario"] = para_el_usuario
    return r


SARGENTO = {"title": "Sargento de banco", "summary": "s", "categoria": "sujeción",
            "parts": [{"name": "cuerpo"}, {"name": "mango"}]}


def _web(ws, trabajos=None):
    return TestClient(crear_app(ws, host_workspace=HOST, trabajos=trabajos))


def _con_trabajos(ws):
    from orchestrator.jobs import JobStore
    trabajos = JobStore(ws / "projects", comando=[sys.executable, "-c", "import sys; print(sys.argv)"])
    return _web(ws, trabajos)


# --- La galería ----------------------------------------------------------------


def test_la_galeria_es_una_tarjeta_por_proyecto_que_lleva_a_su_pagina(tmp_path):
    for n in (1, 2, 3):
        _version(tmp_path, f"2026-09-21-0{n}-gato", "Un gato de tijera",
                 feedback="" if n == 2 else "- choca")

    html = _web(tmp_path).get("/").text

    assert html.count('href="/p/2026-09-21-01-gato"') == 1
    assert "/p/2026-09-21-02-gato" not in html


def test_la_galeria_dice_el_estado_en_palabras_y_sin_jerga(tmp_path):
    _version(tmp_path, "2026-10-01-bueno", "Uno bueno", mecanismo=SARGENTO)
    _version(tmp_path, "2026-10-02-reparos", "Uno con reparos", revision=_revision(no_cumple=11))
    _version(tmp_path, "2026-10-03-malo", "Uno que choca", feedback="- choca")

    html = _web(tmp_path).get("/").text

    assert "Listo para imprimir" in html
    assert "Listo, pero distinto a lo pedido" in html
    assert "No salió" in html
    # Ni rondas, ni requisitos, ni el recuento del revisor en la galería.
    for jerga in ("ronda", "requisito", "revisor", "✗11", "cumple"):
        assert jerga not in html.lower(), jerga


def _categoria_elegida(web, id_):
    """La que sale marcada en el desplegable de la ficha del invento."""
    return re.search(r'<option value="([^"]+)" selected>', web.get(f"/p/{id_}").text).group(1)


def test_cada_invento_sigue_llevando_su_categoria(tmp_path):
    """La categoría era el filtro de la portada; desde el inventario
    (F7.8 (inventario)) se filtra por tipo y etapa, y la categoría queda como
    dato del invento, en su ficha, que se sigue pudiendo cambiar."""
    _version(tmp_path, "2026-10-01-sargento", mecanismo=SARGENTO)
    _version(tmp_path, "2026-10-02-algo", "Algo sin categoría")
    cal = _version(tmp_path, "2026-10-03-calibracion", "Pieza de calibración de holguras")
    (cal / "calibracion.md").write_text("# c\n", encoding="utf-8")
    web = _web(tmp_path)

    assert _categoria_elegida(web, "2026-10-01-sargento") == "sujeción"
    assert _categoria_elegida(web, "2026-10-02-algo") == "otros"
    assert _categoria_elegida(web, "2026-10-03-calibracion") == "calibración"


def test_la_categoria_se_cambia_desde_la_web(tmp_path):
    _version(tmp_path, "2026-10-01-sargento", mecanismo=SARGENTO)
    web = _web(tmp_path)

    assert web.post("/api/proyectos/2026-10-01-sargento/categoria",
                    json={"categoria": "juguetes"}).status_code == 200
    assert web.post("/api/proyectos/2026-10-01-sargento/categoria",
                    json={"categoria": "<script>"}).status_code == 422

    assert _categoria_elegida(web, "2026-10-01-sargento") == "juguetes"
    # Cambiar la categoría no es trabajo del proyecto: no lo pone «en marcha».
    assert "Diseñando" not in web.get("/").text


def test_la_galeria_ensena_la_animacion_o_la_vista(tmp_path):
    con_gif = _version(tmp_path, "2026-10-01-sargento", mecanismo=SARGENTO, piezas=("cuerpo",))
    (con_gif / "animation.gif").write_bytes(b"GIF89a")
    _version(tmp_path, "2026-10-02-pieza", "Una pieza", piezas=("soporte",))

    html = _web(tmp_path).get("/").text

    assert 'src="/proyectos/2026-10-01-sargento/animation.gif"' in html
    assert 'src="/proyectos/2026-10-02-pieza/vista.png"' in html


# --- La página de un proyecto ---------------------------------------------------


def test_la_pagina_elige_la_mejor_version_y_deja_ver_las_demas(tmp_path):
    for n in (1, 2, 3):
        _version(tmp_path, f"2026-09-21-0{n}-gato", "Un gato de tijera",
                 feedback="" if n == 2 else "- choca")
    web = _web(tmp_path)

    html = web.get("/p/2026-09-21-01-gato").text

    for n in (1, 2, 3):
        assert f'href="/p/2026-09-21-01-gato?v=2026-09-21-0{n}-gato"' in html
    assert 'aria-current="true" href="/p/2026-09-21-01-gato?v=2026-09-21-02-gato"' in html
    assert 'href="/proyectos/2026-09-21-02-gato.zip"' in html

    otra = web.get("/p/2026-09-21-01-gato?v=2026-09-21-03-gato").text
    assert 'href="/proyectos/2026-09-21-03-gato.zip"' in otra


def test_lo_distinto_a_lo_pedido_son_tres_frases_como_mucho(tmp_path):
    _version(tmp_path, "2026-10-01-sargento", revision=_revision(
        no_cumple=11, para_el_usuario=["La V es escalonada", "El mango no es hexagonal"]))
    _version(tmp_path, "2026-10-02-viejo", "Otro", revision=_revision(no_cumple=5))
    web = _web(tmp_path)

    html = web.get("/p/2026-10-01-sargento").text
    assert "La V es escalonada" in html and "El mango no es hexagonal" in html
    assert "Requisito largo" not in html

    # Sin frases del revisor (proyectos de antes): los tres primeros, nada más.
    viejo = web.get("/p/2026-10-02-viejo").text
    assert "Requisito largo número 2" in viejo
    assert "Requisito largo número 3" not in viejo


def test_lo_que_no_salio_dice_por_que_en_una_frase(tmp_path):
    _version(tmp_path, "2026-10-01-gato", "Un gato", feedback="- la tijera choca con la base\n- otra")

    html = _web(tmp_path).get("/p/2026-10-01-gato").text

    assert "No salió" in html
    assert "la tijera choca con la base" in html


def test_la_miniatura_de_una_pieza_es_una_imagen(tmp_path):
    _version(tmp_path, "2026-10-01-sargento", mecanismo=SARGENTO, piezas=("mango",))
    web = _web(tmp_path)

    r = web.get("/proyectos/2026-10-01-sargento/piezas/mango.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    for malo in ("no-existe", "..", "%2E%2E"):
        assert web.get(f"/proyectos/2026-10-01-sargento/piezas/{malo}.png").status_code == 404


def test_un_proyecto_que_no_existe_es_404(tmp_path):
    _version(tmp_path, "2026-10-01-sargento")
    assert _web(tmp_path).get("/p/no-existe").status_code == 404
    # «/p/..» lo normaliza el cliente a «/» (la galería); codificado sí llega.
    assert _web(tmp_path).get("/p/%2E%2E").status_code == 404


def test_lo_tecnico_existe_pero_aparte(tmp_path):
    """Las rondas y el informe entero siguen ahí, para depurar, pero no en
    la cara del proyecto: se cargan al abrir «Detalles técnicos»."""
    _version(tmp_path, "2026-10-01-sargento", revision=_revision(no_cumple=2))
    html = _web(tmp_path).get("/p/2026-10-01-sargento").text
    assert "Detalles técnicos" in html
    assert "Ronda 1" not in html


# --- Lo que la web necesita del diseño --------------------------------------------


def test_una_categoria_que_no_esta_en_la_lista_es_otros():
    from orchestrator.categorias import normalizar

    assert normalizar("Sujeción") == "sujeción"
    assert normalizar("cohetes") == "otros"
    assert normalizar(None) == "otros"


# --- El inventario de inventos (F7.8 (inventario)) ------------------------------
# «Es una plataforma de administración de inventos: cada invento puede ser
# sencillo como una pieza o complicado como un robot» (el usuario, 2026-11-10).
# La portada era una galería por categorías donde todo se veía igual.


def _inventario(ws):
    from tests.test_materiales import _pan_tilt
    from tests.test_web_piezas_sueltas import _pieza
    robot = ws / "projects" / "2026-11-09-pan-tilt"
    robot.mkdir(parents=True)
    _pan_tilt(robot)
    (robot / "request.md").write_text("un pan-tilt con dos SG90\n", encoding="utf-8")
    (robot / "nodos" / "conjunto" / "verificacion.json").parent.mkdir(parents=True, exist_ok=True)
    (robot / "nodos" / "conjunto" / "verificacion.json").write_text(json.dumps(
        {"ok": True, "choques": [], "resumen": [], "articulaciones": [
            {"pieza": "soporte", "padre": "base", "de": "sg90", "eje_mundo": [0, 0, 1],
             "recorrido": [-90, 90]}]}), encoding="utf-8")
    _pieza(ws, "2026-11-08-soporte")
    _version(ws, "2026-10-01-sargento", mecanismo=SARGENTO)
    return _web(ws).get("/").text


def _tarjeta(html, id_):
    return re.search(rf'<a class="tarjeta" href="/p/{re.escape(id_)}".*?</a>', html, re.S).group(0)


def test_cada_invento_dice_si_es_una_pieza_un_mecanismo_o_un_robot(tmp_path):
    html = _inventario(tmp_path)
    robot = _tarjeta(html, "2026-11-09-pan-tilt")
    assert 'data-tipo="robot"' in robot and "Robot · 3 piezas" in robot
    assert 'data-tipo="pieza"' in _tarjeta(html, "2026-11-08-soporte")
    assert 'data-tipo="mecanismo"' in _tarjeta(html, "2026-10-01-sargento")


def test_la_tarjeta_de_un_robot_dice_lo_que_se_compra(tmp_path):
    """Dos SG90, contados a mano en `tests/test_materiales.py`."""
    assert "2 × Micro servo SG90" in _tarjeta(_inventario(tmp_path), "2026-11-09-pan-tilt")


def test_se_filtra_por_tipo_y_por_etapa(tmp_path):
    html = _inventario(tmp_path)
    for filtro in ('data-filtro="tipo:robot"', 'data-filtro="tipo:pieza"',
                   'data-filtro="tipo:mecanismo"', 'data-filtro="etapa:listo"'):
        assert filtro in html, filtro
    assert 'data-etapa="listo"' in _tarjeta(html, "2026-11-08-soporte")
    # La categoría ya no es un filtro de la portada.
    assert 'data-filtro="sujeción"' not in html


def test_la_cabecera_cabe_en_un_movil():
    """En el panel estrecho (2026-11-10) «＋ Nuevo diseño» quedaba cortado y la
    página se desplazaba a lo ancho: la barra tiene que poder partirse."""
    from orchestrator.web.paginas import ESTILO
    movil = ESTILO[ESTILO.index("@media (max-width:820px)"):]
    movil = movil[:movil.index("\n  }")]
    assert re.search(r"\.barra \{[^}]*flex-wrap:\s*wrap", movil)
    # Y no se queda pegada arriba: partida en tres filas tapaba media pantalla.
    assert re.search(r"\.barra \{[^}]*position:\s*static", movil)


def test_la_pagina_de_un_robot_dice_lo_que_lleva(tmp_path):
    """La lista de materiales (F7.8 (inventario)): lo que se imprime, lo que
    se compra y qué tornillos, contados a mano en `tests/test_materiales.py`."""
    from tests.test_web_obra import _visible
    _inventario(tmp_path)
    html = _web(tmp_path).get("/p/2026-11-09-pan-tilt").text
    texto = _visible(html)
    assert "Lo que lleva" in texto
    assert "2 × Micro servo SG90 (9 g)" in texto
    for pieza in ("Pieza base", "Pieza soporte", "Pieza plataforma"):
        assert pieza in texto, pieza
    assert "2 × Tornillo avellanado M4" in texto
    # Lo que viene en la bolsa del servo se ve, pero no se compra aparte.
    assert "Viene con lo comprado" in texto
    assert "1 × Tornillo M2 de 10.9 mm" in texto
    assert "Robot · 3 piezas" in texto


def test_la_lista_enlaza_donde_se_compra_lo_que_lo_dice():
    """«En los BOM agrega el link de compra de la reductora» (el usuario,
    2026-11-14): lo comprado que trae enlace lo enseña, en otra pestaña; lo
    que no, sigue como estaba. El enlace va escapado: es un dato de una ficha."""
    from orchestrator.web.paginas import _lista_de_materiales
    html = _lista_de_materiales({
        "impresas": [{"id": "hombro", "nombre": "Hombro", "impresa": False}],
        "comprado": [
            {"id": "reductora", "nombre": "NEMA 23 con reductora", "cuantos": 1,
             "tipo": "componente", "enlace": "https://tienda.example/a?b=1&c=2"},
            {"id": "sg90", "nombre": "Micro servo SG90 (9 g)", "cuantos": 2, "tipo": "componente"}],
        "incluido": []})
    assert html.count("<a ") == 1
    assert 'href="https://tienda.example/a?b=1&amp;c=2"' in html
    assert 'target="_blank"' in html and 'rel="noopener' in html
    assert "<b>2 ×</b> Micro servo SG90 (9 g)</li>" in html


def test_la_tarjeta_no_se_llena_de_tornillos(tmp_path):
    """En la tarjeta caben los componentes; la tornillería va en la página."""
    assert "Tornillo" not in _tarjeta(_inventario(tmp_path), "2026-11-09-pan-tilt")


def test_una_pieza_no_lleva_lista_de_materiales_si_no_compra_nada(tmp_path):
    from tests.test_web_obra import _visible
    _inventario(tmp_path)
    assert "Lo que lleva" not in _visible(_web(tmp_path).get("/p/2026-11-08-soporte").text)


# --- Los mecanismos que ya hay (F9.13 (limpieza)) -------------------------------


def test_un_mecanismo_ya_hecho_se_sigue_viendo_pero_no_se_puede_cambiar(tmp_path):
    """El flujo de mecanismos se quitó, pero los que dejó en el workspace son
    trabajo del usuario: se ven en la galería y en su ficha, con su animación,
    sus piezas, la descarga y PrusaSlicer. Lo que ya no hay es con qué
    cambiarlos, así que la ficha no lo ofrece."""
    carpeta = _version(tmp_path, "2026-10-01-sargento", mecanismo=SARGENTO,
                       piezas=("cuerpo", "mango"))
    (carpeta / "animation.gif").write_bytes(b"GIF89a")
    web = _con_trabajos(tmp_path)

    portada = web.get("/").text
    tarjeta = _tarjeta(portada, "2026-10-01-sargento")
    assert 'data-tipo="mecanismo"' in tarjeta and ">Mecanismo<" in tarjeta
    assert "Sargento de banco" in tarjeta
    assert 'data-filtro="tipo:mecanismo"' in portada

    html = web.get("/p/2026-10-01-sargento").text
    assert "<h1>Sargento de banco</h1>" in html
    assert 'src="/proyectos/2026-10-01-sargento/animation.gif"' in html
    for pieza in ("cuerpo", "mango"):
        assert f'src="/proyectos/2026-10-01-sargento/piezas/{pieza}.png"' in html
    assert 'href="/proyectos/2026-10-01-sargento.zip"' in html
    assert 'data-abrir="2026-10-01-sargento"' in html
    assert web.get("/proyectos/2026-10-01-sargento/animation.gif").status_code == 200
    assert web.get("/proyectos/2026-10-01-sargento.zip").status_code == 200
    # Ni «Cambiar» en cada pieza ni «Cambiar algo» (el guion nombra el
    # atributo sin valor; un formulario lo lleva con él).
    assert 'data-modificar="' not in html and 'data-pieza="' not in html
    assert "Cambiar algo" not in html


def test_la_portada_no_recalcula_los_tornillos_de_un_invento_que_no_ha_cambiado(
        tmp_path, monkeypatch):
    """Medido el 2026-11-11 con tres inventos: la portada tardaba 10 segundos
    en cada carga, 8 de ellos midiendo otra vez el grosor que atraviesa cada
    tornillo en la malla de cada pieza. Y mientras algo se diseña se recarga
    sola cada 15 segundos. La lista de materiales solo cambia si cambia una
    pieza, una ficha, el backlog o la marca de «impresa»."""
    from orchestrator import materiales as M
    from orchestrator.web import paginas
    from tests.test_materiales import _pan_tilt

    carpeta = _pan_tilt(tmp_path)
    veces = []
    de_verdad = M.materiales
    monkeypatch.setattr(M, "materiales", lambda c: veces.append(c) or de_verdad(c))

    primera = paginas._materiales(carpeta)
    assert paginas._materiales(carpeta) == primera and len(veces) == 1

    rasgos = next(carpeta.rglob("rasgos.json"))
    rasgos.write_text(rasgos.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    paginas._materiales(carpeta)
    assert len(veces) == 2, "cambió una pieza: se mide otra vez"

    marca = carpeta / "nodos" / "base" / "lista.json"
    marca.parent.mkdir(parents=True, exist_ok=True)
    marca.write_text('{"por": "web", "impresa": true}', encoding="utf-8")
    paginas._materiales(carpeta)
    assert len(veces) == 3, "se marcó una pieza como impresa"
