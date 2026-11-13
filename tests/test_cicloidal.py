"""La reductora cicloidal (F10.7 (cicloidal), ADR-021).

El disco, los pernos y la excéntrica salen de una fórmula: no los dibuja
ningún modelo. Los oráculos son de fuera del sistema:

- **El perfil del disco**, de «What is Cycloidal Drive? Designing, 3D
  Printing and Testing» (howtomechatronics.com), tal como lo escribe:

      x = (R*cos(t))-(Rr*cos(t+arctan(sin((1-N)*t)/((R/(E*N))-cos((1-N)*t)))))-(E*cos(N*t))
      y = (-R*sin(t))+(Rr*sin(t+arctan(sin((1-N)*t)/((R/(E*N))-cos((1-N)*t)))))+(E*sin(N*t))

  con N el número de pernos, Rr su radio, R el radio del círculo en el que
  van y E la excentricidad. Su ejemplo: N = 16, Rr = 6,5, R = 45, E = 1,5,
  «16 rollers for a 15:1 ratio».
- **La relación**, del mismo sitio: el disco tiene «one less cycloidal lobe»
  que pernos el anillo, y eso es la reducción. Aquí se cuenta en el perfil.
- **Que no se atraviesan**, con geometría: en cada ángulo de la excéntrica,
  la distancia de cada perno al disco.
"""

import math

import pytest

EJEMPLO = dict(pernos=16, radio=45.0, radio_perno=6.5, excentricidad=1.5)


def _publicada(t, N, R, Rr, E):
    """La fórmula del artículo, copiada símbolo a símbolo."""
    psi = math.atan(math.sin((1 - N) * t) / ((R / (E * N)) - math.cos((1 - N) * t)))
    return ((R * math.cos(t)) - (Rr * math.cos(t + psi)) - (E * math.cos(N * t)),
            (-R * math.sin(t)) + (Rr * math.sin(t + psi)) + (E * math.sin(N * t)))


def test_el_perfil_es_el_de_la_formula_publicada_punto_a_punto():
    from mech_toolkit.cicloidal import perfil
    puntos = perfil(**EJEMPLO, puntos=720)
    assert len(puntos) == 720
    for k in (0, 1, 37, 180, 359, 500, 719):
        t = 2 * math.pi * k / 720
        assert puntos[k] == pytest.approx(_publicada(t, 16, 45.0, 6.5, 1.5), abs=1e-9)


def test_la_relacion_se_cuenta_en_los_lobulos_del_disco():
    """16 pernos: 15 lóbulos, 15:1. Un lóbulo es un máximo de la distancia
    al centro al recorrer el perfil."""
    from mech_toolkit.cicloidal import perfil, relacion
    radios = [math.hypot(x, y) for x, y in perfil(**EJEMPLO, puntos=3600)]
    lobulos = sum(1 for k in range(3600)
                  if radios[k - 1] < radios[k] >= radios[(k + 1) % 3600])
    assert lobulos == 15 == relacion(16)


def test_el_disco_roza_los_pernos_sin_atravesarlos_en_toda_la_vuelta():
    """La excéntrica da una vuelta entera, de 5° en 5°. El disco va con su
    centro a E del eje y gira al revés, 1/15 de lo que gira la excéntrica.
    En cada ángulo, lo que más se acerca a un perno es rozarlo: ni lo
    atraviesa ni se separa de todos."""
    from mech_toolkit.cicloidal import holgura_con_los_pernos
    for grados in range(0, 360, 5):
        h = holgura_con_los_pernos(**EJEMPLO, giro_excentrica=math.radians(grados))
        assert -0.02 < h < 0.02, (grados, h)


def test_con_holgura_de_impresion_queda_esa_holgura():
    """El disco se encoge 0,15 mm por todo su contorno: es lo que queda
    entre él y el perno más cercano."""
    from mech_toolkit.cicloidal import holgura_con_los_pernos
    for grados in (0, 45, 200):
        h = holgura_con_los_pernos(**EJEMPLO, holgura=0.15, giro_excentrica=math.radians(grados))
        assert h == pytest.approx(0.15, abs=0.02)


