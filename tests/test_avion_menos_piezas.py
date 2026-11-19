"""Menos piezas para la CORE One L+ (F13.3 (costillas)).

Él, el 2026-11-18, al ver que el avión aún tenía 31 piezas: «Sí, bájalas» y
«toma en cuenta el volumen de impresión de la core one L+ de prusa», que es de
300 × 300 × 330 mm (su hoja: 300 × 300 de cama y 330 de alto).

Medidas una a una en sus STL (la versión 8, `2026-11-18-ala-volante-660kv-a-
mano-sin-modelo`): la punta levantada (y de 860 a 945) cabe pegada al último
tramo (de 646,7 a 860). Juntos miden 298,3 de alto de pie sobre la raíz, y de
huella, del borde de ataque del tramo al de salida de la punta, unos 270 × 110.
Así pedía soportes en un solo sitio: detrás de la bisagra, la punta empezaba
en el aire sobre el hueco del elevón (un techo de 40 mm); lleva una rampa.

Lo demás no baja, y no por la cama:

- el ala no admite tramos más largos: el primero entra en diagonal con 21 mm
  de margen, y con dos tramos en vez de tres cada uno mediría 320 de alto y
  su huella entraría con 1,4 mm;
- la raíz mide 409 mm a lo largo de x, de pie sobre un corte: dos;
- el cuerpo central, que de pie mediría 325 mm en tres celdas, pide soportes
  así (probado ese día con cortes en 430 y en 300). Las orillas de la boca de
  la panza (x = 153,7 y 321,7) y el borde de salida del centro solo se
  imprimen sin soportes de pie sobre un lado concreto: la orilla de delante y
  el borde de salida sobre la cara de delante de su celda, la de detrás sobre
  la de atrás. Una celda que lleve dos que se contradicen no tiene postura, y
  con solo dos celdas detrás del morro siempre hay una: hacen falta las cuatro.

Lo esperado, contado a mano: 31 − 2 puntas = 29.
"""

import copy
import json
from pathlib import Path

import pytest

from mech_toolkit import avion
from orchestrator.build import build_part
from orchestrator.schemas.programa import Programa
from tests.test_generators import _freecadcmd
from tests.test_sondas import PERFIL

CAMA = (300.0, 300.0, 330.0)
HOY = json.loads(Path("scripts/avion_vtol.json").read_text(encoding="utf-8"))["diseno"]
MENOS = copy.deepcopy(HOY)
MENOS["punta_unida"] = True


def test_salen_29_piezas():
    ids = [p[0] for p in avion.piezas(MENOS)]
    assert len(ids) == len(set(ids)) == 29
    for lado in "di":
        assert [i for i in ids if i.startswith(f"ala-{lado}")] == [f"ala-{lado}-{k}"
                                                                    for k in (1, 2, 3)]


def test_el_ultimo_tramo_dice_que_lleva_la_punta():
    nombres = {i: q for i, _, q in avion.piezas(MENOS)}
    assert "punta" in nombres["ala-d-3"]


def test_sin_punta_unida_la_punta_sigue_aparte():
    """Los aviones ya construidos se rehacen igual."""
    d = copy.deepcopy(MENOS)
    del d["punta_unida"]
    assert "ala-d-4" in [p[0] for p in avion.piezas(d)]


# --- construidas -----------------------------------------------------------------

CONSTRUIDAS = ["ala-d-3"]


@pytest.fixture(scope="module")
def piezas(tmp_path_factory):
    if _freecadcmd() is None:
        pytest.skip("sin freecadcmd")
    raiz = tmp_path_factory.mktemp("avion-menos")
    hechas = {}
    for id_ in CONSTRUIDAS:
        codigo = (f"def construir(kit):\n    diseno = {MENOS!r}\n"
                  f"    return kit.avion_pieza(diseno, {id_!r})\n")
        build_part(Programa(part=id_, codigo=codigo), None, raiz / id_, _freecadcmd(),
                   perfil=PERFIL)
        hechas[id_] = raiz / id_
    return hechas


def _caja(carpeta):
    e = json.loads((carpeta / "envolvente.json").read_text(encoding="utf-8"))
    return e["min"], e["max"]


def test_el_ultimo_tramo_llega_a_la_punta(piezas):
    """De 220 + 2 · 640 / 3 = 646,7 a la punta, en 945."""
    lo, hi = _caja(piezas["ala-d-3"])
    assert (lo[1], hi[1]) == pytest.approx((646.7, 945), abs=0.5)


def test_caben_en_la_core_one_l(piezas):
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
