"""El ala volante en una cama de 300 × 300 × 330 y con el tren en las góndolas
(F13.3 (costillas)).

Él, el 2026-11-18, al ver 44 piezas: «tiene como 40 partes el avion, pero mi
impresora es de 300x300x270 algo asi es la core one L+ porque estamos sacando
muchisimas piezas». El kit cortaba con las medidas de la cama del sistema
(235 × 235 × 250): ahora el diseño dice cuánto mide un tramo y una celda.

Y al mirar el avión montado (2026-11-17) se vio que la deriva se montaba
sobre los 30 mm finales de la góndola de atrás y que la viga acababa antes que
ella. Con `aletas`, la pata va en la góndola de delante y la deriva en la de
atrás, centradas en su motor: una pieza en vez de dos, y no se pueden pisar.

El diseño es el del test de las formas (`test_avion_formas.DISENO`) con lo
nuevo; lo esperado está contado a mano con sus cifras:

- el cuerpo central sigue en celdas de 200, cinco: con celdas de 290 una
  llevaba el borde de ataque del centro y la boca de la panza, y pedía
  soportes de pie sobre cualquiera de sus cortes (prueba del 2026-11-18);
- la raíz va de x = 70 a 550 (480 mm): en celdas de 290, dos;
- el ala exterior va de 250 a 1050: 800 mm en tramos de 270 como mucho son
  tres, de 266,7; la punta levantada, el cuarto. Los elevones empiezan en
  640: los llevan los tramos con el centro de ahí en adelante, el 2 (650) y
  el 3 (916,7);
- por lado: 2 de raíz, 4 de ala, 2 elevones, 2 tapas de servo, 2 góndolas y
  el pilón, 13; con las cinco del centro y la panza, 32 (eran 44);
- la viga va de la punta de la pata (−90 − 100/2) a la de la deriva
  (710 + 150/2).
"""

import copy
import json

import pytest

from mech_toolkit import avion
from orchestrator.build import build_part
from orchestrator.schemas.programa import Programa
from tests.test_avion_formas import DISENO
from tests.test_generators import _freecadcmd
from tests.test_sondas import PERFIL

GRANDE = copy.deepcopy(DISENO)
GRANDE.update({"cama": [300, 300, 330], "tramo_max": 270, "celda_raiz": 290, "elevon": [640, 0.75], "elevones": [[2], [3]]})
GRANDE["rotores"]["aletas"] = True
GRANDE["pata"] = {"cuerda": [100, 70]}
CAMA = (300.0, 300.0, 330.0)


def test_con_la_cama_grande_salen_32_piezas():
    ids = [p[0] for p in avion.piezas(GRANDE)]
    assert len(ids) == len(set(ids)) == 32
    assert [i for i in ids if i.startswith("centro")] == [f"centro-{k}" for k in range(1, 6)]
    for lado in "di":
        assert [i for i in ids if i.startswith(f"raiz-{lado}")] == [f"raiz-{lado}-{k}"
                                                                     for k in (1, 2)]
        assert [i for i in ids if i.startswith(f"ala-{lado}")] == [f"ala-{lado}-{k}"
                                                                    for k in range(1, 5)]
        assert [i for i in ids if i.startswith(f"elevon-{lado}")] == [f"elevon-{lado}-{k}"
                                                                       for k in (2, 3)]
    assert not [i for i in ids if i.startswith(("pata", "deriva"))]


def test_los_tramos_son_de_la_cama_grande():
    tramos = [(round(a, 1), round(b, 1)) for a, b, _ in avion._tramos_ala(GRANDE)]
    assert tramos == [(250, 516.7), (516.7, 783.3), (783.3, 1050), (1050, 1135)]


def test_sin_las_medidas_nuevas_corta_como_antes():
    """Los aviones ya construidos se rehacen igual."""
    assert len(avion.piezas(DISENO)) == 44


def test_las_gondolas_dicen_que_llevan_la_pata_y_la_deriva():
    nombres = {i: (n, q) for i, n, q in avion.piezas(GRANDE)}
    assert "pata" in nombres["gondola-d-delante"][1]
    assert "deriva" in nombres["gondola-d-detras"][1]


def test_la_viga_va_de_la_punta_de_la_pata_a_la_de_la_deriva():
    comprado = avion.comprado_a_la_vista(GRANDE)
    puntos = [p for t in comprado["viga-d"] for p in t]
    assert min(p[0] for p in puntos) == pytest.approx(-140, abs=0.01)
    assert max(p[0] for p in puntos) == pytest.approx(785, abs=0.01)


# --- construidas -----------------------------------------------------------------

CONSTRUIDAS = ["gondola-d-delante", "gondola-d-detras", "ala-d-1", "raiz-d-1", "raiz-d-2"]


@pytest.fixture(scope="module")
def piezas(tmp_path_factory):
    if _freecadcmd() is None:
        pytest.skip("sin freecadcmd")
    raiz = tmp_path_factory.mktemp("avion-grande")
    hechas = {}
    for id_ in CONSTRUIDAS:
        codigo = (f"def construir(kit):\n    diseno = {GRANDE!r}\n"
                  f"    return kit.avion_pieza(diseno, {id_!r})\n")
        build_part(Programa(part=id_, codigo=codigo), None, raiz / id_, _freecadcmd(),
                   perfil=PERFIL)
        hechas[id_] = raiz / id_
    return hechas


