"""Las formas de un VTOL de ala volante que genera el kit (F13.3 (costillas), ADR-023).

El diseño de abajo es el que sale de dimensionar el avión con AeroSandbox
(`scripts/avion_vtol_dimensionar.py`, 2026-11-16, con la batería y la carga
en el centro de gravedad), copiado aquí para que el test no cambie cuando
cambie el dimensionado. Lo esperado está contado a mano con esas cifras, no
con lo que sale de construir:

- el fuselaje va de x = -220 a 720: 940 mm en celdas de 200 como mucho son
  cinco; su sección más ancha es de 160, así que el centro va hasta |y| = 100;
- de y = 100 a la raíz del ala exterior (250) el borde de ataque más
  adelantado está en y = 100: 170 · 100 / 200 = 85; el de salida más
  atrasado también: 85 + 620 − 340 · 0,5 = 535; con 15 de margen a cada lado
  son 480 mm en celdas de 230: tres;
- el ala exterior va de 250 a 1050 (800 mm, cinco tramos de 160) y la punta
  levantada de 1050 a 1135 (un tramo, el sexto); los elevones empiezan en
  650, así que los llevan los tramos con el centro de ahí en adelante: el 3
  (650), el 4 y el 5;
- por lado: 3 de raíz, 6 de ala, 3 elevones, 2 góndolas, pilón, pata y
  deriva, 17; con las cinco del centro, 39;
- el tramo 1 va de y = 250 (borde de ataque en x = 190, cuerda 230, sin
  torsión) a 410 (borde de ataque en 190 + 373 · 0,2 = 264,6, cuerda
  230 − 110 · 0,2 = 208; borde de salida en 472,6);
- la bisagra del tramo 3, en y = 570, está al 75 % de una cuerda de 186 que
  empieza en 339,2: x = 478,7; el elevón empieza medio milímetro detrás.
"""

import json
import os

import pytest

from mech_toolkit import avion
from orchestrator.build import build_part
from orchestrator.schemas.programa import Programa
from tests.test_generators import _freecadcmd
from tests.test_sondas import PERFIL

DISENO = {
    "estaciones": [[0.0, 0.0, 0.0, 620.0, 2.0, "mh78"], [200.0, 170.0, 0.0, 280.0, 1.0, "mh60"],
                   [250.0, 190.0, 5.0, 230.0, 0.0, "mh60"],
                   [1050.0, 563.0, 50.0, 120.0, -3.0, "mh60"],
                   [1135.0, 622.7, 121.3, 80.0, -3.0, "mh60"]],
    "raiz": 2,
    "fuselaje": [[-220, 20, 20, -20], [-140, 110, 90, -20], [0, 150, 130, -30],
                 [180, 160, 180, -50], [420, 160, 180, -50], [600, 90, 80, -20],
                 [720, 40, 40, -20]],
    "z_fuselaje": -20,
    "largueros": [[0.25, 10], [0.6, 6]],
    "elevon": [650, 0.75],
    "deriva": {"x": 720, "cuerda": [150, 90], "alto": 165},
    "rotores": {"y": 380, "x": [-53, 677], "viga": 16, "helice": 330},
    "empuje": {"x": 720, "helice": 254},
    "ventanas": [[250, 40, 34], [312, 70, 60], [374, 40, 34]],
    "elevones": [[3], [4, 5]],
    "dentro": [
        {"id": "impreso", "masa_kg": 0.9418, "en": [369.0, 0, -1.8]},
        {"id": "larguero-Ø10", "masa_kg": 0.06, "en": [357.6, 0, 19.3]},
        {"id": "larguero-Ø6", "masa_kg": 0.03, "en": [425.9, 0, 19.3]},
        {"id": "vigas", "masa_kg": 0.09, "en": [388.3, 0, -12.0]},
        {"id": "motor-d-delante", "masa_kg": 0.1812, "en": [-53.4, 380.0, 18.0]},
        {"id": "motor-d-detras", "masa_kg": 0.1812, "en": [677.4, 380.0, 18.0]},
        {"id": "motor-i-delante", "masa_kg": 0.1812, "en": [-53.4, -380.0, 18.0]},
        {"id": "motor-i-detras", "masa_kg": 0.1812, "en": [677.4, -380.0, 18.0]},
        {"id": "motor-empuje", "masa_kg": 0.1735, "en": [735, 0, -20.0]},
        {"id": "variador-empuje", "masa_kg": 0.0434, "en": [600, 0, -20.0]},
        {"id": "electronica", "masa_kg": 0.31, "en": [-20, 0, -28], "caja": [120, 60, 40]},
        {"id": "servo-d-interior", "masa_kg": 0.025, "en": [450.0, 650, 27.5],
         "caja": [24, 34, 10]},
        {"id": "servo-d-exterior", "masa_kg": 0.025, "en": [531.7, 850, 38.8],
         "caja": [24, 34, 10]},
        {"id": "servo-i-interior", "masa_kg": 0.025, "en": [450.0, -650, 27.5],
         "caja": [24, 34, 10]},
        {"id": "servo-i-exterior", "masa_kg": 0.025, "en": [531.7, -850, 38.8],
         "caja": [24, 34, 10]},
        {"id": "carga", "masa_kg": 1.0, "en": [312.0, 0, -88.0], "caja": [160, 80, 50]},
        {"id": "bateria", "masa_kg": 2.7216, "en": [287.2, 0, -36.0], "caja": [210, 130, 46]},
    ],
    "equilibrio": {"punto_neutro_x": 331.9, "cuerda_media": 284.1,
                   "margen_minimo": 0.05, "margen_maximo": 0.12},
}

