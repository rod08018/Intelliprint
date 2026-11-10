"""El estudio de movimientos de un robot (F7.10 (estudio)).

«Lo que sí quiero es el estudio de movimientos, eso sí me lo debe dar» (el
usuario, 2026-11-10, al sacar ROS y Gazebo de Intelliprint): ¿aguanta el
servo?, ¿vuelca?, alcance, velocidades y tiempos, carga máxima. Cada cifra
esperada está calculada a mano en el docstring de su test.
"""

import json

import pytest

from tests.test_tornilleria import _caja_stl

LAMINADO = {"perimeters": "2", "external_perimeter_extrusion_width": "0.5",
            "perimeter_extrusion_width": "0.5", "layer_height": "0.2",
            "top_solid_layers": "5", "bottom_solid_layers": "5", "fill_density": "20%"}


def _cubo(tmp_path, lado=10):
    ruta = tmp_path / "cubo.stl"
    ruta.write_text("solid c\n" + _caja_stl((0, 0, 0), (lado, lado, lado)) + "endsolid c\n",
                    encoding="utf-8")
    return ruta


# --- las masas ------------------------------------------------------------------------------


def test_volumen_area_y_centro_de_un_cubo(tmp_path):
    """Un cubo de 10: 1000 mm³, 600 mm² (400 de lados, 100 arriba, 100
    abajo) y el centro en (5, 5, 5)."""
    from orchestrator.estudio import malla
    m = malla(_cubo(tmp_path))
    assert m.volumen_mm3 == pytest.approx(1000)
    assert (m.lados_mm2, m.arriba_mm2, m.abajo_mm2) == pytest.approx((400, 100, 100))
    assert m.centro == pytest.approx([5, 5, 5])


def test_la_masa_impresa_es_cascara_mas_relleno(tmp_path):
    """Dos perímetros de 0.5 dan 1 mm de pared: 400 mm³ en los lados. Cinco
    capas de 0.2 arriba y cinco abajo: 1 mm, 100 + 100 mm³. Cáscara, 600;
    el interior, (1000 − 600) × 20 % = 80. Son 680 mm³ de PLA a 1.24 g/cm³:
    0.8432 g."""
    from orchestrator.estudio import malla, masa_impresa
    assert masa_impresa(malla(_cubo(tmp_path)), LAMINADO, 1.24) == pytest.approx(0.8432)


def test_si_la_pieza_se_lamino_manda_el_peso_de_prusaslicer(tmp_path):
    """La base del pan-tilt se laminó (`fabrication/slicing_report.json`):
    19.93 g. Lo que dice PrusaSlicer pesa más que cualquier estimación."""
    from orchestrator.estudio import masa_de_parte
    parte = tmp_path / "nodos" / "base" / "parts" / "base"
    parte.mkdir(parents=True)
    _cubo(parte)
    fab = tmp_path / "nodos" / "base" / "fabrication"
    fab.mkdir()
    (fab / "slicing_report.json").write_text(json.dumps({"grams": 19.93}), encoding="utf-8")
    m = masa_de_parte(parte, LAMINADO, 1.24)
    assert (m.g, m.de) == (19.93, "PrusaSlicer")
    assert m.centro == pytest.approx([5, 5, 5])


def test_sin_laminar_la_masa_es_una_estimacion_del_lado_pesado_y_lo_dice(tmp_path):
    """Contra 40 piezas laminadas, PrusaSlicer pesó hasta 1.25 veces la
    estimación (nunca menos): los 0.8432 g del cubo se cuentan como
    0.8432 / 0.80 = 1.054 g."""
    from orchestrator.estudio import masa_de_parte
    parte = tmp_path / "parts" / "cubo"
    parte.mkdir(parents=True)
    _cubo(parte)
    m = masa_de_parte(parte, LAMINADO, 1.24)
    assert m.g == pytest.approx(1.054)
    assert m.de == "estimada"


# --- las respuestas -------------------------------------------------------------------------


