"""Partir una pieza en tramos que caben en la cama: F11.3 (tramos), ADR-022.

Una carcasa de 400 mm no cabe en una cama de 235. `pieza.partir` la corta
por planos y pone en cada corte una unión a media madera: el tramo de antes
se queda con la parte de dentro de la pared (la lengüeta) y el de después
con la de fuera (el labio). La pieza entera no cambia; los tramos son cómo
se imprime.

Cada volumen esperado es una cuenta a mano, escrita en su test. La holgura
es la de deslizar del perfil: 0,2 mm.
"""

import math
from pathlib import Path

import pytest
import yaml

from orchestrator.build import ConstruccionFallida, build_part
from orchestrator.schemas.programa import Programa
from tests.test_generators import _freecadcmd

pytestmark = pytest.mark.skipif(_freecadcmd() is None, reason="sin freecadcmd")

PERFIL = yaml.safe_load(Path("config/printers/ankermake_m5_plamas.yaml").read_text(encoding="utf-8"))
CAMA = (235, 235, 250)


def _construir(codigo: str, tmp_path: Path):
    return build_part(Programa(part="p", codigo=codigo), None, tmp_path, _freecadcmd(),
                      perfil=PERFIL)


TUBO = """
def construir(kit):
    tubo = kit.caja(100, 60, 40) - kit.caja(102, 52, 32, en=(-1, 4, 4))
    return tubo.partir(eje="x", en=[50], lengueta=10, labio=2)
"""


def test_un_tubo_partido_en_dos_reparte_la_pared_entre_lengueta_y_labio(tmp_path):
    """Tubo de 60 × 40 con pared de 4, de 100 de largo, cortado en x = 50.
    La sección de la pared mide 60·40 − 52·32 = 736 mm²; cada mitad, 36 800.

    Con labio de 2, la lengüeta es lo de dentro: 56·36 − 52·32 = 352 mm²,
    por 10 de largo: 3 520. El primer tramo: 36 800 + 3 520 = 40 320.

    Al segundo se le quita la lengüeta con 0,2 de holgura a los lados y al
    fondo: (56,4·36,4 − 4·(1 − π/4)·0,2² − 52·32) · 10,2 = 3 967,04. Queda
    en 32 832,96."""
    r = _construir(TUBO, tmp_path)
    antes, despues = r.tramos
    assert antes["volume_mm3"] == pytest.approx(40320, abs=0.5)
    hueco = (56.4 * 36.4 - 4 * (1 - math.pi / 4) * 0.2 ** 2 - 52 * 32) * 10.2
    assert despues["volume_mm3"] == pytest.approx(36800 - hueco, abs=0.5)
    # El primero llega hasta el final de su lengüeta: x de 0 a 60.
    assert antes["bbox_mm"] == pytest.approx([60, 60, 40], abs=0.01)
    assert despues["bbox_mm"] == pytest.approx([50, 60, 40], abs=0.01)
    for t in r.tramos:
        assert (tmp_path / t["stl"]).is_file()


def test_la_pieza_entera_no_cambia_al_partirla(tmp_path):
    """Se sigue midiendo y montando como una: su volumen es el del tubo,
    736 · 100, y su STL sigue siendo el de la pieza entera."""
    r = _construir(TUBO, tmp_path)
    assert r.volume_mm3 == pytest.approx(73600, abs=0.5)
    assert r.bbox_mm == pytest.approx([100, 60, 40], abs=0.01)
    assert sorted(p.name for p in tmp_path.glob("*.stl")) == ["p.stl"]


def test_una_cascara_abierta_por_debajo_lleva_la_lengueta_por_dentro(tmp_path):
    """Casi todas las carcasas: abiertas por debajo, y el corte es una U,
    que no tiene «dentro» propio. Se cierra con su contorno convexo.

    La U mide 60·40 − 52·36 = 528 mm²; cada mitad, 26 400. Lo de dentro, a 2
    del contorno: 56·36 − 52·34 = 248 mm², por 10: 2 480. El primer tramo,
    28 880. Al segundo se le quita (56,4·36,4 − 4·(1 − π/4)·0,2² − 52·34,2)
    · 10,2 = 2 800,16: queda en 23 599,84."""
    r = _construir("""
def construir(kit):
    carcasa = kit.caja(100, 60, 40) - kit.caja(102, 52, 37, en=(-1, 4, -1))
    return carcasa.partir(eje="x", en=[50], lengueta=10, labio=2)
""", tmp_path)
    antes, despues = r.tramos
    assert antes["volume_mm3"] == pytest.approx(28880, abs=0.5)
    hueco = (56.4 * 36.4 - 4 * (1 - math.pi / 4) * 0.2 ** 2 - 52 * 34.2) * 10.2
    assert despues["volume_mm3"] == pytest.approx(26400 - hueco, abs=0.5)