def _caja(carpeta):
    e = json.loads((carpeta / "envolvente.json").read_text(encoding="utf-8"))
    return e["min"], e["max"]


def test_los_cortes_del_cuerpo_central_se_pueden_dar_a_mano():
    """El borde de ataque del centro del avión del 2026-11-18 va a 41° (de
    x = 0 en y = 0 a x = 150 en y = 170): en la celda que lo lleva de pie
    sobre su corte de delante, su morro vuela 24,4 mm fuera del fuselaje. El
    diseño dice dónde se corta, detrás del borde, y la celda de delante se
    imprime sobre su cara de atrás, con el borde hacia arriba."""
    d = copy.deepcopy(GRANDE)
    d["cortes_fuselaje"] = [-220, 0, 250, 480, 720]       # su fuselaje va de -220 a 720
    celdas = avion._celdas(d)
    assert [celdas[f"centro-{k}"][:2] for k in range(1, 5)] == [(-220, 0), (0, 250),
                                                               (250, 480), (480, 720)]
    assert "centro-5" not in celdas
    assert [i for i, _, _ in avion.piezas(d) if i.startswith("centro")] == [
        f"centro-{k}" for k in range(1, 5)]


def test_unos_cortes_que_no_empiezan_en_el_morro_no_valen():
    d = copy.deepcopy(GRANDE)
    d["cortes_fuselaje"] = [-200, 250, 720]
    with pytest.raises(Exception, match="morro"):
        avion._celdas(d)


def test_la_deriva_cuelga_de_la_gondola_de_atras(piezas):
    """Centrada en el motor de atrás (710), con su cuerda de 150, y bajando lo
    alto que es desde el centro de la viga."""
    lo, hi = _caja(piezas["gondola-d-detras"])
    assert (lo[0], hi[0]) == pytest.approx((635, 785), abs=0.5)
    assert lo[2] == pytest.approx(avion._z_viga(GRANDE) - 255, abs=0.5)


def test_la_pata_cuelga_de_la_gondola_de_delante(piezas):
    lo, hi = _caja(piezas["gondola-d-delante"])
    assert (lo[0], hi[0]) == pytest.approx((-140, -40), abs=0.5)
    assert lo[2] == pytest.approx(avion._z_viga(GRANDE) - 255, abs=0.5)


def test_caben_en_la_cama_grande(piezas):
    from orchestrator.medida import no_cabe_en_la_impresora
    grandes = {}
    for id_, carpeta in piezas.items():
        lo, hi = _caja(carpeta)
        if no_cabe_en_la_impresora([b - a for a, b in zip(lo, hi)], CAMA):
            grandes[id_] = [round(b - a) for a, b in zip(lo, hi)]
    assert grandes == {}


def test_se_imprimen_sin_soportes(piezas):
    from orchestrator.voladizos import como_imprimir
    piden = {}
    for id_, carpeta in piezas.items():
        postura, zonas = como_imprimir(carpeta / f"{id_}.stl", PERFIL["overhang_max_deg"],
                                       PERFIL["bridge_max_mm"])
        if postura is None:
            piden[id_] = min(len(z) for z in zonas.values())
    assert piden == {}


# --- el avión de hoy (`scripts/avion_vtol.json`) ------------------------------------

DE_HOY = ["ala-d-3", "centro-1", "centro-2"]


@pytest.fixture(scope="module")
def de_hoy(tmp_path_factory):
    if _freecadcmd() is None:
        pytest.skip("sin freecadcmd")
    from pathlib import Path
    d = json.loads(Path("scripts/avion_vtol.json").read_text(encoding="utf-8"))["diseno"]
    raiz = tmp_path_factory.mktemp("avion-de-hoy")
    hechas = {}
    for id_ in DE_HOY:
        codigo = (f"def construir(kit):\n    diseno = {d!r}\n"
                  f"    return kit.avion_pieza(diseno, {id_!r})\n")
        build_part(Programa(part=id_, codigo=codigo), None, raiz / id_, _freecadcmd(),
                   perfil=PERFIL)
        hechas[id_] = raiz / id_
    return hechas


def test_la_punta_del_ala_sale_de_una_pieza(de_hoy):
    """Los largueros acababan en el corte de la punta (y = 860), y por el
    diedro el disco de su extremo asomaba 2,4 mm en ella: sus fundas, dentro
    del hueco y sin tocar la piel, eran dos sólidos sueltos (2026-11-18).
    `build_part` no construye una pieza de varios sólidos. Desde que la
    punta va pegada al último tramo (`punta_unida`, ese mismo día), es el
    tramo 3 el que la lleva."""
    assert (de_hoy["ala-d-3"] / "ala-d-3.stl").exists()


def test_el_morro_y_el_cuerpo_de_hoy_se_imprimen_sin_soportes(de_hoy):
    from orchestrator.voladizos import como_imprimir
    piden = {}
    for id_ in ("centro-1", "centro-2"):
        postura, zonas = como_imprimir(de_hoy[id_] / f"{id_}.stl", PERFIL["overhang_max_deg"],
                                       PERFIL["bridge_max_mm"])
        if postura is None:
            piden[id_] = min(len(z) for z in zonas.values())
    assert piden == {}