def test_el_par_de_un_brazo_horizontal_y_el_de_uno_vertical():
    """Un brazo de 100 mm y 20 g sobre un eje horizontal (y) en el origen:
    su centro a 50 mm. Horizontal: 0.020 kg × 9.80665 × 0.050 m = 0.0098 N·m.
    Girado 90°, el centro queda encima del eje: 0."""
    from orchestrator.estudio import par_por_gravedad
    assert abs(par_por_gravedad([(20, [50, 0, 0])], [0, 0, 0], [0, 1, 0])) == \
        pytest.approx(0.0098067, rel=1e-4)
    assert par_por_gravedad([(20, [0, 0, 50])], [0, 0, 0], [0, 1, 0]) == pytest.approx(0, abs=1e-12)


def test_un_eje_vertical_no_carga_peso():
    """El pan de un pan-tilt: lo que gira alrededor de un eje vertical no
    pide par al servo para sostenerse, esté donde esté."""
    from orchestrator.estudio import par_por_gravedad
    assert par_por_gravedad([(50, [80, 30, 40])], [0, 0, 0], [0, 0, 1]) == pytest.approx(0, abs=1e-12)


def test_la_carga_que_aguanta_un_servo_en_la_punta_del_brazo():
    """El SG90, 0.18 N·m de bloqueo; al 50 %, 0.09. El brazo ya pide
    0.0098; lo que queda, en la punta a 100 mm:
    (0.09 − 0.0098067) / (9.80665 × 0.100) = 0.08177 kg = 81.8 g."""
    from orchestrator.estudio import carga_que_aguanta
    assert carga_que_aguanta(0.09, 0.0098067, 0.100) == pytest.approx(81.77, abs=0.01)


def test_el_vuelco_es_la_distancia_del_centro_de_masas_al_borde_del_apoyo():
    """Un apoyo de 40 × 20. Con el centro de masas en (30, 10) queda a 10
    del borde de x = 40; en (45, 10) se ha salido 5: vuelca."""
    from orchestrator.estudio import margen_de_vuelco
    apoyo = [(0, 0), (40, 0), (40, 20), (0, 20)]
    assert margen_de_vuelco([30, 10], apoyo) == pytest.approx(10)
    assert margen_de_vuelco([45, 10], apoyo) == pytest.approx(-5)


def test_tiempo_de_un_recorrido_con_y_sin_carga():
    """180° a 0.1 s/60° son 0.3 s en vacío. Con la recta par-velocidad, al
    50 % del par de bloqueo va a la mitad de velocidad: 0.6 s."""
    from orchestrator.estudio import tiempo_de_recorrido
    assert tiempo_de_recorrido(180, 0.1, 0, 0.18) == pytest.approx(0.3)
    assert tiempo_de_recorrido(180, 0.1, 0.09, 0.18) == pytest.approx(0.6)


# --- el estudio de un conjunto --------------------------------------------------------------


def _brazo_en_voladizo(tmp_path):
    """Un soporte de 56 × 34.5 apoyado en z = 0 con un SG90 tumbado (como el
    del pan-tilt): su eje sale en (0, 0, 25), en horizontal (−y). Encima, un
    brazo de 100 × 5 × 10 que sale en x desde el eje. Pesos de PrusaSlicer:
    soporte 30 g, brazo 20 g."""
    from tests.test_conjunto import _obra, _sg90, _sobre
    girado = ((-5.8, 27.1, 18.8), [("x", 90)])
    cajas = {"soporte": ((-28, -17, 0), (28, 17.5, 31.5)), "brazo": ((0, -6, 20), (100, -1, 30))}
    carpeta = _obra(tmp_path, {
        "soporte": ([], [_sg90(*girado)], [list(c) for c in cajas["soporte"]]),
        "brazo": (["soporte"], [_sobre("soporte", (0, 0, 0))], [list(c) for c in cajas["brazo"]]),
    })
    for i, (a, b) in cajas.items():
        parte = carpeta / "nodos" / i / "parts" / i
        (parte / f"{i}.stl").write_text("solid p\n" + _caja_stl(a, b) + "endsolid p\n",
                                        encoding="utf-8")
        (carpeta / "nodos" / i / "fabrication").mkdir()
        (carpeta / "nodos" / i / "fabrication" / "slicing_report.json").write_text(
            json.dumps({"grams": {"soporte": 30, "brazo": 20}[i]}), encoding="utf-8")
    return carpeta


