"""Un conjunto de la obra se verifica moviéndolo (F7.4 (conjunto)).

Hasta ahora el nodo «conjunto» del pan-tilt decía «su verificación aún no
existe»: cada pieza se medía sola, y nadie movía el giro y la inclinación
para ver si algo choca. La cinemática no se le pide a un modelo: sale de la
geometría que ya existe.

- Qué gira y alrededor de qué: cada pieza guarda dónde colocó la pieza de la
  obra sobre la que va (sus rasgos), y el SG90 de esa pieza tiene su eje de
  salida en la ficha. La pieza que toca ese eje gira con él.
- Cuánto: el recorrido de la ficha. El del SG90 sale de su hoja de datos:
  «approximately 180 degrees (90 in each direction)».
- Qué choca: las piezas construidas y los cuerpos de los servos, movidos en
  FreeCAD por todo el recorrido.

Los esperados están calculados a mano en cada test.
"""

import json

import pytest

from mech_toolkit.geometry import _rotacion
from orchestrator.conjunto import (_angulos_freecad, _rodrigues, articulaciones, leer_piezas,
                                   verificar_conjunto)
from orchestrator.build import build_part
from orchestrator.schemas.programa import Programa
from tests.test_generators import _freecadcmd
from tests.test_sondas import PERFIL


@pytest.mark.parametrize("rx, ry, rz", [(0, 0, 0), (30, -20, 75), (90, 0, 0), (-90, 45, 180),
                                        (10, 90, 0), (0, -90, 30), (170, 10, -100)])
def test_un_giro_vuelve_a_los_angulos_que_entiende_freecad(rx, ry, rz):
    """El ensamble coloca cada pieza con (rx, ry, rz) y R = Rz·Ry·Rx. Con la
    inclinación a ±90° hay bloqueo de cardán: los ángulos pueden salir otros,
    pero el giro tiene que ser el mismo."""
    r = _rotacion(rx, ry, rz)
    vuelta = _rotacion(*_angulos_freecad(r))
    assert sum(vuelta, []) == pytest.approx(sum(r, []), abs=1e-9)


def test_girar_alrededor_de_un_eje_cualquiera():
    """90° alrededor de +z lleva x a y; alrededor de -y, x a +z (mano derecha)."""
    assert [fila[0] for fila in _rodrigues([0, 0, 1], 90)] == pytest.approx([0, 1, 0], abs=1e-12)
    assert [fila[0] for fila in _rodrigues([0, -1, 0], 90)] == pytest.approx([0, 0, 1], abs=1e-12)


# --- Una obra de prueba, sin FreeCAD ----------------------------------------------------

def _obra(tmp_path, piezas: dict, conjunto="conjunto"):
    """`piezas`: id -> (depende_de, rasgos, envolvente)."""
    nodos = [{"id": i, "nombre": f"Pieza {i}", "tipo": "pieza", "que_hace": "x",
              "depende_de": dep} for i, (dep, _, _) in piezas.items()]
    nodos.append({"id": conjunto, "nombre": "El conjunto", "tipo": "conjunto", "que_hace": "x",
                  "depende_de": list(piezas)})
    (tmp_path / "obra.json").write_text(json.dumps({"titulo": "t", "nodos": nodos}),
                                        encoding="utf-8")
    for i, (_, rasgos, (a, b)) in piezas.items():
        parte = tmp_path / "nodos" / i / "parts" / i
        parte.mkdir(parents=True)
        (parte / "rasgos.json").write_text(json.dumps(rasgos), encoding="utf-8")
        (parte / "envolvente.json").write_text(json.dumps({"min": a, "max": b}), encoding="utf-8")
        (parte / f"{i}.step").write_text("STEP", encoding="utf-8")
    return tmp_path


def _sg90(en, giros=()):
    return {"nombre": "sg90", "tipo": "componente", "ficha": "sg90", "en": list(en),
            "giros": [list(g) for g in giros], "entra_por": "+z"}


