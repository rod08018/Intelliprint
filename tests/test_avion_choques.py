"""Lo comprado no se atraviesa (F13.8 (choques)).

Al comparar el avión con el Stallion de Flightory (2026-11-18), medido a mano:
con la flecha, los largueros de las dos alas forman una V, y cada uno pasaba
20 mm al otro lado (`SOLAPE_LARGUEROS`, puesto para que FreeCAD no partiera el
cuerpo central). Los dos Ø10 se cortaban en (154,7; 0; −2,7), y los Ø6 igual:
el avión no se podía montar, y ningún test lo veía.

Con las alas desmontables (F13.7 (desmontable), él: «Alas desmontables»),
cada Ø10 entra en un manguito de 12 × 10 que cruza el fuselaje; los dos
manguitos se cruzan en tijera, uno por encima del otro.

La distancia entre dos tubos se mide aquí por fuerza bruta, punto a punto a
lo largo de cada eje: no se fía de la geometría del kit.
"""

import copy
import itertools
import json
import math
from pathlib import Path

import pytest

from mech_toolkit import avion

HOY = json.loads(Path("scripts/avion_vtol.json").read_text(encoding="utf-8"))["diseno"]
SIN_DESMONTAR = copy.deepcopy(HOY)
SIN_DESMONTAR.pop("desmontable", None)


def _punto(t, a, b):
    return tuple(a[k] + (b[k] - a[k]) * t for k in range(3))


def _distancia(a, b, c, e, n=160):
    """La menor distancia entre los segmentos a–b y c–e, muestreando y
    afinando alrededor del mejor par."""
    mejor = (math.inf, 0.0, 0.0)
    for i in range(n + 1):
        p = _punto(i / n, a, b)
        for j in range(n + 1):
            q = _punto(j / n, c, e)
            dd = math.dist(p, q)
            if dd < mejor[0]:
                mejor = (dd, i / n, j / n)
    _, ti, tj = mejor
    paso = 1 / n
    for _ in range(30):
        paso /= 2
        for di, dj in itertools.product((-paso, 0, paso), repeat=2):
            u, v = min(max(ti + di, 0), 1), min(max(tj + dj, 0), 1)
            dd = math.dist(_punto(u, a, b), _punto(v, c, e))
            if dd < mejor[0]:
                mejor = (dd, u, v)
        _, ti, tj = mejor
    return mejor[0], _punto(ti, a, b)


def test_sin_desmontar_los_dos_largueros_de_10_se_cortan_en_el_centro():
    """El fallo de la versión 9, medido a mano el 2026-11-18."""
    tubos = {t["id"]: t for t in avion.tubos(SIN_DESMONTAR)}
    d, en = _distancia(tubos["larguero-10-d"]["de"], tubos["larguero-10-d"]["a"],
                       tubos["larguero-10-i"]["de"], tubos["larguero-10-i"]["a"])
    assert d == pytest.approx(0, abs=0.01)
    assert en == pytest.approx((154.7, 0, -2.7), abs=0.1)


def test_ningun_tubo_comprado_atraviesa_otro():
    """Cada par, separado al menos por la suma de sus radios. Solo se salta
    el larguero dentro de su manguito, que se mide aparte."""
    tubos = avion.tubos(HOY)
    dentro = {(t["id"], t["dentro_de"]) for t in tubos if t.get("dentro_de")}
    chocan = {}
    for a, b in itertools.combinations(tubos, 2):
        if (a["id"], b["id"]) in dentro or (b["id"], a["id"]) in dentro:
            continue
        d, en = _distancia(a["de"], a["a"], b["de"], b["a"])
        if d < (a["diametro"] + b["diametro"]) / 2:
            chocan[(a["id"], b["id"])] = (round(d, 2), [round(v, 1) for v in en])
    assert chocan == {}


def test_cada_larguero_de_10_entra_cinco_diametros_en_su_manguito():
    """5 Ø = 50 mm a lo largo de y (criterio del asistente), con el mismo eje:
    el ala se enchufa deslizando a lo largo de él."""
    tubos = {t["id"]: t for t in avion.tubos(HOY)}
    for lado in "di":
        lar, man = tubos[f"larguero-10-{lado}"], tubos[f"manguito-{lado}"]
        assert lar["dentro_de"] == f"manguito-{lado}"
        assert man["diametro_interior"] == pytest.approx(lar["diametro"])
        y_raiz = HOY["estaciones"][HOY["raiz"]][0]
        assert abs(lar["de"][1]) == pytest.approx(y_raiz - 50, abs=0.01)
        # El extremo del larguero, sobre el eje del manguito.
        d, _ = _distancia(lar["de"], lar["de"], man["de"], man["a"])
        assert d == pytest.approx(0, abs=0.01)


def test_los_dos_manguitos_cruzan_el_fuselaje():
    """Cada uno, de su raíz al otro lado del centro: es lo que pasa el momento
    de un ala a la otra."""
    tubos = {t["id"]: t for t in avion.tubos(HOY)}
    assert tubos["manguito-d"]["a"][1] < -40 and tubos["manguito-i"]["a"][1] > 40


def test_los_tubos_se_ven_en_el_avion_montado():
    """F13.14 (ensamble): en FreeCAD, escondida el ala, se ven el manguito,
    el larguero y el pasador donde van; lo comprado a la vista solo tenía
    vigas, motores y hélices. Cada tubo, de punta a punta de `tubos`."""
    comprado = avion.comprado_a_la_vista(HOY)
    for t in avion.tubos(HOY):
        assert t["id"] in comprado, t["id"]
        puntos = [p for tri in comprado[t["id"]] for p in tri]
        for i in range(3):
            assert min(p[i] for p in puntos) <= min(t["de"][i], t["a"][i]) + 0.01, t["id"]
            assert max(p[i] for p in puntos) >= max(t["de"][i], t["a"][i]) - 0.01, t["id"]
