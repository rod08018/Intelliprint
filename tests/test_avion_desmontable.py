"""Lo que salió de comparar el avión con el Stallion de Flightory, construido
(F13.7 (desmontable), F13.8 (choques), F13.9 (juntas), F13.10 (mandos) y
F13.12 (pilón)).

Medido a mano el 2026-11-18 en la versión 9: los largueros se cortaban en el
centro; dos tramos se pegaban solo por el canto de su piel (326 a 570 mm²;
los del Stallion, de 1 394 a 3 534); el empuje de los rotores colgaba del
pilón, pegado a 0,6 mm de piel; y el elevón no tenía bisagras ni cuerno.

Se construyen las piezas que tocan esos arreglos y, como sólidos, los tubos
comprados, y se miden en su sitio, montadas.
"""

import copy
import json
import math
import struct
from pathlib import Path

import pytest

from mech_toolkit import avion
from orchestrator.build import build_part
from orchestrator.schemas.programa import Programa
from tests.test_generators import _freecadcmd
from tests.test_sondas import PERFIL

CAMA = (300.0, 300.0, 330.0)
HOY = json.loads(Path("scripts/avion_vtol.json").read_text(encoding="utf-8"))["diseno"]
NUEVO = copy.deepcopy(HOY)
NUEVO.update({"desmontable": True, "juntas": True, "mandos": {"bisel": 30.0},
              "pilon_atornillado": True})

PIEZAS = ["raiz-d-1", "raiz-d-2", "raiz-i-1", "centro-2", "ala-d-1", "ala-i-1", "ala-d-2",
          "elevon-d-2", "pilon-d"]
TUBOS = ["tubo-manguito-d", "tubo-manguito-i", "tubo-larguero-10-d", "tubo-larguero-10-i",
         "tubo-larguero-6-d", "tubo-pasador-d", "tubo-viga-d"]


def _construir(raiz, nombre, llamada):
    codigo = (f"def construir(kit):\n    diseno = {NUEVO!r}\n"
              f"    return {llamada}\n")
    carpeta = raiz / nombre
    build_part(Programa(part=nombre, codigo=codigo), None, carpeta, _freecadcmd(),
               perfil=PERFIL)
    return carpeta


@pytest.fixture(scope="module")
def hechas(tmp_path_factory):
    if _freecadcmd() is None:
        pytest.skip("sin freecadcmd")
    raiz = tmp_path_factory.mktemp("avion-desmontable")
    out = {p: _construir(raiz, p, f'kit.avion_pieza(diseno, "{p}")') for p in PIEZAS}
    out.update({t: _construir(raiz, t, f'kit.avion_dentro(diseno, "{t}")') for t in TUBOS})
    return out


def _huecos(hechas, pares):
    from mech_toolkit.geometry import Placement

    from orchestrator.assembly import pair_gaps
    steps = {n: hechas[n] / f"{n}.step" for par in pares for n in par}
    cuadro = {0.0: {n: Placement() for n in steps}}
    return {(h["a"], h["b"]): h["gap_mm"]
            for h in pair_gaps(steps, {}, cuadro, pares, _freecadcmd())}


def test_los_tubos_comprados_no_atraviesan_ninguna_pieza(hechas):
    pares = [("tubo-manguito-d", "raiz-d-1"), ("tubo-manguito-d", "centro-2"),
             ("tubo-manguito-i", "centro-2"), ("tubo-manguito-i", "raiz-i-1"),
             ("tubo-larguero-10-d", "ala-d-1"), ("tubo-larguero-10-d", "ala-d-2"),
             ("tubo-larguero-10-i", "ala-i-1"), ("tubo-larguero-6-d", "ala-d-1"),
             ("tubo-pasador-d", "raiz-d-2"), ("tubo-pasador-d", "ala-d-1"),
             ("tubo-viga-d", "pilon-d")]
    huecos = _huecos(hechas, pares)
    assert all(h >= 0 for h in huecos.values()), huecos


def test_las_piezas_montadas_no_se_atraviesan(hechas):
    """El ala contra su raíz (y sus orejas), el pilón contra el ala y el
    elevón contra su tramo."""
    pares = [("ala-d-1", "raiz-d-1"), ("ala-d-1", "raiz-d-2"), ("ala-i-1", "raiz-i-1"),
             ("pilon-d", "ala-d-1"), ("elevon-d-2", "ala-d-2"), ("ala-d-1", "ala-d-2")]
    huecos = _huecos(hechas, pares)
    assert all(h >= 0 for h in huecos.values()), huecos


