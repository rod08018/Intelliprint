"""El kit de geometría construyendo de verdad en FreeCAD (F5.18 (kit)).

Los volúmenes esperados están hechos a mano, no sacados de una ejecución:

- Caja 20×10×5 con un agujero pasante vertical de Ø4:
  1000 − π·2²·5 = 937.17 mm³.
- La lágrima de radio r añade a su círculo una cometa de área r² de la que
  el círculo ya cubre un sector de 90° (πr²/4): área = r²·(1 + 3π/4). Con
  r = 2, 13.425 mm²; atravesando 10 mm de caja, 134.25 mm³ de hueco.
- Redondear R2 las 4 aristas verticales de la caja 20×10×5 quita
  4·(R² − πR²/4)·5 = 4·0.8584·5 = 17.17 mm³.
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


def _construir(codigo: str, tmp_path: Path):
    return build_part(Programa(part="p", codigo=codigo), None, tmp_path, _freecadcmd(),
                      perfil=PERFIL)


def test_un_agujero_pasante_quita_lo_que_dice_la_cuenta(tmp_path):
    r = _construir("""
def construir(kit):
    return kit.caja(20, 10, 5).taladrar("centro", 4, en=(10, 5, 5))
""", tmp_path)
    assert r.volume_mm3 == pytest.approx(1000 - math.pi * 4 * 5, abs=0.01)
    assert (tmp_path / "p.stl").exists() and (tmp_path / "p.step").exists()


def test_cada_agujero_queda_registrado_con_su_nombre(tmp_path):
    """Es lo que la medida (F2.6 (dfm), F2.12 (aserciones)) comparará con
    los requisitos: sin nombre no se sabe qué agujero es cuál."""
    r = _construir("""
def construir(kit):
    p = kit.caja(20, 10, 5)
    for i, x in enumerate([5, 15]):
        p = p.taladrar(f"fijacion_{i + 1}", 3, en=(x, 5, 5))
    return p
""", tmp_path)
    assert [x["nombre"] for x in r.rasgos] == ["fijacion_1", "fijacion_2"]
    assert r.rasgos[1]["entrada"] == [15, 5, 5] and r.rasgos[1]["diametro_mm"] == 3


def test_el_tornillo_usa_el_diametro_del_perfil_y_no_uno_de_memoria(tmp_path):
    r = _construir("""
def construir(kit):
    return kit.caja(20, 10, 5).tornillo("pared", "M3", en=(10, 5, 5))
""", tmp_path)
    assert r.rasgos[0]["diametro_mm"] == PERFIL["holes"]["M3_through_mm"]


def test_la_lagrima_tiene_el_area_de_la_cuenta(tmp_path):
    r = _construir("""
def construir(kit):
    return kit.caja(20, 10, 20).taladrar("eje", 4, en=(10, 0, 10), eje="y", lagrima=True)
""", tmp_path)
    hueco = 4 * (1 + 3 * math.pi / 4) * 10
    assert r.volume_mm3 == pytest.approx(20 * 10 * 20 - hueco, abs=0.05)


def test_redondear_las_aristas_verticales(tmp_path):
    r = _construir("""
def construir(kit):
    return kit.caja(20, 10, 5).redondear(2, aristas="verticales")
""", tmp_path)
    assert r.volume_mm3 == pytest.approx(1000 - 4 * (4 - math.pi) * 5, abs=0.01)


def test_una_escuadra_con_cartela_por_extrusion(tmp_path):
    """Lo que el catálogo cerrado no podía: la L y su cartela son un perfil
    extruido, no un prisma macizo. Área de la L (60×10 + 10×50) y del
    triángulo de catetos 30 (450), por 20 de ancho."""
    r = _construir("""
def construir(kit):
    l = kit.extruir([(0, 0), (60, 0), (60, 10), (10, 10), (10, 60), (0, 60)], 20, plano="xz")
    cartela = kit.extruir([(10, 10), (40, 10), (10, 40)], 20, plano="xz")
    return l + cartela
