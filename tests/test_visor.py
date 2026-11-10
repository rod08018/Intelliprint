"""El ensamble en 3D de la web (F7.9 (visor)).

«Si es un robot debería poder ver en algún momento el ensamble final» (el
usuario, 2026-11-10). El GIF enseña un recorrido fijo; en el visor se gira
con el ratón y cada articulación se mueve con un deslizador. Las poses no
las calcula el navegador: las da `conjunto.poses()`, la misma cinemática con
la que se barrieron los choques. Lo esperado está calculado a mano.
"""

import json

import pytest

from tests.test_conjunto import _obra, _sg90, _sobre
from tests.test_web_galeria import _web

ID = "2026-11-10-giro"


def _giro(ws, choques=()):
    """La base y el soporte de giro del pan-tilt (como en
    `test_la_pieza_de_encima_gira_con_el_eje_del_servo_de_la_de_abajo`): el
    soporte gira alrededor del eje del SG90 de la base, que pasa por
    (29.4, 12.2) en vertical."""
    carpeta = ws / "projects" / ID
    carpeta.mkdir(parents=True)
    _obra(carpeta, {
        "base": ([], [_sg90((23.6, 6, 0))], ([0, 0, 0], [70, 34, 18.5])),
        "soporte": (["base"], [_sobre("base", (-29.4, -12.2, -27.6))],
                    ([-28, -17, 0], [28, 17, 31])),
    })
    (carpeta / "request.md").write_text("un soporte que gira\n", encoding="utf-8")
    (carpeta / "nodos" / "conjunto").mkdir(parents=True)
    (carpeta / "nodos" / "conjunto" / "verificacion.json").write_text(json.dumps(
        {"ok": not choques, "paso": 10.0, "choques": list(choques), "resumen": [],
         "articulaciones": []}), encoding="utf-8")
    return carpeta


def test_las_poses_salen_de_la_cinematica_del_conjunto(tmp_path):
    """El soporte colocó la base en (-29.4, -12.2, -27.6): en reposo está en
    (29.4, 12.2, 27.6) del marco de la base. Su origen cae en el eje del
    SG90, así que a 90° no se mueve y solo gira: x pasa a y."""
    _giro(tmp_path)
    web = _web(tmp_path)
    r = web.get(f"/proyectos/{ID}/nodos/conjunto/poses", params={"soporte": 90})
    assert r.status_code == 200, r.text
    m = r.json()["poses"]["soporte"]       # 4x4, por filas
    assert m == pytest.approx([0, -1, 0, 29.4,
                               1, 0, 0, 12.2,
                               0, 0, 1, 27.6,
                               0, 0, 0, 1], abs=1e-9)
    assert r.json()["poses"]["base"] == pytest.approx([1, 0, 0, 0, 0, 1, 0, 0,
                                                       0, 0, 1, 0, 0, 0, 0, 1])


def test_lo_que_choca_en_ese_angulo_sale_en_rojo(tmp_path):
    _giro(tmp_path, choques=[{"a": "soporte", "b": "base", "solido_a": "soporte",
                              "solido_b": "base: montado", "angulos": {"soporte": 90.0},
                              "hueco_mm": 0}])
    web = _web(tmp_path)
    rojo = web.get(f"/proyectos/{ID}/nodos/conjunto/poses", params={"soporte": 90}).json()
    assert set(rojo["rojos"]) == {"soporte", "base: montado"}
    assert web.get(f"/proyectos/{ID}/nodos/conjunto/poses",
                   params={"soporte": 0}).json()["rojos"] == []


def test_un_nodo_que_no_es_del_arbol_no_se_sirve(tmp_path):
    _giro(tmp_path)
    web = _web(tmp_path)
    assert web.get(f"/proyectos/{ID}/nodos/no-existe/poses").status_code == 404
    assert web.get(f"/proyectos/{ID}/nodos/conjunto/ensamble.json").status_code == 404