def test_el_estudio_de_un_brazo_en_voladizo(tmp_path):
    """Calculado a mano:

    - ¿Aguanta el servo? El brazo (20 g, centro a 50 mm del eje) pide
      0.020 × 9.80665 × 0.050 = 0.0098 N·m en horizontal, a 0°. El SG90 da
      0.17652 a 4.8 V (el invento no dice su tensión: la más baja de la
      hoja); al 50 %, 0.08826. Aguanta.
    - La carga en la punta (x = 100): (0.08826 − 0.0098067) / (9.80665 ×
      0.100) = 0.0800 kg, 80.0 g, lo que deja el servo.
    - ¿Vuelca? Centros en x: soporte 0 (30 g), SG90 5.6 (9 g, el centro de
      sus cajas de la ficha), brazo 50 (20 g): Σm·x = 1050.4 g·mm sobre
      59 g, x = 17.8, dentro del apoyo (x ≤ 28): 10.2 mm de margen. Con c
      gramos en x = 100 vuelca cuando (1050.4 + 100c) / (59 + c) = 28:
      c = (28 × 59 − 1050.4) / 72 = 8.36 g. Vuelca antes de que el servo
      ceda: la carga máxima del sistema es 8.4 g, por vuelco."""
    from orchestrator.estudio import estudiar
    e = estudiar(_brazo_en_voladizo(tmp_path), "conjunto")
    [s] = e["servos"]
    assert s["pieza"] == "brazo" and s["tension_V"] == 4.8
    assert s["par_max_Nm"] == pytest.approx(0.0098067, rel=1e-3)
    assert s["angulo_peor"] == 0
    assert s["par_disponible_Nm"] == pytest.approx(0.08826, rel=1e-3)
    assert s["aguanta"] is True
    assert s["carga_max_g"] == pytest.approx(80.0, abs=0.1)
    assert e["vuelco"]["margen_mm"] == pytest.approx(10.2, abs=0.05)
    assert e["vuelco"]["carga_max_g"] == pytest.approx(8.36, abs=0.05)
    assert (e["carga_max"]["g"], e["carga_max"]["limita"]) == (pytest.approx(8.36, abs=0.05), "vuelco")


def test_el_estudio_dice_alcance_y_tiempos(tmp_path):
    """La punta del brazo (100, −1, 30) está a √(100² + 5²) = 100.1 mm del
    eje. El SG90 recorre sus 180° en 3 × 0.1 = 0.3 s en vacío; con el
    brazo, que pide 0.0098 de 0.17652, va un 5.6 % más lento: 0.3176 s."""
    from orchestrator.estudio import estudiar
    e = estudiar(_brazo_en_voladizo(tmp_path), "conjunto")
    assert e["alcance"]["radio_mm"] == pytest.approx(100.12, abs=0.01)
    [s] = e["servos"]
    assert s["tiempo_s"] == pytest.approx(0.3 / (1 - 0.0098067 / 0.17652), rel=1e-3)


# --- la carga que aguanta el material (FreeCAD) ---------------------------------------------


