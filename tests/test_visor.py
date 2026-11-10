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


# --- El estudio de movimientos en la web (F7.10 (estudio)) ----------------------------


def _estudio_hecho(carpeta):
    """Un `estudio.json` escrito a mano para el giro: 10 g de lastre en la
    base, en (35, 17), y 20 g en el soporte, a 10 mm de su eje en x."""
    e = {"conjunto": "conjunto", "tension_V": 4.8, "paso": 10.0, "poses": 19,
         "masas": [{"nombre": "Lastre", "g": 10.0, "centro": [35, 17, 0], "de": "PrusaSlicer",
                    "pieza": "base"},
                   {"nombre": "Soporte", "g": 20.0, "centro": [10, 0, 0], "de": "estimada",
                    "pieza": "soporte"}],
         "masa_total_g": 30.0,
         "carga": {"punto": [0, 0, 31], "pieza": "soporte", "donde": "en lo alto del soporte"},
         "servos": [{"pieza": "soporte", "nombre": "Pieza soporte", "servo": "Micro servo SG90",
                     "par_max_Nm": 0.0, "angulo_peor": 0.0, "recorrido": [-90, 90],
                     "tension_V": 4.8, "par_bloqueo_Nm": 0.17652, "par_disponible_Nm": 0.08826,
                     "aguanta": True, "margen": 1.0, "carga_max_g": None, "tiempo_s": 0.3,
                     "velocidad_punta_mm_s": 0.0}],
         "vuelco": {"margen_mm": 13.53, "pose": {"soporte": 90.0}, "atornillada": False,
                    "carga_max_g": 250.0, "apoyo": [[0, 0], [70, 0], [70, 34], [0, 34]]},
         "alcance": {"radio_mm": 0.0, "caja_mm": [[29.4, 12.2, 58.6], [29.4, 12.2, 58.6]],
                     "puntos": [[29.4, 12.2, 58.6], [30.4, 12.2, 58.6]]},
         "carga_max": {"g": 250.0, "limita": "vuelco"},
         "material": [{"pieza": "soporte", "nombre": "Pieza soporte", "largo_mm": 31.0,
                       "detalle": "la carga tira a lo largo: no flexa", "carga_max_g": None}],
         "avisos": ["El invento no dice con qué tensión van los servos: se toma 4.8 V."]}
    (carpeta / "nodos" / "conjunto" / "estudio.json").write_text(
        json.dumps(e, ensure_ascii=False), encoding="utf-8")


def test_las_poses_dicen_el_par_de_cada_servo_y_el_margen_de_vuelco(tmp_path):
    """A 0° el soporte está en (29.4, 12.2): sus 20 g caen en (39.4, 12.2) y
    el centro de masas en (37.93, 13.8), a 13.8 mm del borde y = 0. A 90°
    caen en (29.4, 22.2): el centro, en (31.27, 20.47), a 13.53 del borde
    y = 34. El eje es vertical: la gravedad no le pide par al servo."""
    carpeta = _giro(tmp_path)
    _estudio_hecho(carpeta)
    web = _web(tmp_path)
    a0 = web.get(f"/proyectos/{ID}/nodos/conjunto/poses", params={"soporte": 0}).json()
    assert a0["estudio"]["vuelco_mm"] == pytest.approx(13.8, abs=1e-6)
    assert a0["estudio"]["pares"]["soporte"] == pytest.approx({"Nm": 0.0, "uso": 0.0}, abs=1e-9)
    a90 = web.get(f"/proyectos/{ID}/nodos/conjunto/poses", params={"soporte": 90}).json()
    assert a90["estudio"]["vuelco_mm"] == pytest.approx(13.5333, abs=1e-3)


def test_sin_estudio_las_poses_no_lo_inventan(tmp_path):
    _giro(tmp_path)
    r = _web(tmp_path).get(f"/proyectos/{ID}/nodos/conjunto/poses", params={"soporte": 0})
    assert r.status_code == 200 and r.json().get("estudio") is None


def test_la_pagina_responde_las_cinco_preguntas(tmp_path):
    carpeta = _con_ensamble(tmp_path)
    _estudio_hecho(carpeta)
    html = _web(tmp_path).get(f"/p/{ID}").text
    assert "Estudio de movimientos" in html
    assert "250 g" in html and "la limita el vuelco" in html
    assert "¿Aguanta el servo?" in html and "Micro servo SG90" in html
    assert "¿Vuelca?" in html and "Alcance" in html and "Velocidades y tiempos" in html
    assert "la carga tira a lo largo: no flexa" in html
    assert f'src="/proyectos/{ID}/nodos/conjunto/alcance.png"' in html


def test_el_alcance_se_dibuja(tmp_path):
    carpeta = _con_ensamble(tmp_path)
    web = _web(tmp_path)
    assert web.get(f"/proyectos/{ID}/nodos/conjunto/alcance.png").status_code == 404
    _estudio_hecho(carpeta)
    r = web.get(f"/proyectos/{ID}/nodos/conjunto/alcance.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_un_par_pequeno_no_sale_como_cero():
    """El tilt del pan-tilt pide 0.000451 N·m = 0.0046 kgf·cm: con dos
    decimales la página decía «pide 0.00», como si no pidiera nada."""
    from orchestrator.web.paginas import _kgf_cm
    assert _kgf_cm(0.000451) == "0.0046"
    assert _kgf_cm(0.08826) == "0.9"
    assert _kgf_cm(0.17652) == "1.8"
    assert _kgf_cm(1.0787) == "11"
    assert _kgf_cm(0.0) == "0"