def _sobre(nodo, en):
    return {"nombre": f"obra-{nodo}", "tipo": "componente", "ficha": f"obra-{nodo}",
            "en": list(en), "giros": [], "entra_por": "-z"}


def test_la_pieza_de_encima_gira_con_el_eje_del_servo_de_la_de_abajo(tmp_path):
    """Como la base y el soporte de giro del pan-tilt: el SG90 de la base va
    en (23.6, 6, 0), así que su eje (5.8, 6.2 en la ficha, sale de la
    carcasa a 27.1) está en (29.4, 12.2, 27.1) del marco de la base. El
    soporte colocó la base en (-29.4, -12.2, -27.6): está 0.5 por encima."""
    carpeta = _obra(tmp_path, {
        "base": ([], [_sg90((23.6, 6, 0))], ([0, 0, 0], [70, 34, 18.5])),
        "soporte": (["base"], [_sobre("base", (-29.4, -12.2, -27.6))],
                    ([-28, -17, 0], [28, 17, 31])),
    })
    [a] = articulaciones(leer_piezas(carpeta, "conjunto"))
    assert (a.pieza, a.padre, a.de) == ("soporte", "base", "sg90")
    assert a.punto == pytest.approx([29.4, 12.2, 27.1])
    assert a.eje == pytest.approx([0, 0, 1])
    assert a.recorrido == (-90, 90)


def test_el_servo_que_coloca_la_pieza_de_arriba_es_de_la_de_abajo(tmp_path):
    """La plataforma del pan-tilt coloca también el SG90 superior, en el
    mismo sitio que el soporte, para dejarle hueco. Es del soporte: si fuera
    de la plataforma, giraría con ella y «chocaría» con su propio alojamiento."""
    girado = ((-5.8, 27.1, 18.8), [("x", 90)])
    carpeta = _obra(tmp_path, {
        "soporte": ([], [_sg90(*girado)], ([-28, -17, 0], [28, 17.5, 31.5])),
        "plataforma": (["soporte"], [_sg90(*girado), _sobre("soporte", (0, 0, 0))],
                       ([-25, -70, 0], [25, -1, 31])),
    })
    piezas = leer_piezas(carpeta, "conjunto")
    assert [m["de"] for m in piezas["soporte"].montados] == ["sg90", "sg90"]   # cuerpo y orejas
    assert piezas["plataforma"].montados == []
    [a] = articulaciones(piezas)
    # El eje del SG90 girado x+90: (5.8, 6.2, 27.1) -> (5.8, -27.1, 6.2) + en.
    assert a.punto == pytest.approx([0, 0, 25])
    assert a.eje == pytest.approx([0, -1, 0])


def test_una_pieza_que_no_toca_el_eje_va_fija(tmp_path):
    """Una tapa atornillada a un lado de la base no gira con su servo."""
    carpeta = _obra(tmp_path, {
        "base": ([], [_sg90((23.6, 6, 0))], ([0, 0, 0], [70, 34, 18.5])),
        "tapa": (["base"], [_sobre("base", (0, 0, 0))], ([-10, 0, 0], [-2, 34, 18])),
    })
    assert articulaciones(leer_piezas(carpeta, "conjunto")) == []


# --- Moviéndolo de verdad, con FreeCAD -----------------------------------------------------

BASE = """
def construir(kit):
    placa = kit.caja(160, 160, 5, en=(-80, -80, 0))
    poste = kit.caja(10, 10, 40, en=({x0}, {y0}, 5))
    return placa + poste
"""
BRAZO = "def construir(kit):\n    return kit.caja(50, 6, 3, en=(-3, -3, 0))\n"


def _construida(tmp_path, nodo, codigo, extra=()):
    parte = tmp_path / "nodos" / nodo / "parts" / nodo
    build_part(Programa(part=nodo, codigo=codigo), None, parte, _freecadcmd(), perfil=PERFIL)
    rasgos = json.loads((parte / "rasgos.json").read_text(encoding="utf-8"))
    (parte / "rasgos.json").write_text(json.dumps(rasgos + list(extra)), encoding="utf-8")