def test_la_carga_que_aguanta_una_barra_en_voladizo(tmp_path):
    """Una barra de 100 × 10 × 10 en x, cargada en la punta hacia −z.
    I = 10·10³/12 = 833.3 mm⁴, c = 5. El primer corte (de 30) está a
    100/30 = 3.33 mm del arranque: M = F·96.67. Tumbada, el brazo va en el
    plano de capa: 35 MPa entre el factor 3, 11.67 MPa. F = 11.67 × 833.3 /
    (5 × 96.67) = 20.1 N."""
    from tests.test_generators import _freecadcmd
    if _freecadcmd() is None:
        pytest.skip("sin freecadcmd")
    from orchestrator.build import build_part
    from orchestrator.estudio import resistencia_de_tramos
    from orchestrator.schemas.programa import Programa
    from tests.test_sondas import PERFIL, MATERIAL
    build_part(Programa(part="p", codigo="def construir(kit):\n    return kit.caja(100, 10, 10)\n"),
               None, tmp_path, _freecadcmd(), perfil=PERFIL)
    [r] = resistencia_de_tramos(tmp_path / "p.step", [
        {"desde": [0, 5, 5], "hasta": [100, 5, 5], "gravedad": [0, 0, -1]}], _freecadcmd(), MATERIAL)
    assert r["N_max"] == pytest.approx(20.11, rel=0.01)


def test_el_material_resta_lo_que_ya_cuelga_y_el_peso_propio(tmp_path, monkeypatch):
    """Si el corte peor del brazo aguanta 1 N en la punta: 1 / 9.80665 =
    101.97 g. El brazo (20 g) tiene el centro a medio camino del eje a la
    punta: pesa en ella como 10 g. Quedan 91.97 g. El sistema sigue
    limitado por el vuelco (8.36 g), que es menos."""
    from orchestrator import estudio
    llamadas = []

    def falsa(step, tramos, freecadcmd, material):
        # La sección no flexa igual hacia todos lados: se prueba cada
        # dirección de la gravedad que ve la pieza y manda la peor (la última).
        llamadas.append(tramos)
        return [{"N_max": 1.0 + len(tramos) - 1 - i, "detalle": "x"} for i in range(len(tramos))]
    monkeypatch.setattr(estudio, "resistencia_de_tramos", falsa)
    carpeta = _brazo_en_voladizo(tmp_path)
    e = estudio.escribir_estudio(carpeta, "conjunto", "freecadcmd")
    [m] = e["material"]
    assert m["pieza"] == "brazo"
    assert m["carga_max_g"] == pytest.approx(91.97, abs=0.05)
    [tramos] = llamadas
    assert len(tramos) > 1
    assert all(t["desde"] == pytest.approx([0, 0, 25]) for t in tramos)
    assert e["carga_max"]["limita"] == "vuelco"
    assert json.loads((carpeta / "nodos" / "conjunto" / "estudio.json").read_text(
        encoding="utf-8"))["carga_max"]["g"] == pytest.approx(8.36, abs=0.05)


def test_el_estudio_se_lee_en_castellano(tmp_path):
    """El `estudio.md` responde a las cinco preguntas con las cifras del
    `estudio.json`: el SG90 del brazo aguanta, la base vuelca con 8.4 g
    (no va atornillada), el alcance es de 100.1 mm y no hay FreeCAD."""
    from orchestrator import estudio
    carpeta = _brazo_en_voladizo(tmp_path)
    e = estudio.escribir_estudio(carpeta, "conjunto", None)
    md = (carpeta / "nodos" / "conjunto" / "estudio.md").read_text(encoding="utf-8")
    assert "## ¿Aguanta el servo?" in md
    assert "Sí" in md and "SG90" in md
    assert "## ¿Vuelca?" in md and "8.4 g" in md
    assert "## Alcance" in md and "100.1 mm" in md
    assert "## Velocidades y tiempos" in md
    assert "## Carga máxima" in md and "vuelco" in md
    assert "Sin FreeCAD no se mide la resistencia del material." in md
    assert e["carga_max"]["g"] == pytest.approx(8.36, abs=0.05)


