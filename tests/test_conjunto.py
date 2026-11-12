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
from orchestrator.conjunto import (Articulacion, _angulos_freecad, _rodrigues, articulaciones,
                                   chocan_en, fotogramas, leer_piezas, verificar_conjunto)
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


def test_la_polea_gira_con_el_rodamiento_del_soporte(tmp_path):
    """La petición del banco: «una polea impresa que gira en ese rodamiento».
    Sin salida en la ficha del 608ZZ el conjunto solo se comprobaba en
    reposo, y el banco lo daba por «sin medir» (1110-0313). El 608ZZ va en
    (0, 0, 5) del soporte con su eje en z; la polea colocó el soporte en
    (0, 0, -12), así que el eje pasa por (0, 0, -7) de la polea, que está
    dentro de su caja. Un rodamiento gira libre: la vuelta entera."""
    rodamiento = {"nombre": "608zz", "tipo": "componente", "ficha": "608zz", "en": [0, 0, 5],
                  "giros": [], "entra_por": "+z"}
    carpeta = _obra(tmp_path, {
        "soporte": ([], [rodamiento], ([-20, -20, 0], [20, 20, 12])),
        "polea": (["soporte"], [_sobre("soporte", (0, 0, -12))], ([-15, -15, -7], [15, 15, 10])),
    })
    [a] = articulaciones(leer_piezas(carpeta, "conjunto"))
    assert (a.pieza, a.padre, a.de) == ("polea", "soporte", "608zz")
    assert a.punto == pytest.approx([0, 0, 5])
    assert a.eje == pytest.approx([0, 0, 1])
    assert a.recorrido == (0, 360)


def test_la_polea_apoyada_en_la_cara_de_arriba_del_rodamiento_gira_con_el(tmp_path):
    """La polea de verdad del banco (1110-0313) no entra en el rodamiento:
    se apoya encima. El 608ZZ va en (0, 0, 6) del soporte y ocupa hasta
    z = 13 (7 de ancho); la polea colocó el soporte en (0, 0, 22.55) volteado,
    así que en el soporte empieza en z = 13.35, a 0.35 de la cara de arriba
    del aro interior pero a 7.35 de la de abajo, que era el único punto que
    se miraba: el conjunto daba «ninguna» articulación."""
    rodamiento = {"nombre": "608zz", "tipo": "componente", "ficha": "608zz", "en": [0, 0, 6],
                  "giros": [], "entra_por": "+z"}
    volteado = {**_sobre("soporte", (0, 0, 22.55)), "giros": [["x", 180]]}
    carpeta = _obra(tmp_path, {
        "soporte": ([], [rodamiento], ([-28, -18, 0], [28, 18, 13])),
        "polea": (["soporte"], [volteado], ([-15, -15, 0], [15, 15, 9.2])),
    })
    [a] = articulaciones(leer_piezas(carpeta, "conjunto"))
    assert (a.pieza, a.padre, a.de) == ("polea", "soporte", "608zz")
    assert a.eje == pytest.approx([0, 0, 1])


# --- Lo que se ve: la animación del conjunto ------------------------------------------------

def _art(pieza, recorrido):
    return Articulacion(pieza, "base", "sg90", [0, 0, 0], [0, 0, 1], recorrido)


def test_cada_articulacion_va_de_reposo_a_un_extremo_al_otro_y_vuelve():
    """[-90, 90] de 10 en 10, contados a mano: 0, -10 … -90 son 10; -80 … 90
    son 18; 80 … 0 son 9. Total 37, y empieza y acaba en reposo."""
    cuadros = fotogramas({"brazo": _art("brazo", (-90, 90))}, paso=10)
    valores = [c["brazo"] for c in cuadros]
    assert len(valores) == 37
    assert valores[:3] == [0, -10, -20] and valores[9] == -90
    assert valores[27] == 90 and valores[-1] == 0