CAMA = (235.0, 235.0, 250.0)


def test_el_avion_tiene_las_piezas_contadas_a_mano():
    ids = [p[0] for p in avion.piezas(DISENO)]
    assert len(ids) == len(set(ids)) == 39
    assert [i for i in ids if i.startswith("centro")] == [f"centro-{k}" for k in range(1, 6)]
    for lado in "di":
        assert [i for i in ids if i.startswith(f"raiz-{lado}")] == [
            f"raiz-{lado}-{k}" for k in (1, 2, 3)]
        assert [i for i in ids if i.startswith(f"ala-{lado}")] == [
            f"ala-{lado}-{k}" for k in range(1, 7)]
        assert [i for i in ids if i.startswith(f"elevon-{lado}")] == [
            f"elevon-{lado}-{k}" for k in (3, 4, 5)]
        for resto in ("gondola-{}-delante", "gondola-{}-detras", "pilon-{}", "pata-{}",
                      "deriva-{}"):
            assert resto.format(lado) in ids


def test_una_pieza_que_no_existe_se_dice_con_las_que_hay():
    with pytest.raises(Exception, match="no tiene la pieza 'ala-d-9'.*ala-d-6"):
        avion.pieza(None, DISENO, "ala-d-9")


# --- lo de dentro y el equilibrio ------------------------------------------------

def test_el_centro_de_gravedad_es_la_media_de_las_masas():
    """2 kg en x = 100 y 1 kg en x = 400 (z = 30): (200 + 400) / 3 = 200, y
    z = 30 / 3 = 10. Con el punto neutro en 230 y 100 de cuerda media, el
    margen es 0,3; sin el de 1 kg, el centro de gravedad va a 100 y 1,3."""
    d = {"dentro": [{"id": "a", "masa_kg": 2, "en": [100, 0, 0]},
                    {"id": "b", "masa_kg": 1, "en": [400, 0, 30]}],
         "equilibrio": {"punto_neutro_x": 230, "cuerda_media": 100}}
    eq = avion.equilibrio(d)
    assert eq["cg"] == pytest.approx([200, 0, 10])
    assert eq["margen"] == pytest.approx(0.3)
    assert avion.equilibrio(d, sin=("b",))["margen"] == pytest.approx(1.3)


def test_con_carga_y_sin_ella_el_ala_volante_es_estable():
    """Lo pidió él el 2026-11-16: «la batería debe estar en un lugar donde no
    modifique mucho el centro de gravedad». Con la carga en el morro, como
    estaba, quitarla echaba el centro de gravedad 35–83 mm atrás, pasado el
    punto neutro (un 7 % de 284 mm de margen son 20 mm)."""
    eq = DISENO["equilibrio"]
    for sin in ((), ("carga",)):
        margen = avion.equilibrio(DISENO, sin=sin)["margen"]
        assert eq["margen_minimo"] <= margen <= eq["margen_maximo"], (sin, margen)


def _hueco_en(x):
    """(ancho, alto, z) del hueco del fuselaje en `x`: la sección de fuera
    menos 2,5 mm de pared por cada lado, lineal entre secciones."""
    fus = DISENO["fuselaje"]
    for a, b in zip(fus, fus[1:]):
        if a[0] <= x <= b[0]:
            t = (x - a[0]) / (b[0] - a[0])
            w, h, z = (a[k] + (b[k] - a[k]) * t for k in (1, 2, 3))
            return w - 5, h - 5, z
    raise AssertionError(x)