def test_si_el_disco_girase_otra_cosa_atravesaria_los_pernos():
    """Lo que hace que la relación sea 15:1 y no otra: con el disco girando
    1/16 de vuelta por vuelta de la excéntrica, a media vuelta ya se ha
    metido en los pernos."""
    from mech_toolkit.cicloidal import holgura_con_los_pernos
    peor = min(holgura_con_los_pernos(**EJEMPLO, giro_excentrica=math.radians(g),
                                      giro_del_disco=-math.radians(g) / 16)
               for g in range(0, 360 * 8, 10))
    assert peor < -0.1


@pytest.mark.parametrize("cambio, dice", [
    # «The eccentricity value should be smaller than half of the roller diameter».
    (dict(excentricidad=7.0), "excentricidad"),
    # Con E·N ≥ R el perfil se cruza consigo mismo: 3 × 16 = 48 > 45.
    (dict(excentricidad=3.0), "se cruza"),
    (dict(pernos=3), "pernos"),
])
def test_unos_parametros_que_no_dan_un_disco_se_rechazan(cambio, dice):
    from mech_toolkit.cicloidal import perfil
    with pytest.raises(ValueError, match=dice):
        perfil(**{**EJEMPLO, **cambio})


# --- el módulo: cinco piezas para un NEMA 17 -------------------------------------------------------

def test_el_modulo_10_a_1_esta_en_la_biblioteca_con_su_ficha():
    """Once pernos, diez lóbulos. La carcasa mide Ø76 y, con su tapa, 23,3 mm
    de alto: 9 de suelo, 6 de disco con medio milímetro a cada lado, 4 de
    plato, 0,3 de juego y 3 de tapa. El plato de salida asoma 1 mm más: la
    cara a la que se atornilla lo que se mueve está a 24,3."""
    from orchestrator import modulos
    from orchestrator.componentes import cargar, envolvente
    assert "cicloidal-nema17-10" in modulos.ids()
    m = modulos.cargar("cicloidal-nema17-10")
    assert sorted(m.piezas) == ["carcasa", "disco", "excentrica", "salida", "tapa"]
    f = cargar("cicloidal-nema17-10")
    assert f.origen == "modulo" and f.reduccion == 10 and not f.da_par()
    assert envolvente(f) == ([-38, -38, 0], [38, 38, pytest.approx(23.3)])
    [salida] = f.salidas
    assert salida.en == pytest.approx([0, 0, 24.3]) and salida.eje == "+z"
    # Los cuatro tornillos del motor, en su cuadro de 31 mm.
    assert sorted((round(a.en[0], 1), round(a.en[1], 1)) for a in f.fijacion) == [
        (-15.5, -15.5), (-15.5, 15.5), (15.5, -15.5), (15.5, 15.5)]


@pytest.mark.parametrize("relacion", [5, 10, 20, 21, 25, 28])
def test_con_la_excentricidad_que_elige_el_modulo_el_disco_no_se_socava(relacion):
    """Con 1 mm de excentricidad, a partir de 22 pernos el disco se socava:
    con 26 quedan 0,04 mm de los 0,15 de holgura, y con 29 se atraviesan. El
    módulo baja a 0,7 mm desde ahí. Con la que elige, y con el polígono de
    32 puntos por lóbulo que de verdad se imprime (sus cuerdas se comen
    parte de la holgura en los valles), en toda la vuelta quedan al menos
    0,08 mm; construida, la de 20:1 midió 0,09."""
    from mech_toolkit.cicloidal import holgura_con_los_pernos
    from orchestrator.cicloidal import RADIO, RADIO_PERNO, medidas
    m = medidas(relacion)
    peor = min(holgura_con_los_pernos(m["pernos"], RADIO, RADIO_PERNO, m["e"],
                                      math.radians(g), holgura=m["holgura"],
                                      puntos=32 * m["pernos"])
               for g in range(0, 360, 40))
    assert peor >= 0.08, peor


def test_una_relacion_que_no_se_puede_hacer_se_dice():
    from orchestrator.cicloidal import generar
    with pytest.raises(ValueError, match="de 5 a 28"):
        generar(40)