""", tmp_path)
    assert r.volume_mm3 == pytest.approx((600 + 500 + 450) * 20, abs=0.01)
    assert r.solids == 1


def test_un_error_del_programa_vuelve_con_su_linea(tmp_path):
    with pytest.raises(ConstruccionFallida, match="línea 4"):
        _construir("""
def construir(kit):
    p = kit.caja(20, 10, 5)
    return p.taladrar("perdido", 3, en=(100, 100, 100))
""", tmp_path)


def test_un_programa_prohibido_no_llega_a_freecad(tmp_path):
    with pytest.raises(ValueError, match="import"):
        _construir("import os\ndef construir(kit):\n    return kit.caja(1, 1, 1)", tmp_path)
    assert not (tmp_path / "build.py").exists()


def test_el_ejemplo_del_prompt_se_construye(tmp_path):
    """El ejemplo es lo que más copia el modelo. La primera versión dibujaba
    de pie una escuadra que decía «tumbada» y avellanaba la cara que apoya
    en la pared: un ejemplo roto enseña el error."""
    import re

    md = Path("config/agents/disenador_kit.md").read_text(encoding="utf-8")
    r = _construir(re.search(r"```python\n(.*?)```", md, re.S).group(1), tmp_path)
    assert r.solids == 1
    assert r.bbox_mm[2] == pytest.approx(28)   # tumbada: el ancho es la altura
    assert [x["nombre"] for x in r.rasgos] == ["pared_1", "pared_2"]


def test_redondear_verticales_con_un_agujero_solo_redondea_el_contorno(tmp_path):
    """Se sospechó de la costura vertical de los agujeros como causa de los
    redondeos fallidos del banco (2026-11-04); este test la descartó: pasa sin
    tocar nada. Queda como oráculo del redondeo con agujeros.
    Cuenta: 1000 − π·2²·5 (agujero) − 4·(1 − π/4)·5 (redondeo R1 de las
    cuatro aristas exteriores) = 932.876 mm³."""
    r = _construir("""
def construir(kit):
    p = kit.caja(20, 10, 5).taladrar("centro", 4, en=(10, 5, 5))
    return p.redondear(1, aristas="verticales")
""", tmp_path)
    assert r.volume_mm3 == pytest.approx(1000 - math.pi * 4 * 5 - 4 * (1 - math.pi / 4) * 5,
                                         abs=0.01)


def test_un_agujero_que_no_toca_la_pieza_es_un_error(tmp_path):
    """Fallo real del banco: el gancho taladraba a 40 mm en una placa de 30
    de alto, un agujero caía fuera y la pieza salía sin él, en silencio."""
    with pytest.raises(ConstruccionFallida, match="pared_2.*no toca"):
        _construir("""
def construir(kit):
    p = kit.caja(6, 30, 20)
    p = p.taladrar("pared_1", 4.5, en=(6, 10, 10), eje="-x")
    return p.taladrar("pared_2", 4.5, en=(6, 50, 10), eje="-x")
""", tmp_path)


def test_un_redondeo_que_no_cabe_en_una_arista_no_tira_la_pieza(tmp_path):
    """Fallo real del banco (2026-11-04): el soporte del MG996R y el clip se
    construían bien, con todos sus agujeros, y morían en el redondeo final
    de acabado porque R1 no cabía en alguna arista. La función manda: la
    arista donde no cabe se queda viva, con un aviso, y la pieza sale.
    Aquí un nervio de 1.5 mm: R1 cabe en cada arista suya por separado,
    pero no en las dos a la vez."""
    r = _construir("""
def construir(kit):
    p = kit.caja(20, 10, 5) + kit.caja(1.5, 10, 10, en=(9, 0, 4))
    return p.redondear(1, aristas="verticales")
""", tmp_path)
    assert r.solids == 1
    assert any("vivas" in a for a in r.avisos)