def test_un_rodamiento_da_una_vuelta_entera():
    """[0, 360] de 10 en 10: 0, 10 … 360, 37 cuadros, sin ir y volver."""
    valores = [c["polea"] for c in fotogramas({"polea": _art("polea", (0, 360))}, paso=10)]
    assert valores == list(range(0, 361, 10))


def test_con_dos_articulaciones_se_ve_cada_una_y_luego_las_dos_juntas():
    """Primero una (la otra quieta), luego la otra, y al final las dos a la
    vez: en el pan-tilt, la plataforma chocaba con la base solo al girar e
    inclinar juntas (2026-11-09)."""
    cuadros = fotogramas({"giro": _art("giro", (-90, 90)), "incl": _art("incl", (-90, 90))},
                         paso=10)
    assert all(c["incl"] == 0 for c in cuadros[:37])
    assert all(c["giro"] == 0 for c in cuadros[37:74])
    juntas = cuadros[74:]
    assert juntas and all(c["giro"] == c["incl"] for c in juntas)
    assert {-90, 90} <= {c["giro"] for c in juntas}


def test_el_rotulo_de_un_cuadro_cabe_en_el_dibujo():
    """El del pan-tilt del banco (2026-11-10) llevaba en una línea los
    nombres enteros de las tres piezas que chocaban y se salía por los dos
    lados: no se leía qué chocaba."""
    from orchestrator.conjunto import ANCHO_ROTULO, Pieza, rotulo
    largo = "Soporte de pan con alojamiento para SG90 de inclinación"
    piezas = {i: Pieza(i, n, None, ([0, 0, 0], [1, 1, 1])) for i, n in (
        ("base", "Base con alojamiento para SG90 de giro"), ("giro", largo),
        ("plataforma", "Plataforma para cámara pequeña"))}
    texto = rotulo(piezas, ["giro", "plataforma"], {"giro": 50.0, "plataforma": -30.0},
                   {"base", "giro", "plataforma"})
    assert all(len(linea) <= ANCHO_ROTULO for linea in texto.splitlines()), texto
    assert f"{largo} 50°" in texto and "Plataforma para cámara pequeña -30°" in texto
    assert "choca:" in texto and texto.replace("\n", " ").count("Base con alojamiento") == 1


def test_en_cada_cuadro_se_resalta_solo_lo_que_choca_en_ese_angulo():
    """Los choques del brazo y el poste, calculados a mano en el test de
    abajo: a 80° y 90°, no a 70°. Un choque entre dos piezas que no dependen
    de una articulación cuenta en cualquier ángulo de ella."""
    choques = [{"solido_a": "base", "solido_b": "brazo", "angulos": {"brazo": a}}
               for a in (80, 90)]
    choques.append({"solido_a": "base: montado", "solido_b": "tapa", "angulos": {}})
    assert chocan_en({"brazo": 80.0}, choques) == {"base", "brazo", "base: montado", "tapa"}
    assert chocan_en({"brazo": 70}, choques) == {"base: montado", "tapa"}


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

    # Y se ve: el GIF en el nodo, y en la raíz porque es el conjunto de toda
    # la obra (la web, Crafty y Telegram buscan ahí). En rojo a 80°, no a
    # -30°: en el orden de `fotogramas`, 80° es el cuadro 26 y -30°, el 3.
    from PIL import Image
    gif = carpeta / "nodos" / "conjunto" / "animation.gif"
    assert (carpeta / "animation.gif").read_bytes() == gif.read_bytes()
    with Image.open(gif) as imagen:
        assert imagen.n_frames == 37
        assert _rojos(imagen, 26) > 50
        assert _rojos(imagen, 3) == 0

    # Y para el visor de la web (F7.9 (visor)): las mismas mallas, cada una con
    # su pieza, y la articulación del brazo con su recorrido.
    ensamble = json.loads((carpeta / "nodos" / "conjunto" / "ensamble.json")
                          .read_text(encoding="utf-8"))
    assert {x["pieza"] for x in ensamble["solidos"].values()} == {"base", "brazo"}
    assert all(x["v"] and x["t"] for x in ensamble["solidos"].values())
    assert [a["recorrido"] for a in ensamble["articulaciones"]] == [[-90, 90]]


