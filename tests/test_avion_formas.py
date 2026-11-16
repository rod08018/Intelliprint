"""Las formas de un VTOL de ala volante que genera el kit (F13.3 (costillas), ADR-023).

El diseño de abajo es el que sale de dimensionar el avión con AeroSandbox
(`scripts/avion_vtol_dimensionar.py`, 2026-11-16), copiado aquí para que el
test no cambie cuando cambie el dimensionado. Lo esperado está contado a mano
con esas cifras, no con lo que sale de construir:

- el fuselaje va de x = -220 a 720: 940 mm en celdas de 200 como mucho son
  cinco; su sección más ancha es de 150, así que el centro va hasta |y| = 95;
- de y = 95 a la raíz del ala exterior (250) el borde de ataque más adelantado
  está en y = 95: 170 · 95 / 200 = 80,75; el de salida más atrasado también:
  80,75 + 620 − 340 · 0,475 = 539,25; con 15 de margen a cada lado son
  488,5 mm en celdas de 230: tres;
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
    "fuselaje": [[-220, 20, 20], [-140, 110, 90], [0, 150, 120], [350, 150, 120],
                 [600, 90, 80], [720, 40, 40]],
    "z_fuselaje": -20,
    "largueros": [[0.25, 10], [0.6, 6]],
    "elevon": [650, 0.75],
    "deriva": {"x": 720, "cuerda": [150, 90], "alto": 130},
    "rotores": {"y": 380, "x": [-46, 677], "viga": 16, "helice": 330},
    "empuje": {"x": 720, "helice": 254},
    "ventanas": [[-100, 40, 34], [10, 40, 34], [140, 84, 72]],
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


# --- construidas -----------------------------------------------------------------

# El centro-1 y el centro-5 son los extremos del hueco del fuselaje: con una
# transición suave el morro quedaba roto y la cola salía en tres sólidos; el
# centro-3 es por donde los largueros cruzan el hueco.
CONSTRUIDAS = ["centro-1", "centro-3", "centro-5", "raiz-d-1", "ala-d-1", "ala-i-1", "ala-d-3", "elevon-d-3",
               "ala-d-6", "gondola-d-delante", "pilon-d", "pata-d", "deriva-d"]


@pytest.fixture(scope="module")
def piezas(tmp_path_factory):
    if _freecadcmd() is None:
        pytest.skip("sin freecadcmd")
    raiz = tmp_path_factory.mktemp("avion")
    carpetas = {}
    for id_ in CONSTRUIDAS:
        codigo = (f"def construir(kit):\n    diseno = {json.dumps(DISENO)}\n"
                  f'    return kit.avion_pieza(diseno, "{id_}")\n')
        carpeta = raiz / id_
        build_part(Programa(part=id_, codigo=codigo), None, carpeta, _freecadcmd(),
                   perfil=PERFIL)
        carpetas[id_] = carpeta
    return carpetas


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
