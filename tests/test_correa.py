"""La correa GT2 y sus poleas (F10.3 (correa), ADR-021).

Los dientes los genera el código, no el modelo: una polea sale de una
fórmula con parámetros y tiene oráculo. Los de aquí no salen del sistema:

- **Diámetros**, de la tabla «2mm - PowerGrip GT / 2MR» de Pfeifer
  Industries (pfeiferindustries.com, «Timing Belt Pulley PD and OD»):
  20 dientes, 12,73 de primitivo y 12,22 de exterior; 60 dientes, 38,20 y
  37,69; 80 dientes, 50,93 y 50,42.
- **La correa**, del manual técnico de SDP/SI (sdp-si.com,
  D820 «Technical Section», sección 22): con dos poleas iguales,
  C = p·(NB − N1)/2; con dos distintas, 2C·sen φ = L − π(R1 + R2) −
  (π − 2φ)(R1 − R2), con C·cos φ = R1 − R2.
- **Los volúmenes**, a mano, con el área de la lente que dos círculos se
  quitan uno a otro. Van en el docstring de su test.
"""

import math
from pathlib import Path

import pytest
import yaml

from tests.test_generators import _freecadcmd

PERFIL = yaml.safe_load(Path("config/printers/ankermake_m5_plamas.yaml").read_text(encoding="utf-8"))


# --- las cuentas ----------------------------------------------------------------------------

@pytest.mark.parametrize("dientes, primitivo, exterior", [
    (20, 12.73, 12.22), (60, 38.20, 37.69), (80, 50.93, 50.42)])
def test_los_diametros_de_una_polea_son_los_de_la_tabla(dientes, primitivo, exterior):
    from mech_toolkit.transmisiones import diametro_exterior, diametro_primitivo
    assert diametro_primitivo(dientes) == pytest.approx(primitivo, abs=0.006)
    assert diametro_exterior(dientes) == pytest.approx(exterior, abs=0.006)


def test_con_dos_poleas_iguales_la_correa_son_dos_tramos_y_una_vuelta():
    """Dos poleas de 20 dientes a 80 mm: dos tramos rectos de 80 y media
    vuelta en cada una, 160 + 20 × 2 = 200 mm, 100 dientes. Y al revés,
    como lo da el manual: C = p·(NB − N1)/2 = 2 × (100 − 20)/2 = 80."""
    from mech_toolkit.transmisiones import distancia_entre_ejes, largo_de_correa
    assert largo_de_correa(20, 20, 80) == pytest.approx(200)
    assert distancia_entre_ejes(20, 20, 100) == pytest.approx(80)


def test_el_largo_de_la_correa_entre_una_polea_de_20_y_una_de_80():
    """A 60 mm entre ejes, a mano. Radios primitivos: 80/π = 25,465 y
    20/π = 6,366; su diferencia, 19,099.

    - cos φ = 19,099 / 60 = 0,31831 → φ = 1,24685 rad; sen φ = 0,94799.
    - L = 2 × 60 × 0,94799 + π × 31,831 + (π − 2 × 1,24685) × 19,099
        = 113,759 + 100,000 + 12,374 = 226,13 mm.

    La fórmula corta de los libros, 2C + π(D + d)/2 + (D − d)²/(4C), da
    120 + 100 + 38,197² / 240 = 226,08: lo mismo con medio diente de
    diferencia en cien."""
    from mech_toolkit.transmisiones import largo_de_correa
    assert largo_de_correa(20, 80, 60) == pytest.approx(226.13, abs=0.01)
    assert largo_de_correa(80, 20, 60) == pytest.approx(226.13, abs=0.01)


def test_la_distancia_entre_ejes_que_pide_una_correa():
    """Una correa de 140 dientes (280 mm) entre una polea de 20 y una de 80.
    Con la fórmula corta: 280 = 2C + 100 + 1459,0/(4C) → 2C² − 180C +
    364,75 = 0 → C = (180 + √(32400 − 2918)) / 4 = 87,93 mm. La exacta
    tiene que devolver los 280 mm al volver a medir la correa."""
    from mech_toolkit.transmisiones import distancia_entre_ejes, largo_de_correa
    c = distancia_entre_ejes(20, 80, 140)
    assert c == pytest.approx(87.93, abs=0.05)
    assert largo_de_correa(20, 80, c) == pytest.approx(280, abs=1e-6)


def test_una_correa_que_no_abraza_las_dos_poleas_no_tiene_distancia():
    """Con las poleas de 20 y 80 tocándose (ejes a 31,83 mm, la suma de sus
    radios primitivos) la correa ya mide 175,5 mm: una de 80 dientes,
    160 mm, no llega."""
    from mech_toolkit.transmisiones import distancia_entre_ejes
    assert distancia_entre_ejes(20, 80, 80) is None


def test_la_polea_conducida_sale_de_la_relacion():
    """4:1 con la polea de 20 del motor son 80 dientes. Una relación que no
    da dientes enteros no existe: 20 × 2,33 = 46,6."""
    from mech_toolkit.transmisiones import dientes_de_la_conducida
    assert dientes_de_la_conducida(20, 4) == 80
    assert dientes_de_la_conducida(20, 2.5) == 50
    with pytest.raises(ValueError, match="46.6"):
        dientes_de_la_conducida(20, 2.33)