def _rojos(imagen, cuadro: int) -> int:
    """Los píxeles del rojo de un choque, con cualquier sombra."""
    imagen.seek(cuadro)
    return sum(1 for r, g, b in imagen.convert("RGB").getdata()
               if r > 100 and g < 0.35 * r and b < 0.35 * r)


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


def test_animar_una_obra_vuelve_a_mover_sus_conjuntos_sin_modelo(tmp_path, monkeypatch):
    """Los conjuntos ya verificados antes de que hubiera animación (el
    pan-tilt de la web, los del banco 1110-0313) se animan sin volver a
    diseñar nada. La verificación anterior se guarda: archivar no es borrar."""
    from types import SimpleNamespace

    from orchestrator import cli

    carpeta = _obra(tmp_path, {"base": ([], [], ([0, 0, 0], [1, 1, 1]))})
    (carpeta / "nodos" / "base" / "lista.json").write_text('{"por": "banco"}', encoding="utf-8")
    anterior = '{"ok": false, "choques": [1]}'
    (carpeta / "nodos" / "conjunto").mkdir()
    (carpeta / "nodos" / "conjunto" / "verificacion.json").write_text(anterior, encoding="utf-8")
    movidos = []
    monkeypatch.setattr("orchestrator.conjunto.verificar_conjunto",
                        lambda c, n, f, min_gap_mm: movidos.append((n, min_gap_mm)) or
                        {"ok": True, "articulaciones": [], "resumen": []})
    monkeypatch.setattr(cli, "_freecadcmd", lambda env: "freecadcmd")
    monkeypatch.setattr(cli, "_perfil", lambda raiz, env: SimpleNamespace(
        impresora=SimpleNamespace(fit_mm=lambda tipo: 0.2)))

    cli._animar(SimpleNamespace(carpeta=str(carpeta)), tmp_path, {}, "t")

    assert movidos == [("conjunto", 0.1)]
    assert (carpeta / "nodos" / "conjunto" / "verificacion-anterior.json").read_text(
        encoding="utf-8") == anterior


# --- El choque va a la pieza que lo causa (F7.7 (culpable)) ------------------------------------

def _inclina():
    """Una base de 100 × 100 con la cara de arriba en z = 0, y una placa de
    60 × 10 × 6 (z 20 a 26) que se inclina alrededor de una recta paralela a
    y que pasa por (0, 0, 25), como la plataforma del pan-tilt."""
    from orchestrator.conjunto import Pieza
    base = Pieza("base", "Base", None, ([-50, -50, -20], [50, 50, 0]))
    placa = Pieza("placa", "Plataforma", None, ([-30, -5, 20], [30, 5, 26]), padre="base",
                  al_padre=([[1, 0, 0], [0, 1, 0], [0, 0, 1]], [0, 0, 0]))
    art = Articulacion("placa", "base", "sg90", [0, 0, 25], [0, 1, 0], (-90, 90))
    return {"base": base, "placa": placa}, {"placa": art}


def test_choca_la_pieza_que_se_diseno_contra_la_otra():
    """La que va después en la obra se diseñó contra la de antes, y es la que
    puede cambiar sin deshacer nada: en el pan-tilt, la plataforma y no la
    base; el soporte de giro y no el SG90 que monta la base."""
    from orchestrator.conjunto import Pieza, culpable
    piezas = {i: Pieza(i, i, None, ([0, 0, 0], [1, 1, 1])) for i in ("base", "giro", "plataforma")}
    assert culpable(piezas, "base", "plataforma") == "plataforma"
    assert culpable(piezas, "plataforma", "base") == "plataforma"
    assert culpable(piezas, "giro", "base") == "giro"