def test_la_cli_estudia_los_conjuntos_que_se_mueven(tmp_path, monkeypatch, capsys):
    """`intelliprint estudio <carpeta>` estudia los conjuntos verificados (o
    con choques: se mueven igual) y deja los que aún no se han movido."""
    from types import SimpleNamespace

    from orchestrator import cli, estudio
    hechos = []
    monkeypatch.setattr("orchestrator.obra.estados", lambda c: {
        "base": "lista", "conjunto": "verificado", "otro": "con choques", "nuevo": "por verificar"})
    monkeypatch.setattr(estudio, "escribir_estudio", lambda c, n, f, raiz=None: hechos.append((n, f)) or {
        "carga_max": {"g": 8.4, "limita": "vuelco"},
        "servos": [{"nombre": "Brazo", "servo": "SG90", "aguanta": True}]})
    monkeypatch.setattr(cli, "_freecadcmd", lambda env: "freecadcmd")
    assert cli._parser().parse_args(["estudio", str(tmp_path)]).comando == "estudio"
    cli._estudio(SimpleNamespace(carpeta=str(tmp_path)), tmp_path, {}, "t")
    assert hechos == [("conjunto", "freecadcmd"), ("otro", "freecadcmd")]
    salida = capsys.readouterr().out
    assert "8.4 g" in salida and "vuelco" in salida and "SG90 aguanta" in salida


def test_en_cada_pose_el_par_sale_del_estudio_guardado(tmp_path):
    """El visor no recalcula las masas (las mallas del pan-tilt pesan 200
    MB): toma las del `estudio.json`. A 0° el brazo, 20 g a 50 mm, pide
    0.02 × 9.80665 × 0.05 = 0.0098067 N·m de los 0.08826 disponibles."""
    from orchestrator import estudio
    carpeta = _brazo_en_voladizo(tmp_path)
    assert estudio.en_la_pose(carpeta, "conjunto", {"brazo": 0}) is None
    estudio.escribir_estudio(carpeta, "conjunto", None)
    p = estudio.en_la_pose(carpeta, "conjunto", {"brazo": 0})
    assert p["pares"]["brazo"]["Nm"] == pytest.approx(0.0098067, abs=2e-6)
    assert p["pares"]["brazo"]["uso"] == pytest.approx(0.0098067 / 0.08826, abs=1e-4)


def test_un_vertice_repetido_no_pega_el_centro_al_borde():
    """El apoyo del pan-tilt, redondeado a centésimas para guardarlo, traía
    vértices repetidos: un lado de largo cero da distancia cero, y el visor
    decía «a 0.0 mm del borde» en todas las poses (el estudio, 5.4)."""
    from orchestrator.estudio import margen_de_vuelco
    cuadrado = [(0, 0), (20, 0), (20, 20), (0, 20)]
    repetido = [(0, 0), (20, 0), (20, 0), (20, 20), (0, 20)]
    assert margen_de_vuelco([5, 10], repetido) == pytest.approx(5)
    assert margen_de_vuelco([25, 10], repetido) == pytest.approx(margen_de_vuelco([25, 10], cuadrado))


def test_el_apoyo_guardado_sigue_siendo_convexo():
    """El apoyo del pan-tilt tiene 344 vértices a menos de medio milímetro
    unos de otros. Redondeados a centésimas, alguno se mete hacia dentro, y
    la recta de ese lado diminuto pasa más cerca del centro que el borde: el
    visor daba 5.1 mm donde el estudio, 5.4. Un círculo de 30 mm de radio,
    con 2000 vértices, debe seguir a 30 mm de su centro."""
    import math

    from orchestrator.estudio import apoyo_para_guardar, margen_de_vuelco
    circulo = [(30 * math.cos(2 * math.pi * k / 2000) + 0.123456,
                30 * math.sin(2 * math.pi * k / 2000) - 0.654321) for k in range(2000)]
    guardado = [tuple(p) for p in apoyo_para_guardar(circulo)]
    assert margen_de_vuelco([0.123456, -0.654321], guardado) == pytest.approx(30, abs=0.01)
