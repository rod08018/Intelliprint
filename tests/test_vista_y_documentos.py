"""Que un proyecto sin mecanismo también se entienda en la web (F5.5 (web)).

Fallo real (2026-10-24): la pieza de calibración salía como «3 piezas» y
nada más. Sin animación —no es un mecanismo— no había imagen; las
instrucciones de cómo probarla estaban en calibracion.md y la web no las
enseñaba; y los textos hablaban de «montar el mecanismo» y de rondas.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from orchestrator.web.app import crear_app
from tests.test_slicing import _cubo_stl

HOST = r"C:\repo\workspace"


@pytest.fixture
def ws(tmp_path):
    """Un proyecto de piezas sueltas, como el de calibración, y un mecanismo."""
    piezas = tmp_path / "projects" / "2026-10-24-1607-calibracion_holguras"
    for nombre, lado in (("calibracion_agujeros", 30), ("calibracion_eje", 20)):
        (piezas / "parts" / nombre).mkdir(parents=True)
        _cubo_stl(piezas / "parts" / nombre / f"{nombre}.stl", lado)
    (piezas / "request.md").write_text("Pieza de calibración de holguras\n", encoding="utf-8")
    (piezas / "calibracion.md").write_text(
        "# Calibración\n\nPrueba el eje en cada agujero:\n\n"
        "- **a presión**: el primero que entra empujando\n\n"
        "| Posición | Agujero (mm) |\n|---|---|\n| 1 | 5.00 |\n| 2 | 5.10 |\n\n"
        "<script>alert(1)</script>\n\n```\nintelliprint calibrar resultados --press 0.1\n```\n",
        encoding="utf-8")

    meca = tmp_path / "projects" / "2026-10-20-trinquete"
    meca.mkdir(parents=True)
    (meca / "request.md").write_text("un trinquete\n", encoding="utf-8")
    (meca / "mechanism.json").write_text(json.dumps({"parts": [{"name": "rueda"}]}),
                                         encoding="utf-8")
    return tmp_path


@pytest.fixture
def web(ws):
    return TestClient(crear_app(ws, host_workspace=HOST))


ID = "2026-10-24-1607-calibracion_holguras"


def test_un_proyecto_de_piezas_tiene_una_vista_de_ellas(web, ws):
    r = web.get(f"/proyectos/{ID}/vista.png")

    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "image/png"
    imagen = Image.open(ws / "projects" / ID / "vista.png")
    assert imagen.width > 200 and imagen.height > 200


def test_la_vista_se_guarda_y_no_se_redibuja_en_cada_visita(web, ws):
    web.get(f"/proyectos/{ID}/vista.png")
    antes = (ws / "projects" / ID / "vista.png").stat().st_mtime_ns

    web.get(f"/proyectos/{ID}/vista.png")

    assert (ws / "projects" / ID / "vista.png").stat().st_mtime_ns == antes


def test_sin_piezas_no_hay_vista(web):
    assert web.get("/proyectos/2026-10-20-trinquete/vista.png").status_code == 404


def test_el_detalle_dice_que_no_es_un_mecanismo_y_que_hay_vista(web):
    d = web.get(f"/api/proyectos/{ID}").json()

    assert d["es_mecanismo"] is False and d["vista"] is True
    assert web.get("/api/proyectos/2026-10-20-trinquete").json()["es_mecanismo"] is True


def test_el_detalle_trae_las_instrucciones_de_la_pieza(web):
    (doc,) = web.get(f"/api/proyectos/{ID}").json()["documentos"]

    assert doc["archivo"] == "calibracion.md"
    assert "<td>5.10</td>" in doc["html"]
    assert "<strong>a presión</strong>" in doc["html"]
    assert "intelliprint calibrar resultados --press 0.1" in doc["html"]
    # Es texto, no HTML: lo que venga en el archivo no se ejecuta.
    assert "<script>" not in doc["html"]


def test_la_fila_ensena_la_vista_si_no_hay_animacion(web):
    html = web.get("/").text
    assert f'src="/proyectos/{ID}/vista.png"' in html


def test_a_un_proyecto_que_no_es_un_mecanismo_no_se_le_piden_modificaciones(web):
    """Una modificación relanza el DISEÑO del mecanismo con la petición del
    proyecto: con la de la pieza de calibración, el diseñador inventaría
    un mecanismo a partir de «Pieza de calibración de holguras»."""
    assert f'data-modificar="{ID}"' not in web.get(f"/p/{ID}").text
    assert 'data-modificar="2026-10-20-trinquete"' in web.get("/p/2026-10-20-trinquete").text