def test_la_correccion_dice_cuanto_gira_y_donde_empieza_lo_que_choca():
    """A mano: la esquina más lejana del eje es (±30, ±5, 20), a
    √(30² + 5²) = 30.4 mm; la cara de arriba de la base está a 25 mm del
    eje, justo debajo. La corrección a mano del 9 de noviembre, la que
    arregló el pan-tilt, daba esas dos cifras."""
    from orchestrator.conjunto import correcciones
    piezas, arts = _inclina()
    choques = [{"a": "base", "b": "placa", "solido_a": "base", "solido_b": "placa",
                "angulos": {"placa": a}, "hueco_mm": -12.0} for a in (-90, -80, 80, 90)]
    [(nodo, texto)] = correcciones(piezas, arts, choques, paso=10).items()
    assert nodo == "placa"
    for parte in ("«Base»", "de -90° a -80° y de 80° a 90°", "30.4 mm", "25.0 mm"):
        assert parte in texto, (parte, texto)


# --- El sitio libre de un giro (F9.1 (barrido)) --------------------------------------------------

def _torre(h, recorrido=None, montado=None):
    """Una base de 100 × 100 con la cara de arriba en z = 30 y, encima, una
    torre con un actuador cuyo eje sale en (0, 0, h) hacia +y. Con
    `recorrido`, la torre gira sobre la base alrededor de z."""
    from orchestrator.conjunto import I3, Pieza
    base = Pieza("base", "Base", None, ([-50, -50, 0], [50, 50, 30]))
    if montado:
        base.montados = [{"tipo": "caja", "nombre": "pilar", "de": "pilar",
                          "min": montado[0], "max": montado[1]}]
    torre = Pieza("torre", "Torre", None, ([-10, -10, 30], [10, 10, h + 10]), padre="base",
                  al_padre=(I3, [0, 0, 0]))
    salida = {"de": "sg90", "nombre": "eje", "punto": [0, 0, h], "eje": [0, 1, 0],
              "recorrido": (-90, 90), "largo": 0.0}
    arts = ({"torre": Articulacion("torre", "base", "sg90", [0, 0, 30], [0, 0, 1], recorrido)}
            if recorrido else {})
    return {"base": base, "torre": torre}, arts, salida


def test_el_sitio_libre_de_un_giro_es_del_eje_a_lo_que_tiene_debajo():
    """A mano: el eje sale a 50 de altura y la base acaba en 30. Lo que gire
    alrededor de ese eje tiene 50 − 30 = 20 mm antes de tocar la base."""
    from orchestrator.conjunto import radio_libre
    piezas, arts, salida = _torre(50)
    assert radio_libre(piezas, arts, "torre", salida) == (pytest.approx(20.0), "base")


def test_el_sitio_libre_se_mide_en_todos_los_giros_de_lo_de_abajo():
    """Un pilar montado en la base, de x 40 a 50 y hasta z = 45. Con la torre
    quieta, el eje (hacia +y) pasa a √(40² + 5²) = 40.3 del pilar y manda la
    base, a 20. Si la torre gira ±90° sobre la base, a −90° el eje apunta a
    +x y pasa por encima del pilar: quedan 50 − 45 = 5 mm."""
    from orchestrator.conjunto import radio_libre
    pilar = ([40, -5, 30], [50, 5, 45])
    piezas, arts, salida = _torre(50, montado=pilar)
    assert radio_libre(piezas, arts, "torre", salida) == (pytest.approx(20.0), "base")
    piezas, arts, salida = _torre(50, recorrido=(-90, 90), montado=pilar)
    assert radio_libre(piezas, arts, "torre", salida) == (pytest.approx(5.0), "base: montado")


def test_el_sitio_libre_cuenta_desde_la_cara_de_la_salida_hacia_fuera():
    """El mismo pilar, pero detrás del actuador (y de −50 a −40): la recta
    del eje pasa a 5 mm de él, pero lo que gira va por delante de la cara de
    salida. Manda la base, a 20."""
    from orchestrator.conjunto import radio_libre
    piezas, arts, salida = _torre(50, montado=([-5, -50, 30], [5, -40, 45]))
    assert radio_libre(piezas, arts, "torre", salida) == (pytest.approx(20.0), "base")