@pytest.mark.parametrize("que", ["bateria", "carga", "electronica"])
def test_lo_de_dentro_cabe_en_el_hueco_del_fuselaje(que):
    """Cada esquina de la caja, dentro de la elipse del hueco en su x, en las
    dos puntas de la caja y en cada sección que cae entre ellas."""
    c = next(c for c in DISENO["dentro"] if c["id"] == que)
    (x, y, z), (lx, ly, lz) = c["en"], c["caja"]
    xs = [x - lx / 2, x + lx / 2] + [f[0] for f in DISENO["fuselaje"]
                                     if x - lx / 2 < f[0] < x + lx / 2]
    for xq in xs:
        w, h, zc = _hueco_en(xq)
        for yq in (y - ly / 2, y + ly / 2):
            for zq in (z - lz / 2, z + lz / 2):
                assert (yq / (w / 2)) ** 2 + ((zq - zc) / (h / 2)) ** 2 <= 1, (que, xq, yq, zq)


def test_la_bateria_pasa_bajo_los_largueros():
    """Los largueros cruzan el fuselaje de lado a lado: la batería, que se
    mete y se saca, tiene que quedar debajo con 1 mm de aire."""
    c = next(c for c in DISENO["dentro"] if c["id"] == "bateria")
    (x, _, z), (lx, ly, lz) = c["en"], c["caja"]
    cruzan = 0
    for f, diametro in DISENO["largueros"]:
        for y in (-ly / 2, 0, ly / 2):
            xl, zl, _ = avion._punto_larguero(DISENO, abs(y), f)
            if x - lx / 2 <= xl <= x + lx / 2:
                cruzan += 1
                assert z + lz / 2 <= zl - diametro / 2 - 1, (f, y, zl)
    assert cruzan > 0


def test_lleva_cuatro_servos_dos_elevones_por_lado():
    """Él, el 2026-11-16: «debe tener alerones, implica que debe tener 4
    servos». El interior es el tramo 3 y el exterior, el 4 y el 5 pegados con
    una varilla."""
    nombres = {i: (n, q) for i, n, q in avion.piezas(DISENO)}
    assert "interior" in nombres["elevon-d-3"][0]
    assert "exterior 1" in nombres["elevon-d-4"][0] and "exterior 2" in nombres["elevon-d-5"][0]
    assert "varilla" in nombres["elevon-d-5"][1]
    assert "servo del elevón interior" in nombres["ala-d-3"][1]
    assert "servo del elevón exterior" in nombres["ala-d-4"][1]
    servos = [c["id"] for c in DISENO["dentro"] if c["id"].startswith("servo-")]
    assert sorted(servos) == ["servo-d-exterior", "servo-d-interior", "servo-i-exterior",
                              "servo-i-interior"]


# --- construidas -----------------------------------------------------------------

# El centro-1 y el centro-5 son los extremos del hueco del fuselaje: con una
# transición suave el morro quedaba roto y la cola salía en tres sólidos; el
# centro-3 es por donde los largueros cruzan el hueco. El 2, el 3 y el 4
# llevan la electrónica, la batería y la carga; el ala 3 y la 4, los servos.
CONSTRUIDAS = ["centro-1", "centro-2", "centro-3", "centro-4", "centro-5", "raiz-d-1",
               "ala-d-1", "ala-i-1", "ala-d-3", "ala-d-4", "elevon-d-3", "elevon-d-4",
               "elevon-d-5", "ala-d-6", "gondola-d-delante", "pilon-d", "pata-d", "deriva-d"]
DENTRO = ["bateria", "carga", "electronica", "servo-d-interior", "servo-d-exterior",
          "canal-d", "varilla-d"]


def _construir(raiz, nombre, llamada):
    codigo = (f"def construir(kit):\n    diseno = {json.dumps(DISENO)}\n"
              f"    return {llamada}\n")
    carpeta = raiz / nombre
    build_part(Programa(part=nombre, codigo=codigo), None, carpeta, _freecadcmd(),
               perfil=PERFIL)
    return carpeta


@pytest.fixture(scope="module")
def piezas(tmp_path_factory):
    if _freecadcmd() is None:
        pytest.skip("sin freecadcmd")
    raiz = tmp_path_factory.mktemp("avion")
    return {id_: _construir(raiz, id_, f'kit.avion_pieza(diseno, "{id_}")')
            for id_ in CONSTRUIDAS}


@pytest.fixture(scope="module")
def dentro(tmp_path_factory):
    if _freecadcmd() is None:
        pytest.skip("sin freecadcmd")
    raiz = tmp_path_factory.mktemp("dentro")
    return {q: _construir(raiz, q, f'kit.avion_dentro(diseno, "{q}")') for q in DENTRO}


def _huecos(piezas, dentro, pares):
    from mech_toolkit.geometry import Placement

    from orchestrator.assembly import pair_gaps
    todas = {**piezas, **dentro}
    steps = {n: todas[n] / f"{n}.step" for par in pares for n in par}
    cuadro = {0.0: {n: Placement() for n in steps}}
    return {(h["a"], h["b"]): h["gap_mm"]
            for h in pair_gaps(steps, {}, cuadro, pares, _freecadcmd())}


