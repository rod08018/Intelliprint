"""Lo impreso del ala volante se pesa en sus STL (`scripts/avion_vtol_masas.py`).

El dimensionado lo estimaba (0,94 kg) mientras las piezas, macizas, pesaban
de 6 a 7 kg. Lo esperado aquí está contado a mano.
"""

import importlib.util
import struct
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("avion_vtol_masas",
                                               RAIZ / "scripts" / "avion_vtol_masas.py")
masas = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(masas)


def _caja(lo, hi, hacia_fuera=True):
    """Los 12 triángulos de una caja, con la normal hacia fuera (o hacia
    dentro, para el hueco)."""
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    caras = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (1, 2, 6, 5), (0, 4, 7, 3)]
    tri = []
    for a, b, c, d in caras:
        for t in ((a, b, c), (a, c, d)):
            tri.append([v[i] for i in (t if hacia_fuera else t[::-1])])
    return tri


def _stl(ruta, triangulos):
    ruta.parent.mkdir(parents=True)
    datos = bytearray(80) + struct.pack("<I", len(triangulos))
    for t in triangulos:
        datos += struct.pack("<12fH", 0, 0, 0, *[c for p in t for c in p], 0)
    ruta.write_bytes(bytes(datos))


def test_el_dimensionado_cuenta_lo_pesado_de_todas_las_piezas():
    """El JSON del dimensionado lleva lo que pesaron las 44 piezas, no su
    estimación de piel por área."""
    import json
    pesado = json.loads((RAIZ / "scripts" / "avion_vtol_impreso.json").read_text(encoding="utf-8"))
    dim = json.loads((RAIZ / "scripts" / "avion_vtol.json").read_text(encoding="utf-8"))
    assert pesado["piezas_contadas"] == 44
    assert dim["masa_kg"]["impreso, pesado en sus STL"] == pytest.approx(pesado["masa_kg"], abs=1e-3)
    assert dim["impreso_pesado_en"] == pesado["proyecto"]


def test_las_alas_son_de_lw_pla_y_el_resto_de_petg():
    """Él, el 2026-11-16: «las alas son de lw pla el resto de petg», ambos
    Prusament. El PETG de Prusament pesa 1,27 g/cm³ (su hoja técnica, ISO
    1183). El cuerpo central es el resto: no es ala."""
    for id_ in ("raiz-d-1", "ala-i-6", "elevon-d-4"):
        assert masas.material(id_)[0] == "LW-PLA", id_
    for id_ in ("centro-3", "panza", "tapa-servo-d-interior", "gondola-d-delante", "pilon-i",
                "pata-d", "deriva-i"):
        assert masas.material(id_) == ("PETG", 1.27), id_


def test_una_caja_hueca_de_piel_fina_pesa_su_volumen_por_la_densidad(tmp_path):
    """Un cubo de 20 mm con 0,6 mm de pared: 20³ − 18,8³ = 1355,3 mm³. Más
    fino que la cáscara del perfil, se imprime macizo: a 0,6 g/cm³, 0,8132 g.
    Su centro, el del cubo."""
    tri = _caja((0, 0, 0), (20, 20, 20)) + _caja((0.6, 0.6, 0.6), (19.4, 19.4, 19.4), False)
    _stl(tmp_path / "nodos" / "ala-d-1" / "parts" / "v1" / "ala-d-1.stl", tri)
    r = masas.pesar(tmp_path)
    p = r["piezas"]["ala-d-1"]
    assert p["volumen_cm3"] == pytest.approx(1.4, abs=0.05)
    assert r["masa_kg"] == pytest.approx(1355.3e-3 * 0.6 / 1000, rel=1e-3)
    assert r["centro_mm"] == pytest.approx([10, 10, 10], abs=0.05)