CARCASA_DE_400 = """
LARGO = 400
PARED = 2.4

def construir(kit):
    carcasa = kit.caja(LARGO, 80, 60) - kit.caja(LARGO - 2 * PARED, 80 - 2 * PARED, 60,
                                                 en=(PARED, PARED, -PARED))
    # Los tornillos que cierran la unión, en la pieza entera: entran por el
    # labio y siguen por la lengüeta, que va de x = 200 a 212.
    carcasa = carcasa.tornillo("union_1", "M3", en=(206, 0, 30), eje="+y", tipo="rosca",
                               profundidad=3, lagrima=True)
    carcasa = carcasa.tornillo("union_2", "M3", en=(206, 80, 30), eje="-y", tipo="rosca",
                               profundidad=3, lagrima=True)
    return carcasa.partir(eje="x", en=[200], lengueta=12)
"""


def test_una_carcasa_de_400_sale_en_dos_tramos_que_caben_en_la_cama(tmp_path):
    """El criterio de la fila: 400 mm no caben en 235 × 235 × 250; partida
    en x = 200, un tramo mide 212 (con su lengüeta) y el otro 200."""
    from orchestrator.medida import no_cabe_en_la_impresora, tramos_que_no_caben
    r = _construir(CARCASA_DE_400, tmp_path)
    assert no_cabe_en_la_impresora(r.bbox_mm, CAMA) != []
    assert [t["bbox_mm"][0] for t in r.tramos] == pytest.approx([212, 200], abs=0.01)
    assert tramos_que_no_caben(r, CAMA) == []


def test_los_agujeros_de_un_lado_caen_frente_a_los_del_otro(tmp_path):
    """Medido en los tramos ya partidos, no en la pieza entera: por el eje de
    cada tornillo, una broca fina no toca ninguno de los dos tramos y una
    gruesa toca los dos. Los dos de la carcasa cierran su corte."""
    from orchestrator.medida import cortes_sin_cerrar
    r = _construir(CARCASA_DE_400, tmp_path)
    [corte] = r.cortes
    assert corte["en"] == 200 and corte["tornillos"] == ["union_1", "union_2"]
    assert cortes_sin_cerrar(r) == []


def test_un_corte_sin_tornillo_que_lo_cierre_es_un_defecto(tmp_path):
    """El tubo de arriba no lleva ninguno: los dos tramos se separarían."""
    from orchestrator.medida import cortes_sin_cerrar
    [d] = cortes_sin_cerrar(_construir(TUBO, tmp_path))
    assert "x = 50" in d and "tornillo" in d and "de 50 a 60" in d


def test_un_tramo_que_sigue_sin_caber_se_dice_con_su_medida(tmp_path):
    """Partida por x = 100, el segundo tramo mide 300: tampoco cabe."""
    from orchestrator.medida import tramos_que_no_caben
    r = _construir(CARCASA_DE_400.replace("en=[200]", "en=[100]"), tmp_path)
    [d] = tramos_que_no_caben(r, CAMA)
    assert "tramo 2" in d and "300" in d


def test_a_la_pieza_que_no_cabe_se_le_dice_que_se_puede_partir():
    from orchestrator.medida import no_cabe_en_la_impresora
    [d] = no_cabe_en_la_impresora([400, 80, 60], CAMA)
    assert "partir" in d


def test_donde_la_pieza_se_estrecha_no_se_puede_cortar_y_dice_por_que(tmp_path):
    """Un cono hueco: 10 mm más allá del corte la pared ya está 2 mm más
    adentro, y una lengüeta recta se saldría por ella."""
    with pytest.raises(ConstruccionFallida) as fallo:
        _construir("""
def construir(kit):
    cono = kit.cono(60, 20, 100) - kit.cono(54, 14, 100)
    return cono.partir(eje="z", en=[50], lengueta=10)
""", tmp_path)
    assert "se estrecha" in str(fallo.value) and "z = 50" in str(fallo.value)


def test_una_pared_demasiado_fina_para_la_union_dice_cuanto_hace_falta(tmp_path):
    """Pared de 1 mm: no da para un labio y una lengüeta de 0,8 cada uno."""
    with pytest.raises(ConstruccionFallida) as fallo:
        _construir("""
def construir(kit):
    fina = kit.caja(100, 60, 40) - kit.caja(102, 58, 38, en=(-1, 1, 1))
    return fina.partir(eje="x", en=[50], lengueta=10)
""", tmp_path)
    assert "la pared mide 1.0 mm" in str(fallo.value)


def test_al_disenador_se_le_dice_cuando_y_como_partir():
    texto = Path("config/agents/disenador_kit.md").read_text(encoding="utf-8")
    assert "partir(" in texto and "lengüeta" in texto and "no cabe" in texto