def _brazo_y_poste(tmp_path, x0, y0):
    """Un SG90 en la base con el eje en (0, 0) y la carcasa hasta z = 32.1;
    un brazo de 50 × 6 × 3 que sale de su eje hacia +x, de z 35 a 38; y un
    poste de 10 × 10 que sube de 5 a 45."""
    _obra(tmp_path, {"base": ([], [], ([0, 0, 0], [1, 1, 1])),
                     "brazo": (["base"], [], ([0, 0, 0], [1, 1, 1]))})
    _construida(tmp_path, "base", BASE.format(x0=x0, y0=y0), [_sg90((-5.8, -6.2, 5))])
    _construida(tmp_path, "brazo", BRAZO, [_sobre("base", (0, 0, -35))])
    return tmp_path


def test_el_brazo_que_choca_con_el_poste_al_girar_se_ve_en_que_angulos(tmp_path):
    """El poste está en x -5..5, y 30..40, en el camino del brazo hacia los
    90°. A mano, a ángulo θ el canto del poste más cercano al brazo es
    (5, 30), a |-5·sen θ + 30·cos θ| de su línea, y el brazo tiene 3 de medio
    ancho: a 70° quedan 5.56 - 3 = 2.6 mm; a 80°, 0.29 - 3 < 0, choca; a 90°
    el brazo pasa por encima del poste. De 10 en 10, chocan 80° y 90°."""
    carpeta = _brazo_y_poste(tmp_path, x0=-5, y0=30)
    v = verificar_conjunto(carpeta, "conjunto", _freecadcmd(), min_gap_mm=0.2)

    assert not v["ok"]
    chocan = sorted({c["angulos"]["brazo"] for c in v["choques"]
                     if {c["a"], c["b"]} == {"brazo", "base"}})
    assert chocan == [80, 90]
    assert any("Pieza brazo" in r and "Pieza base" in r and "80°" in r and "90°" in r
               for r in v["resumen"]), v["resumen"]
    assert json.loads((carpeta / "nodos" / "conjunto" / "verificacion.json")
                      .read_text(encoding="utf-8"))["ok"] is False


def test_los_angulos_de_un_choque_salen_por_tramos_y_no_de_punta_a_punta():
    """El pan-tilt (2026-11-09) chocaba con la inclinación en ±40–50°, y el
    resumen decía «girada de -50° a 50°»: parecía que chocaba también en
    reposo. Con paso 10, {-50, -40, 40, 50} son dos tramos. Y «la base y la
    plataforma chocan con la plataforma girada…» se leía como si la
    plataforma chocara consigo misma: los ángulos van tras un «si»."""
    from orchestrator.conjunto import Pieza, _resumen
    piezas = {i: Pieza(i, n, None, ([0, 0, 0], [1, 1, 1])) for i, n in
              (("base", "Base"), ("plataforma", "Plataforma"))}
    choques = [{"solido_a": "base", "solido_b": "plataforma", "a": "base", "b": "plataforma",
                "angulos": {"plataforma": a}, "hueco_mm": -1.0} for a in (-50, -40, 40, 50)]
    [linea] = _resumen(piezas, choques, paso=10)
    assert "chocan si «Plataforma» está girada de -50° a -40° y de 40° a 50°" in linea


def test_el_brazo_que_no_llega_al_poste_se_mueve_libre(tmp_path):
    """Con el poste a 60 del eje, el brazo (50 de largo) no lo alcanza en
    ningún ángulo; la carcasa del servo queda 2.9 por debajo del brazo."""
    carpeta = _brazo_y_poste(tmp_path, x0=-5, y0=60)
    v = verificar_conjunto(carpeta, "conjunto", _freecadcmd(), min_gap_mm=0.2)
    assert v["ok"], v["resumen"]
    assert v["choques"] == []
