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


def test_la_galeria_se_ordena_por_categorias(tmp_path):
    _version(tmp_path, "2026-10-01-sargento", mecanismo=SARGENTO)
    _version(tmp_path, "2026-10-02-algo", "Algo sin categoría")
    cal = _version(tmp_path, "2026-10-03-calibracion", "Pieza de calibración de holguras")
    (cal / "calibracion.md").write_text("# c\n", encoding="utf-8")

    html = _web(tmp_path).get("/").text

    assert 'data-categoria="sujeción"' in html
    assert 'data-categoria="otros"' in html
    assert 'data-categoria="calibración"' in html
    assert 'data-filtro="sujeción"' in html


def test_la_categoria_se_cambia_desde_la_web(tmp_path):
    _version(tmp_path, "2026-10-01-sargento", mecanismo=SARGENTO)
    web = _web(tmp_path)

    assert web.post("/api/proyectos/2026-10-01-sargento/categoria",
                    json={"categoria": "juguetes"}).status_code == 200
    assert web.post("/api/proyectos/2026-10-01-sargento/categoria",
                    json={"categoria": "<script>"}).status_code == 422

    html = web.get("/").text
    assert 'data-categoria="juguetes"' in html
    # Cambiar la categoría no es trabajo del proyecto: no lo pone «en marcha».
    assert "Diseñando" not in html


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


def test_cada_pieza_tiene_su_miniatura_y_se_puede_cambiar_sola(tmp_path):
    _version(tmp_path, "2026-10-01-sargento", mecanismo=SARGENTO, piezas=("cuerpo", "mango"))
    web = _con_trabajos(tmp_path)

    html = web.get("/p/2026-10-01-sargento").text
    assert 'src="/proyectos/2026-10-01-sargento/piezas/mango.png"' in html
    assert 'data-pieza="mango"' in html

    r = web.post("/api/proyectos/2026-10-01-sargento/modificar",
                 json={"peticion": "Ø40 mm", "pieza": "mango"})
    assert r.status_code == 200, r.text
    marca = json.loads((tmp_path / "projects" / r.json()["id"] / "proyecto.json").read_text(encoding="utf-8"))
    assert marca["pieza"] == "mango" and marca["cambio"] == "Ø40 mm"


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


def test_el_revisor_da_como_mucho_tres_frases_para_el_usuario():
    from orchestrator.schemas.review import ReviewReport

    r = ReviewReport.model_validate({"items": [], "summary": "s",
                                     "para_el_usuario": ["a", "b", "c", "d"]})
    assert r.para_el_usuario == ["a", "b", "c"]
    assert ReviewReport.model_validate({"items": [], "summary": "s"}).para_el_usuario == []


def test_el_disenador_elige_la_categoria_de_la_lista():
    from mech_toolkit.generators import CATALOGO
    from orchestrator.agents.mechanism_designer import MechanismDesignerAgent
    from orchestrator.categorias import CATEGORIAS
    from tests.test_mechanism_flow import PERFIL, Guion

    agente = MechanismDesignerAgent(Guion([]), CATALOGO, PERFIL, (235, 235, 250), 0.1)
    for categoria in CATEGORIAS:
        assert categoria in agente._instrucciones


def test_una_categoria_que_no_esta_en_la_lista_es_otros():
    from orchestrator.categorias import normalizar

    assert normalizar("Sujeción") == "sujeción"
    assert normalizar("cohetes") == "otros"
    assert normalizar(None) == "otros"