def test_lo_de_dentro_no_atraviesa_el_fuselaje(piezas, dentro):
    """La batería, la carga y la electrónica, contra las celdas que cruzan:
    la piel, los largueros, el canal de los cables."""
    pares = [("bateria", "centro-3"), ("bateria", "centro-4"), ("carga", "centro-3"),
             ("carga", "centro-4"), ("electronica", "centro-1"), ("electronica", "centro-2")]
    huecos = _huecos(piezas, dentro, pares)
    assert all(h >= 0 for h in huecos.values()), huecos


def test_cada_servo_esta_en_su_hueco_del_ala(piezas, dentro):
    """Sin tocar el ala y a menos de 1 mm de ella: metido en su hueco, no
    flotando fuera (el hueco le deja 0,5 mm por cada lado)."""
    huecos = _huecos(piezas, dentro, [("servo-d-interior", "ala-d-3"),
                                      ("servo-d-exterior", "ala-d-4")])
    assert all(0 <= h < 1 for h in huecos.values()), huecos


def test_el_canal_lleva_los_cables_del_fuselaje_a_los_servos(piezas, dentro):
    """Un mazo de Ø4 por el canal de Ø6,3 pasa por la piel del fuselaje, la
    raíz y los tramos del ala sin tocarlos: le quedan 1,15 mm."""
    huecos = _huecos(piezas, dentro, [("canal-d", p) for p in
                                      ("centro-3", "raiz-d-1", "ala-d-1", "ala-d-3")])
    assert all(0 < h < 1.5 for h in huecos.values()), huecos


def test_la_varilla_une_los_dos_trozos_del_elevon_exterior(piezas, dentro):
    """Pasa por los dos trozos, en un agujero de 0,3 mm más que ella."""
    huecos = _huecos(piezas, dentro, [("varilla-d", "elevon-d-4"), ("varilla-d", "elevon-d-5")])
    assert all(0 <= h < 0.5 for h in huecos.values()), huecos


def _caja(carpeta):
    e = json.loads((carpeta / "envolvente.json").read_text(encoding="utf-8"))
    return e["min"], e["max"]


def test_el_primer_tramo_del_ala_va_de_raiz_a_raiz_y_de_borde_a_borde(piezas):
    lo, hi = _caja(piezas["ala-d-1"])
    assert lo[1] == pytest.approx(250, abs=0.1) and hi[1] == pytest.approx(410, abs=0.1)
    assert lo[0] == pytest.approx(190, abs=1) and hi[0] == pytest.approx(472.6, abs=1)


def test_el_lado_izquierdo_es_el_reflejo_del_derecho(piezas):
    lo_d, hi_d = _caja(piezas["ala-d-1"])
    lo_i, hi_i = _caja(piezas["ala-i-1"])
    assert lo_i[1] == pytest.approx(-hi_d[1], abs=0.01)
    assert hi_i[1] == pytest.approx(-lo_d[1], abs=0.01)
    assert (lo_i[0], hi_i[0]) == pytest.approx((lo_d[0], hi_d[0]), abs=0.01)


def test_el_elevon_queda_a_un_milimetro_del_ala(piezas):
    lo, _ = _caja(piezas["elevon-d-3"])
    assert lo[0] == pytest.approx(478.7 + 0.5, abs=0.3)
    assert lo[1] == pytest.approx(570, abs=0.1)


def test_cada_pieza_cabe_en_la_cama(piezas):
    """Con la cama girada: un tramo de ala con flecha solo entra en
    diagonal (`test_medida`)."""
    from orchestrator.medida import no_cabe_en_la_impresora
    grandes = {}
    for id_, carpeta in piezas.items():
        lo, hi = _caja(carpeta)
        if no_cabe_en_la_impresora([b - a for a, b in zip(lo, hi)], CAMA):
            grandes[id_] = [round(b - a) for a, b in zip(lo, hi)]
    assert grandes == {}


def test_se_imprimen_sin_soportes(piezas):
    """La primera versión, dibujada pieza a pieza, dejaba techos en el morro,
    la cola y la deriva (prueba a mano del 2026-11-16)."""
    from orchestrator.voladizos import como_imprimir
    piden = {}
    for id_, carpeta in piezas.items():
        postura, zonas = como_imprimir(carpeta / f"{id_}.stl", PERFIL["overhang_max_deg"],
                                       PERFIL["bridge_max_mm"])
        if postura is None:
            piden[id_] = min(len(z) for z in zonas.values())
    assert piden == {}