# --- las juntas -------------------------------------------------------------------

def _triangulos(stl):
    b = Path(stl).read_bytes()
    n = struct.unpack("<I", b[80:84])[0]
    return [[struct.unpack("<3f", b[84 + k * 50 + 12 + v * 12:84 + k * 50 + 24 + v * 12])
             for v in range(3)] for k in range(n)]


def _cara(stl, y, paso=0.5):
    """Las celdas (x, z) de una rejilla de `paso` mm cubiertas por los
    triángulos de la pieza que están en el plano `y`."""
    celdas = set()
    for t in _triangulos(stl):
        if not all(abs(p[1] - y) < 0.05 for p in t):
            continue
        (ax, _, az), (bx, _, bz), (cx, _, cz) = t
        xs, zs = (ax, bx, cx), (az, bz, cz)
        den = (bz - cz) * (ax - cx) + (cx - bx) * (az - cz)
        if abs(den) < 1e-12:
            continue
        for i in range(math.floor(min(xs) / paso), math.ceil(max(xs) / paso) + 1):
            for j in range(math.floor(min(zs) / paso), math.ceil(max(zs) / paso) + 1):
                px, pz = (i + 0.5) * paso, (j + 0.5) * paso
                u = ((bz - cz) * (px - cx) + (cx - bx) * (pz - cz)) / den
                v = ((cz - az) * (px - cx) + (ax - cx) * (pz - cz)) / den
                if u >= 0 and v >= 0 and u + v <= 1:
                    celdas.add((i, j))
    return celdas


def test_dos_tramos_se_pegan_cara_con_cara(hechas):
    """Al menos 1 000 mm² comunes (criterio del asistente): lo que tienen de
    material las dos caras a la vez, contado en una rejilla de 0,5 mm."""
    y = avion._tramos_ala(NUEVO)[0][1]
    comun = (_cara(hechas["ala-d-1"] / "ala-d-1.stl", y)
             & _cara(hechas["ala-d-2"] / "ala-d-2.stl", y))
    assert len(comun) * 0.25 >= 1000, len(comun) * 0.25


# --- el pilón -----------------------------------------------------------------------

def _material_en_vertical(stl, x, y):
    """Los mm de pieza que cruza la recta vertical por (x, y)."""
    cortes = []
    for t in _triangulos(stl):
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = t
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-12:
            continue
        u = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / den
        v = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / den
        if u >= 0 and v >= 0 and u + v <= 1:
            cortes.append(u * az + v * bz + (1 - u - v) * cz)
    cortes.sort()
    return sum(b - a for a, b in zip(cortes[0::2], cortes[1::2]))


def test_los_tornillos_del_pilon_cruzan_un_teton_y_no_solo_la_piel(hechas):
    """Por la recta de cada M3, el ala tiene casi todo su grueso de material
    (el tetón), no dos pieles de 0,6. A un lado del agujero, para no caer en
    él: a 2,5 mm de su eje."""
    for x, y in avion._tornillos_pilon_en(NUEVO):
        arriba, abajo = avion._caras_en(NUEVO, y)
        grueso = avion._z_cara(arriba, x) - avion._z_cara(abajo, x)
        lleno = _material_en_vertical(hechas["ala-d-1"] / "ala-d-1.stl", x + 2.5, y)
        assert lleno > 0.8 * grueso, (x, y, lleno, grueso)


# --- todas ---------------------------------------------------------------------------

def _caja(carpeta):
    e = json.loads((carpeta / "envolvente.json").read_text(encoding="utf-8"))
    return e["min"], e["max"]


def test_caben_en_la_core_one_l(hechas):
    from orchestrator.medida import no_cabe_en_la_impresora
    grandes = {}
    for id_ in PIEZAS:
        lo, hi = _caja(hechas[id_])
        if no_cabe_en_la_impresora([b - a for a, b in zip(lo, hi)], CAMA):
            grandes[id_] = [round(b - a) for a, b in zip(lo, hi)]
    assert grandes == {}


def test_se_imprimen_sin_soportes(hechas):
    from orchestrator.voladizos import como_imprimir
    piden = {}
    for id_ in PIEZAS:
        postura, zonas = como_imprimir(hechas[id_] / f"{id_}.stl", PERFIL["overhang_max_deg"],
                                       PERFIL["bridge_max_mm"])
        if postura is None:
            piden[id_] = min(len(z) for z in zonas.values())
    assert piden == {}