def test_el_ensamble_guardado_lleva_cada_malla_con_su_pieza(tmp_path):
    """Lo que escribe la verificación para el visor: una malla por sólido,
    de quién es y cómo se mueve cada articulación."""
    from orchestrator.conjunto import Articulacion, guardar_ensamble, leer_piezas
    carpeta = _giro(tmp_path)
    piezas = leer_piezas(carpeta, "conjunto")
    cubo = ([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 2]])
    arts = {"soporte": Articulacion("soporte", "base", "sg90", [29.4, 12.2, 27.1], [0, 0, 1],
                                    (-90, 90))}
    destino = carpeta / "nodos" / "conjunto" / "ensamble.json"
    guardar_ensamble({"base": cubo, "soporte": cubo, "base: montado": cubo}, piezas, arts,
                     {"base": "base", "soporte": "soporte", "base: montado": "base"},
                     paso=10.0, destino=destino)
    datos = json.loads(destino.read_text(encoding="utf-8"))
    assert {s: x["pieza"] for s, x in datos["solidos"].items()} == {
        "base": "base", "soporte": "soporte", "base: montado": "base"}
    assert datos["solidos"]["base"]["v"] == [0, 0, 0, 1, 0, 0, 0, 1, 0]
    assert datos["solidos"]["base"]["t"] == [0, 1, 2]
    assert datos["articulaciones"] == [{"pieza": "soporte", "nombre": "Pieza soporte",
                                        "recorrido": [-90, 90], "paso": 10.0}]

    web = _web(tmp_path)
    assert web.get(f"/proyectos/{ID}/nodos/conjunto/ensamble.json").json() == datos


# --- El visor en la página ----------------------------------------------------------


def _con_ensamble(ws):
    carpeta = _giro(ws)
    (carpeta / "nodos" / "conjunto" / "ensamble.json").write_text(
        json.dumps({"solidos": {}, "piezas": {}, "articulaciones": []}), encoding="utf-8")
    return carpeta


def test_la_pagina_de_un_ensamble_lleva_el_visor_del_ultimo_conjunto(tmp_path):
    _con_ensamble(tmp_path)
    html = _web(tmp_path).get(f"/p/{ID}").text
    assert f'data-visor="/proyectos/{ID}/nodos/conjunto"' in html
    assert '"three": "/estatico/three.module.min.js"' in html


def test_sin_ensamble_no_hay_visor(tmp_path):
    """Un proyecto anterior al visor, o un conjunto aún sin mover: se queda
    con lo que tenía."""
    _giro(tmp_path)
    assert "data-visor=" not in _web(tmp_path).get(f"/p/{ID}").text


def test_three_se_sirve_desde_la_propia_web(tmp_path):
    """Sin CDN: la web corre en la red de casa y tiene que funcionar sin
    internet. Solo se sirve lo que está en la lista."""
    web = _web(tmp_path)
    r = web.get("/estatico/three.module.min.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]
    assert 'const t="170"' in r.text[:400]
    assert web.get("/estatico/OrbitControls.js").status_code == 200
    assert web.get("/estatico/README.md").status_code == 404
    assert web.get("/estatico/..%2Fapp.py").status_code == 404


def test_el_visor_recibe_cada_tornillo_en_el_marco_de_la_pieza_donde_apoya(tmp_path):
    """«El ensamble debe mostrar todo lo que el BOM requiere» (el usuario,
    2026-11-10). El M3 × 16 que une tapa y base (sumado a mano en
    `tests/test_tornilleria.py`) va con la tapa, donde apoya su cabeza, y
    su tuerca con la base."""
    from tests.test_tornilleria import _agujero, _tuerca
    carpeta = tmp_path / "projects" / ID
    carpeta.mkdir(parents=True)
    _obra(carpeta, {
        "base": ([], [_agujero("pasa", (10, 10, 10), metrica="M3"),
                      _tuerca("tuerca", (10, 10, 0))], ([0, 0, 0], [40, 20, 10])),
        "tapa": (["base"], [_sobre("base", (0, 0, -10)),
                            _agujero("pasa", (10, 10, 5), metrica="M3")],
                 ([0, 0, 0], [40, 20, 5])),
    })
    (carpeta / "request.md").write_text("una caja\n", encoding="utf-8")
    [t] = _web(tmp_path).get(f"/proyectos/{ID}/nodos/conjunto/tornillos").json()
    assert (t["pieza"], t["d"], t["largo"]) == ("tapa", 3.0, 16)
    assert t["cabeza"] == pytest.approx([10, 10, 5])
    assert t["eje"] == pytest.approx([0, 0, -1])
    [n] = t["tuercas"]
    assert (n["pieza"], n["alto"]) == ("base", 2.4)
    assert n["en"] == pytest.approx([10, 10, 0])