def test_el_plan_no_puede_pedir_otra_relacion_que_la_de_la_reductora():
    """La 10:1 da 10:1. Un plan que la monta y dice 12 se rechaza con las
    dos cifras."""
    from orchestrator.plan import validar_plan
    from orchestrator.schemas.obra import Obra
    from tests.test_plan_mecanico import AGUJEROS
    plan = {"titulo": "Hombro", "nodos": [
        {"id": "base", "nombre": "Base", "que_hace": "aloja el motor y la reductora",
         "compra": ["nema17", "cicloidal-nema17-10"]},
        {"id": "brazo", "nombre": "Brazo", "que_hace": "gira", "depende_de": ["base"]},
        {"id": "todo", "nombre": "El hombro", "tipo": "conjunto", "que_hace": "se mueve",
         "depende_de": ["base", "brazo"]}],
        "uniones": [{"tipo": "gira", "id": "u1", "gira": "brazo", "sobre": "base",
                     "componente": "cicloidal-nema17-10", "recorrido_grados": 180,
                     "radio_libre_mm": 200,
                     "movido_por": {"motor": "nema17", "tipo": "reductora", "relacion": 10}}]}
    assert validar_plan(Obra(**plan), AGUJEROS)[0] == []
    plan["uniones"][0]["movido_por"]["relacion"] = 12
    [error] = validar_plan(Obra(**plan), AGUJEROS)[0]
    assert "u1" in error and "10" in error and "12" in error


def test_el_par_que_llega_por_la_reductora_lleva_su_rendimiento_medido():
    """El artículo midió 26 N a 10 cm con un motor de 26 N·cm y 15:1:
    «efficiency of around 66%». Se toma 0,65."""
    from orchestrator.estudio import RENDIMIENTO
    assert RENDIMIENTO["reductora"] == 0.65


from tests.test_generators import _freecadcmd  # noqa: E402


@pytest.mark.skipif(_freecadcmd() is None, reason="sin freecadcmd")
def test_las_cinco_piezas_construidas_giran_sin_atravesarse(tmp_path):
    """Las piezas de verdad, construidas con FreeCAD y puestas donde las deja
    la excéntrica cada 30° de su vuelta. Nada se atraviesa; el disco va
    pegado a los pernos (menos de 0,4 mm), que es engranar, y sus agujeros a
    los pasadores del plato."""
    from pathlib import Path

    import yaml
    from mech_toolkit.geometry import Placement

    from orchestrator.assembly import pair_gaps
    from orchestrator.build import build_part
    from orchestrator.cicloidal import generar, montaje
    from orchestrator.schemas.programa import Programa

    perfil = yaml.safe_load(Path("config/printers/ankermake_m5_plamas.yaml")
                            .read_text(encoding="utf-8"))
    modulo = generar(10)
    steps = {}
    for nombre, programa in modulo.piezas.items():
        build_part(Programa(part=nombre, codigo=programa), None, tmp_path / nombre,
                   _freecadcmd(), perfil=perfil)
        steps[nombre] = tmp_path / nombre / f"{nombre}.step"
    cuadros = {float(g): {p: Placement(origin=list(o), rotation=list(r))
                          for p, (o, r) in montaje(10, g).items()}
               for g in range(0, 360, 30)}
    pares = [("carcasa", "disco"), ("disco", "excentrica"), ("disco", "salida"),
             ("carcasa", "salida"), ("salida", "tapa"), ("carcasa", "excentrica"),
             ("excentrica", "salida"), ("disco", "tapa")]
    huecos = pair_gaps(steps, {}, cuadros, pares, _freecadcmd())
    assert len(huecos) == 12 * len(pares)
    peor = min(huecos, key=lambda h: h["gap_mm"])
    assert peor["gap_mm"] > 0.03, peor
    engrana = [h["gap_mm"] for h in huecos if {h["a"], h["b"]} == {"carcasa", "disco"}]
    assert max(engrana) < 0.4, engrana
    arrastra = [h["gap_mm"] for h in huecos if {h["a"], h["b"]} == {"disco", "salida"}]
    assert max(arrastra) < 0.4, arrastra


# --- lo que se atornilla al plato de salida -------------------------------------------------------