def test_la_correa_que_cabe_en_una_distancia_con_su_ajuste():
    """Los ejes a 88 mm con ±2 mm de colisa: entre 86 y 90 mm. La de 140
    dientes pide 87,93 (cabe); la de 139, 86,90 (cabe); la de 141, 88,95
    (cabe). Se elige la que queda más cerca del centro del ajuste: 140."""
    from mech_toolkit.transmisiones import correa_para
    c = correa_para(20, 80, 88, ajuste=2)
    assert c["dientes"] == 140 and c["largo_mm"] == 280
    assert c["entre_ejes_mm"] == pytest.approx(87.93, abs=0.05)
    # Sin ajuste no hay correa que dé 88,5 mm justos: ninguna cae a ±0,2.
    assert correa_para(20, 80, 88.45, ajuste=0.2) is None


# --- la polea, construida de verdad ---------------------------------------------------------

con_freecad = pytest.mark.skipif(_freecadcmd() is None, reason="sin freecadcmd")


def _construir(codigo: str, tmp_path: Path):
    from orchestrator.build import build_part
    from orchestrator.schemas.programa import Programa
    return build_part(Programa(part="p", codigo=codigo), None, tmp_path, _freecadcmd(),
                      perfil=PERFIL)


def _lente(R: float, r: float) -> float:
    """El área que un círculo de radio r con el centro en el borde de otro
    de radio R le quita a este: r²·acos(r/2R) + R²·acos(1 − r²/2R²) −
    (r/2)·√(4R² − r²)."""
    return (r * r * math.acos(r / (2 * R)) + R * R * math.acos(1 - r * r / (2 * R * R))
            - r / 2 * math.sqrt(4 * R * R - r * r))


@con_freecad
def test_una_polea_de_80_dientes_tiene_80_ranuras(tmp_path):
    """Sin pestañas, para una correa de 6 mm: 9 mm de ancho (el manual pide
    3 mm más que la correa si no hay pestañas). Es un cilindro del diámetro
    exterior, 50,42 mm, con 80 ranuras semicirculares con el centro en su
    borde y el radio del alto del diente de la correa, 0,76 mm (manual de
    SDP/SI, figura 19g). Entre ranura y ranura quedan 0,46 mm de cresta.

    Cada ranura quita una lente de 0,9015 mm²: (π × 25,211² − 80 × 0,9015)
    × 9 = 17 321,6 mm³. Con 79 u 81 ranuras saldrían 8 mm³ de más o de
    menos."""
    r = _construir("""
def construir(kit):
    return kit.polea_gt2("polea", 80, pestanas=False)
""", tmp_path)
    R = (160 / math.pi - 0.508) / 2
    assert r.volume_mm3 == pytest.approx(17321.6, abs=1.5)
    assert (math.pi * R * R - 80 * _lente(R, 0.76)) * 9 == pytest.approx(17321.6, abs=0.1)
    [polea] = [x for x in r.rasgos if x["tipo"] == "polea_gt2"]
    assert polea["dientes"] == 80 and polea["ancho_mm"] == 9
    assert polea["primitivo_mm"] == pytest.approx(50.93, abs=0.006)
    assert polea["centro"] == [0, 0, 0] and polea["eje"] == [0, 0, 1]


@con_freecad
def test_las_pestanas_son_dos_conos_que_se_imprimen_sin_soportes(tmp_path):
    """Con pestañas la cara de los dientes mide 7 mm (1 más que la correa,
    según el manual) y a cada lado va un cono de 1,5 mm de alto —la altura
    nominal de pestaña para 2 mm GT— que sube a 45° del diámetro exterior a
    3 mm más. Un tronco de cono: π·h/3·(R² + R·r + r²).

    Con 20 dientes (R = 6,112): dientes, (π × 6,112² − 20 × 0,8833) × 7 =
    697,9 mm³; cada cono, π × 1,5/3 × (7,612² + 7,612 × 6,112 + 6,112²) =
    222,8 mm³. En total, 1 143,5 mm³, y 10 mm de alto."""
    r = _construir("""
def construir(kit):
    return kit.polea_gt2("polea", 20, en=(10, 0, 5))
""", tmp_path)
    R = (40 / math.pi - 0.508) / 2
    cono = math.pi * 1.5 / 3 * ((R + 1.5) ** 2 + (R + 1.5) * R + R * R)
    assert r.volume_mm3 == pytest.approx(1143.5, abs=1.0)
    assert (math.pi * R * R - 20 * _lente(R, 0.76)) * 7 + 2 * cono == pytest.approx(1143.5,
                                                                                    abs=0.1)
    [polea] = [x for x in r.rasgos if x["tipo"] == "polea_gt2"]
    assert polea["ancho_mm"] == 7 and polea["alto_mm"] == 10
    assert polea["centro"] == [10, 0, 5]


@con_freecad
def test_una_polea_con_muy_pocos_dientes_no_se_hace(tmp_path):
    """Menos de 12 dientes no está ni en la tabla del fabricante: la correa
    no se dobla tanto."""
    from orchestrator.build import ConstruccionFallida
    with pytest.raises(ConstruccionFallida, match="12"):
        _construir("""
def construir(kit):
    return kit.polea_gt2("polea", 8)
""", tmp_path)


# --- lo que se compra ------------------------------------------------------------------------

def test_la_polea_del_motor_tiene_ficha_con_lo_que_dice_su_tienda():
    """Adafruit 1251: 16 mm de largo, 16 mm de diámetro mayor, agujero de
    5 mm y 6 g. Con el agujero de 5: la atraviesa el eje del NEMA 17, que
    mide eso."""
    from orchestrator.componentes import cargar, envolvente
    f = cargar("polea-gt2-20")
    assert envolvente(f) == ([-8, -8, 0], [8, 8, 16])
    assert f.cuerpos[0].cilindro.interior == 5 == cargar("nema17").cuerpos[2].cilindro.diametro
    assert f.masa_g == 6 and not f.da_par()