def test_lo_que_no_tiene_nada_debajo_tiene_todo_el_sitio():
    import math

    from orchestrator.conjunto import radio_libre
    piezas, arts, salida = _torre(50)
    assert radio_libre(piezas, arts, "base", salida) == (math.inf, None)


def test_el_soporte_del_pan_tilt_dejaba_12_7_mm_para_inclinar(tmp_path):
    """Las piezas del pan-tilt del banco 1110-0313, con sus rasgos tal como
    quedaron. A mano: el SG90 del soporte saca su eje a z = 12.2 del soporte;
    el soporte se colocó a 33.6 por encima del origen de la base; y la
    carcasa del SG90 de la base acaba en 6.0 + 27.1 = 33.1. Del eje de
    inclinación al servo de abajo quedan 12.2 + 33.6 − 33.1 = 12.7 mm, y la
    plataforma que tenía que caber ahí medía 37.7."""
    from orchestrator.conjunto import radio_libre
    carpeta = _obra(tmp_path, {
        "base": ([], [_sg90((13.6, 8.8, 6.0))], ([0, 0, 0], [50, 30, 21.6])),
        "soporte": (["base"], [_sobre("base", (-19.4, -15.0, -33.6)),
                               _sg90((-13.55, -11.4, 6.0), [("x", 90), ("z", 90)])],
                    ([-18, -18, 0], [16, 18, 20])),
    })
    piezas = leer_piezas(carpeta, "conjunto")
    arts = {a.pieza: a for a in articulaciones(piezas)}
    [salida] = piezas["soporte"].salidas
    assert salida["punto"] == pytest.approx([13.55, -5.6, 12.2])
    assert radio_libre(piezas, arts, "soporte", salida) == (pytest.approx(12.7), "base: montado")


# --- Lo que va atornillado puede tocarse (banco 1112-1359) ----------------------------------

PLACA = "def construir(kit):\n    return kit.caja(40, 40, 5)\n"
TACO = "def construir(kit):\n    return kit.caja(20, 20, 4, en=(10, 10, 0))\n"


def _placa_y_taco(tmp_path, z):
    """Una placa de 40 × 40 × 5 y, atornillado encima, un taco de 20 × 20 × 4
    que colocó la placa en z = `z`: sin servo, no hay giro entre los dos."""
    _obra(tmp_path, {"placa": ([], [], ([0, 0, 0], [1, 1, 1])),
                     "taco": (["placa"], [], ([0, 0, 0], [1, 1, 1]))})
    _construida(tmp_path, "placa", PLACA)
    _construida(tmp_path, "taco", TACO, [_sobre("placa", (0, 0, z))])
    return tmp_path


def test_dos_piezas_atornilladas_una_a_otra_pueden_tocarse(tmp_path):
    """La pinza del banco 1112-1359 «chocaba en reposo» con la plataforma a
    la que va atornillada: quedaban a 0.00 mm, apoyada una en la otra, y la
    holgura que se pide entre lo que se mueve es de 0.1. Entre dos piezas
    sin ningún giro por medio no hay nada que pueda rozar al moverse. Aquí
    el taco apoya en la cara de arriba de la placa (z = 5): 0 mm."""
    v = verificar_conjunto(_placa_y_taco(tmp_path, z=-5), "conjunto", _freecadcmd(),
                           min_gap_mm=0.2, animar=False)
    assert v["ok"], v["resumen"]


def test_dos_piezas_atornilladas_no_pueden_atravesarse(tmp_path):
    """Tocarse sí, meterse una en otra no. Con la placa colocada 1 mm más
    arriba, el taco se hunde 1 mm en ella: 20 · 20 · 1 = 400 mm³."""
    v = verificar_conjunto(_placa_y_taco(tmp_path, z=-4), "conjunto", _freecadcmd(),
                           min_gap_mm=0.2, animar=False)
    assert not v["ok"]
    [c] = v["choques"]
    assert c["hueco_mm"] == pytest.approx(-400, abs=1)
    assert "en reposo" in v["resumen"][0] and "400.0 mm³" in v["resumen"][0]