def _hombro(tmp_path, radio=20.0):
    """El hombro hecho a mano el 2026-11-12: la reductora tumbada en el
    soporte, con su eje a 60 mm de la mesa y hacia −y (la cara del plato, en
    y = −24,3), y el brazo, dibujado tumbado, contra ese plato: sus cuatro
    pasantes de M3 a `radio` del eje."""
    import json

    from tests.test_conjunto import _obra
    from tests.test_tornilleria import _caja_stl
    reductora = {"nombre": "cicloidal-nema17-10", "tipo": "componente",
                 "ficha": "cicloidal-nema17-10", "en": [0, 0, 60], "giros": [["x", 90]],
                 "entra_por": "-y"}
    en_el_soporte = {"nombre": "obra-soporte", "tipo": "componente", "ficha": "obra-soporte",
                     "en": [0, -60, -24.3], "giros": [["x", -90]], "entra_por": "-z"}
    pasantes = [{"nombre": f"acople {n}", "tipo": "agujero", "entrada": [x, y, 6],
                 "eje": [0, 0, -1], "diametro_mm": 3.3, "tornillo": "M3"}
                for n, (x, y) in enumerate([(radio, 0), (0, radio), (-radio, 0), (0, -radio)])]
    carpeta = _obra(tmp_path, {
        "soporte": ([], [reductora], ([-42, 0, 0], [42, 76, 105])),
        "brazo": (["soporte"], [en_el_soporte, *pasantes], ([-28, -28, 0], [28, 152, 6])),
    })
    for i, (a, b) in {"soporte": ((-42, 0, 0), (42, 76, 105)),
                      "brazo": ((-28, -28, 0), (28, 152, 6))}.items():
        (carpeta / "nodos" / i / "parts" / i / f"{i}.stl").write_text(
            "solid p\n" + _caja_stl(a, b) + "endsolid p\n", encoding="utf-8")
    return carpeta


def test_los_tornillos_del_brazo_agarran_en_el_plato_de_salida(tmp_path):
    """El plato tiene cuatro agujeros para rosca de M3 a 20 mm del eje. Los
    cuatro pasantes del brazo dan en ellos: agarran en la reductora, no «a
    donde se fije». Hecho a mano, el estudio los tomaba por tornillos al
    exterior y ponía la carga en ellos, en el eje: alcance 0 y carga sin
    medir."""
    from orchestrator.tornilleria import tornillos
    suyos = tornillos(_hombro(tmp_path), "conjunto")
    assert len(suyos) == 4
    assert {t.termina for t in suyos} == {"componente"}
    assert {(t.componente, t.lo_monta, t.pieza) for t in suyos} == {
        ("cicloidal-nema17-10", "soporte", "brazo")}
    # 6 mm de brazo y 7 de fondo de rosca: 13, y de catálogo, el de 12.
    assert {t.largo for t in suyos} == {12}


def test_un_pasante_que_no_da_en_los_agujeros_del_plato_no_agarra_en_el(tmp_path):
    """A 12 mm del eje no hay agujeros en el plato."""
    from orchestrator.tornilleria import tornillos
    suyos = tornillos(_hombro(tmp_path, radio=12.0), "conjunto")
    assert {t.termina for t in suyos} == {"superficie"}


def test_el_cuerno_de_un_servo_no_cuenta_como_rosca_de_metrica(tmp_path):
    """Los agujeros del cuerno de un SG90 son para sus tornillos de chapa, no
    para un M3: su ficha no dice ninguna métrica, y nada cambia para él."""
    from orchestrator.componentes import cargar
    assert cargar("sg90").salidas[0].acople.tornillo == ""
    assert cargar("cicloidal-nema17-10").salidas[0].acople.tornillo == "M3"


# --- la reductora en el banco y en lo que se le dice a quien la monta ----------------------------

def _con_plan_de_reductora(carpeta):
    import json
    plan = json.loads((carpeta / "obra.json").read_text(encoding="utf-8"))
    plan["nodos"][0]["compra"] = ["nema17", "cicloidal-nema17-10"]
    plan["uniones"] = [{"tipo": "gira", "id": "u1", "gira": "brazo", "sobre": "soporte",
                        "componente": "cicloidal-nema17-10", "recorrido_grados": 180,
                        "radio_libre_mm": 160,
                        "movido_por": {"motor": "nema17", "tipo": "reductora", "relacion": 10}}]
    (carpeta / "obra.json").write_text(json.dumps(plan), encoding="utf-8")
    return carpeta


def test_el_banco_cuenta_la_reduccion_de_una_reductora(tmp_path, monkeypatch):
    """El brazo gira sobre la salida de la cicloidal de 10:1 que monta el
    soporte: 10:1. Si se piden 20, no cumple, con las dos cifras."""
    from tests.test_banco import _juzgar_brazo
    for pide, estado, dice in ((10, "cumple", "10:1"), (20, "no_cumple", "10:1")):
        [r] = _juzgar_brazo(tmp_path / str(pide), monkeypatch,
                            [{"tipo": "reduccion", "relacion": pide}],
                            f"un hombro con una reductora cicloidal {pide}:1",
                            brazo=lambda p: _con_plan_de_reductora(_hombro(p)))
        assert r.estado == estado, r.detalle
        assert dice in r.detalle and "cicloidal" in r.detalle.lower()


def test_a_quien_monta_la_reductora_se_le_dice_como_va_con_el_motor(tmp_path):
    """El texto de una transmisión estaba escrito para una correa: «pon el
    eje del motor paralelo y a un lado». Una reductora va en el mismo eje
    que el motor, con la pared de la pieza entre los dos."""
    from orchestrator.obra import uniones_del_nodo
    [u] = [x for x in uniones_del_nodo(_con_plan_de_reductora(_hombro(tmp_path)), "soporte")
           if x.get("papel") == "sobre"]
    assert "mismo eje" in u["texto"] and "a un lado" not in u["texto"]
    assert "pared" in u["texto"] and "cuatro tornillos" in u["texto"]


def test_el_encargo_del_hombro_pide_lo_que_dice_su_peticion():
    from pathlib import Path

    from orchestrator.banco import cargar_encargos
    from orchestrator.componentes import mencionados
    [e] = [e for e in cargar_encargos(Path("tests/banco/encargos"))
           if e.nombre == "hombro_cicloidal_nema17"]
    por_tipo = {a.tipo: a for a in e.oraculo}
    assert por_tipo["reduccion"].relacion == 10 and por_tipo["carga"].minimo_g == 500
    assert "cicloidal 10:1" in e.peticion and "500 g" in e.peticion
    # La petición nombra la reductora: el desglosador recibe su ficha.
    assert "cicloidal-nema17-10" in mencionados(e.peticion)
    assert "cicloidal-nema17-20" not in mencionados(e.peticion)


@pytest.mark.llm
def test_deepseek_planifica_un_hombro_con_la_reductora_cicloidal():
    """La petición del encargo, tal cual: «gira 180° … sobre una reductora
    cicloidal 10:1 movida por un motor NEMA 17, con el eje horizontal»,
    «a 150 mm del eje y levanta 500 g»."""
    import os
    from pathlib import Path

    import yaml

    from orchestrator.agents.desglosador import DesglosadorAgent
    from orchestrator.cli import _cliente
    from orchestrator.config import load_env
    from orchestrator.impresion import perfil_activo
    from orchestrator.llm.router import Router
    from orchestrator.plan import validar_plan

    env = {**os.environ, **load_env(Path(".env"))}
    if not env.get("DEEPSEEK_API_KEY"):
        pytest.skip("sin DEEPSEEK_API_KEY")
    encargo = yaml.safe_load(Path("tests/banco/encargos/14b_hombro_cicloidal_nema17.yaml")
                             .read_text(encoding="utf-8"))
    router = Router.from_config_file(Path("config/models.yaml"), env=env)
    agujeros = perfil_activo(Path(".")).datos["holes"]
    obra = DesglosadorAgent(_cliente(router, env, "reason"), reserva=_cliente(router, env)).desglosar(
        encargo["peticion"], agujeros=agujeros)
    print(obra.model_dump_json(indent=1))
    [giro] = [u for u in obra.uniones if u.tipo == "gira"]
    assert giro.componente == "cicloidal-nema17-10"
    t = giro.movido_por
    assert t is not None and (t.motor, t.tipo, t.relacion) == ("nema17", "reductora", 10)
    assert {"nema17", "cicloidal-nema17-10"} <= set(obra.nodo(giro.sobre).compra)
    assert giro.eje == "horizontal" and giro.brazo_mm == 150 and obra.carga_g == 500
    assert validar_plan(obra, agujeros)[0] == []
