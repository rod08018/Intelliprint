"""Medir lo que el banco contaba como «sin medir» (F6.12 (techo)).

13-15 de las 42 exigencias del banco eran «sin medir» y contaban como no
aprobadas: la nota máxima posible era 64 %, y con 62 % (2026-11-04) el
siguiente punto ya no podía salir del diseño. Cada sonda mide la geometría
del STEP en FreeCAD, nunca lo que el diseñador dice de ella.

Cuentas a mano de la resistencia (la pieza de `_L`):
    placa de pared x∈[0,5], brazo x∈[0,50] de 20 (y) × 6 (z), agujeros
    Ø4.5 en x a z=15 y z=35 → la carga va en z (la línea entre agujeros) y
    el brazo en x. Sección del brazo: I = 20·6³/12 = 360 mm⁴, c = 3 mm,
    W = 120 mm³. Con 20 N en la punta, en el arranque (x=5): M = 20·45 =
    900 N·mm, σ = 7.5 MPa. Tumbada (brazo en x, capas en z): 35/7.5 = 4.67.
"""

import math
from pathlib import Path

import pytest
import yaml

from orchestrator.banco import (AristasVivas, Coaxiales, ParedMinima, PasoLibre, Ranura,
                                Resistencia, Retencion, Ventana, medir_sondas)
from orchestrator.build import build_part
from orchestrator.schemas.programa import Programa
from tests.test_generators import _freecadcmd

pytestmark = pytest.mark.skipif(_freecadcmd() is None, reason="sin freecadcmd")

PERFIL = yaml.safe_load(Path("config/printers/ankermake_m5_plamas.yaml").read_text(encoding="utf-8"))
MATERIAL = {"xy_MPa": 35, "z_MPa": 15, "factor_seguridad": 3}


def _step(codigo, tmp_path) -> Path:
    build_part(Programa(part="p", codigo=codigo), None, tmp_path, _freecadcmd(), perfil=PERFIL)
    return tmp_path / "p.step"


def _medir(codigo, aserciones, tmp_path):
    return medir_sondas(_step(codigo, tmp_path), aserciones, _freecadcmd(), MATERIAL)


CAJA = "def construir(kit):\n    return kit.caja(20, 10, 5)\n"
REDONDEADA = "def construir(kit):\n    return kit.caja(20, 10, 5).redondear(1, aristas=\"todas\")\n"


def test_una_caja_de_aristas_vivas_no_pasa_y_redondeada_si(tmp_path):
    a = AristasVivas(tipo="aristas_vivas", max_fraccion=0.1)
    [viva] = _medir(CAJA, [a], tmp_path / "1")
    [suave] = _medir(REDONDEADA, [a], tmp_path / "2")
    assert viva.estado == "no_cumple" and "100 %" in viva.detalle
    assert suave.estado == "cumple"


_L = """
def construir(kit):
    p = kit.caja(5, 20, 40) + kit.caja(50, 20, 6)
    p = p.taladrar("pared_1", 4.5, en=(5, 10, 15), eje="-x")
    return p.taladrar("pared_2", 4.5, en=(5, 10, 35), eje="-x")
"""


def _resistencia(carga):
    return Resistencia(tipo="resistencia", carga_N=carga, fijacion_diametro_mm=4.5,
                       direccion="entre_agujeros", brazo="punta")


def test_la_resistencia_sale_de_la_seccion_real(tmp_path):
    [r] = _medir(_L, [_resistencia(20)], tmp_path)
    assert r.estado == "cumple"
    factor = float(r.detalle.split("factor ")[1].split()[0])
    assert factor == pytest.approx(35 / 7.5, rel=0.05)


def test_si_no_llega_al_factor_no_cumple(tmp_path):
    """Con 40 N: σ = 15 MPa en el arranque, factor 35/15 = 2.33 < 3."""
    [r] = _medir(_L, [_resistencia(40)], tmp_path)
    assert r.estado == "no_cumple"


def test_una_ventana_pasante_deja_pasar_el_cuerpo_del_servo(tmp_path):
    marco = """
def construir(kit):
    return kit.caja(60, 40, 10).quitar("ventana", kit.caja({a}, {b}, 12, en=(9, 9, -1)))
"""
    v = Ventana(tipo="ventana", ancho_mm=40.7, alto_mm=19.7)
    [cabe] = _medir(marco.format(a=42, b=21), [v], tmp_path / "1")
    [no_cabe] = _medir(marco.format(a=38, b=21), [v], tmp_path / "2")
    assert cabe.estado == "cumple" and no_cabe.estado == "no_cumple"


def test_alojamientos_coaxiales_y_paso_libre(tmp_path):
    """Un tubo de Ø30 con alojamiento Ø25.4 abajo y Ø20.4 arriba: coaxiales,
    y deja pasar Ø20 pero no Ø21."""
    tubo = """
def construir(kit):
    p = kit.cilindro(30, 40)
    p = p.taladrar("abajo", 25.4, en=(0, 0, 0), eje="z", profundidad=20)
    return p.taladrar("arriba", 20.4, en=(0, 0, 40), eje="-z", profundidad=21)
"""
    coax = Coaxiales(tipo="coaxiales", diametros_mm=[[25, 26], [20, 21]])
    pasa = PasoLibre(tipo="paso_libre", diametro_mm=20, eje_de_mm=[25, 26])
    no_pasa = PasoLibre(tipo="paso_libre", diametro_mm=21, eje_de_mm=[25, 26])
    r = _medir(tubo, [coax, pasa, no_pasa], tmp_path)
    assert [x.estado for x in r] == ["cumple", "cumple", "no_cumple"]


def test_alojamientos_desalineados_no_son_coaxiales(tmp_path):
    torcido = """
def construir(kit):
    p = kit.caja(40, 40, 40)
    p = p.taladrar("a", 10, en=(20, 20, 0), eje="z", profundidad=15)
    return p.taladrar("b", 8, en=(21, 20, 40), eje="-z", profundidad=15)
"""
    [r] = _medir(torcido, [Coaxiales(tipo="coaxiales", diametros_mm=[[9.9, 10.1], [7.9, 8.1]])],
                 tmp_path)
    assert r.estado == "no_cumple" and "1" in r.detalle


def test_pared_minima(tmp_path):
    """Caja de 20 × 20 × 10 con una cajera que deja 1.2 mm de pared lateral."""
    cajera = """
def construir(kit):
    return kit.caja(20, 20, 10).quitar("cajera", kit.caja({a}, 17.6, 9, en=(1.2, 1.2, 2)))
"""
    pared = ParedMinima(tipo="pared_minima", min_mm=1.8)
    [fina] = _medir(cajera.format(a=17.6), [pared], tmp_path / "1")
    [otra] = _medir(cajera.format(a=10), [pared], tmp_path / "2")
    assert fina.estado == "no_cumple" and "1.2" in fina.detalle
    assert otra.estado == "no_cumple"   # la pared de 1.2 en y sigue ahí


def test_pared_minima_que_cumple(tmp_path):
    cajera = """
def construir(kit):
    return kit.caja(20, 20, 10).quitar("cajera", kit.caja(14, 14, 9, en=(3, 3, 2)))
"""
    [r] = _medir(cajera, [ParedMinima(tipo="pared_minima", min_mm=1.8)], tmp_path)
    assert r.estado == "cumple"


def test_la_boca_del_clip(tmp_path):
    u = """
def construir(kit):
    return kit.caja(40, 30, 20).quitar("boca", kit.caja({b}, 31, 15, en=(10, -0.5, 6)))
"""
    boca = Ranura(tipo="ranura", min_mm=17, max_mm=18)
    [justa] = _medir(u.format(b=17.5), [boca], tmp_path / "1")
    [ancha] = _medir(u.format(b=19), [boca], tmp_path / "2")
    assert justa.estado == "cumple" and ancha.estado == "no_cumple"


def test_el_cable_queda_retenido(tmp_path):
    """Cavidad Ø6 con una abertura de 4 mm: la cuerda de 4 en un radio de 3
    deja abierto 2·asin(2/3) = 83.6°, y abraza 276.4°. Con una abertura de
    6.5, más ancha que el cable, no lo retiene."""
    clip = """
def construir(kit):
    p = kit.caja(20, 20, 10)
    p = p.taladrar("cable", 6, en=(10, 10, 10), eje="-z")
    return p.quitar("abertura", kit.caja({b}, 12, 12, en=(10 - {b} / 2, 10, -1)))
"""
    ret = Retencion(tipo="retencion", diametro_min_mm=5.9, diametro_max_mm=6.8)
    [abraza] = _medir(clip.format(b=4), [ret], tmp_path / "1")
    [suelto] = _medir(clip.format(b=6.5), [ret], tmp_path / "2")
    assert abraza.estado == "cumple" and "276" in abraza.detalle
    assert suelto.estado == "no_cumple"


def test_con_agujeros_a_la_pared_y_a_la_repisa_el_apoyo_es_la_pared(tmp_path):
    """La escuadra de repisa lleva Ø4.5 a la pared y Ø4.5 a la repisa. El
    voladizo cuelga del grupo desde el que la pieza se aleja más (los 50 del
    brazo frente a los 40 de la placa): la misma cuenta que `_L`, 4.67."""
    con_repisa = _L.replace('    return p.taladrar("pared_2"',
                            '    p = p.taladrar("repisa_1", 4.5, en=(25, 5, 6), eje="-z")\n'
                            '    p = p.taladrar("repisa_2", 4.5, en=(45, 5, 6), eje="-z")\n'
                            '    return p.taladrar("pared_2"')
    [r] = _medir(con_repisa, [_resistencia(20)], tmp_path)
    factor = float(r.detalle.split("factor ")[1].split()[0])
    assert factor == pytest.approx(35 / 7.5, rel=0.08)


def test_la_ventana_de_una_escuadra_en_l_se_encuentra(tmp_path):
    """La placa con la ventana ocupa solo y ∈ [0, 5] de una pieza que llega
    a y = 40: un corte por la mitad de y no la ve."""
    ele = """
def construir(kit):
    placa = kit.caja(60, 5, 40).quitar("ventana", kit.caja(42, 7, 21, en=(9, -1, 10)))
    return placa + kit.caja(60, 40, 5)
"""
    [r] = _medir(ele, [Ventana(tipo="ventana", ancho_mm=40.7, alto_mm=19.7)], tmp_path)
    assert r.estado == "cumple"


def test_acabar_deja_la_pieza_sin_aristas_vivas(tmp_path):
    """`acabar()` es lo que el diseñador tiene que llamar al final: chaflán de
    0.5 en la base (un redondeo abajo sería un voladizo) y redondeo en todo
    lo demás. Con la escalera de dos cajas quedan aristas a media altura que
    «verticales» + «base» no tocaban."""
    escalera = """
def construir(kit):
    p = kit.caja(30, 20, 10) + kit.caja(15, 20, 8, en=(0, 0, 9.5))
    return p.taladrar("a", 4, en=(22, 10, 10)).acabar()
"""
    [r] = _medir(escalera, [AristasVivas(tipo="aristas_vivas", max_fraccion=0.1)], tmp_path)
    assert r.estado == "cumple", r.detalle


def test_la_envolvente_de_una_pieza_redondeada_es_la_real(tmp_path):
    """Fallo real (2026-11-04): con `acabar()` la placa de 80 × 50 del e2e
    medía 80.82 × 50.82 para el juez, que usaba `BoundBox`; en caras curvas
    sale holgada. Era la medida, no la pieza."""
    from orchestrator.banco import extraer_hechos

    step = _step("def construir(kit):\n    return kit.caja(80, 50, 4).redondear(5).acabar()\n", tmp_path)
    h = extraer_hechos(step, _freecadcmd(), None)
    assert sorted(h.bbox_mm) == pytest.approx([4, 50, 80], abs=0.01)


def test_una_arista_concava_no_cuenta_como_viva(tmp_path):
    """Una L de dos cajas: perfil (x, z) de 30 + 5 + 25 + 25 + 5 + 30 = 120 mm,
    dos veces, más 6 aristas de 20 en y: 360 mm. La esquina interior (x = 5,
    z = 5) es cóncava y mide 20: vivas, 340 de 360. Fallo real (2026-11-04):
    la sonda las contaba todas, y redondear la esquina interior de una
    ventana la estrecha."""
    ele = "def construir(kit):\n    return kit.caja(30, 20, 5) + kit.caja(5, 20, 30)\n"
    [r] = _medir(ele, [AristasVivas(tipo="aristas_vivas", max_fraccion=0.1)], tmp_path)
    assert "(340 de 360 mm)" in r.detalle, r.detalle


def test_una_ranura_abierta_por_arriba_deja_pasar_el_servo(tmp_path):
    """El soporte del MG996R del banco (2026-11-04): una placa de pie con una
    ranura en U de 41.1 × 20.1 abierta por arriba. El servo entra por ella y
    atornilla sus orejetas a la placa; la sonda solo buscaba agujeros
    cerrados y lo daba por suspenso. Un hueco abierto por DOS lados (el
    rincón de una L) no sujeta nada y no cuenta."""
    u = """
def construir(kit):
    placa = kit.caja(60, 6, 30, en=(-30, 0, 0)) + kit.caja(60, 40, 6, en=(-30, 0, 0))
    return placa.quitar("ranura", kit.caja(41.1, 42, 30, en=(-20.55, -1, 9.9)))
"""
    ele = "def construir(kit):\n    return kit.caja(60, 5, 60) + kit.caja(60, 60, 5)\n"
    v = Ventana(tipo="ventana", ancho_mm=40.7, alto_mm=19.7)
    [ranura] = _medir(u, [v], tmp_path / "1")
    [rincon] = _medir(ele, [v], tmp_path / "2")
    assert ranura.estado == "cumple", ranura.detalle
    assert rincon.estado == "no_cumple"


def test_acabar_no_estrecha_una_ventana(tmp_path):
    """El soporte del SG90 del banco (2026-11-04): ventana de 23.2 × 12.6 para
    un cuerpo de 22.8 × 12.2, y el redondeo de 1 mm rellenaba sus cuatro
    esquinas interiores (aristas cóncavas): el servo ya no entraba."""
    marco = """
def construir(kit):
    p = kit.caja(60, 40, 10).quitar("ventana", kit.caja(23.2, 12.6, 12, en=(18, 13, -1)))
    return p.acabar()
"""
    [r] = _medir(marco, [Ventana(tipo="ventana", ancho_mm=22.8, alto_mm=12.2)], tmp_path)
    assert r.estado == "cumple", r.detalle


def test_un_booleano_que_falla_en_silencio_no_deja_pasar_nada():
    """El soporte del SG90 del banco (2026-11-04, copiado tal cual): `common`
    y `cut` devuelven vacío para una caja que atraviesa la base maciza, y la
    sonda la daba por pasante. El cuerpo de 22.8 × 12.2 NO cabe: la ventana
    es de 23.2 × 12.6 y el redondeo de sus rincones invade 0.72 mm³
    (medido aparte con `distToShape`, que sí da 0 al chocar)."""
    step = Path(__file__).parent / "sondas_regresiones" / "sg90_booleano_mudo.step"
    [r] = medir_sondas(step, [Ventana(tipo="ventana", ancho_mm=22.8, alto_mm=12.2)],
                       _freecadcmd(), MATERIAL)
    assert r.estado == "no_cumple", r.detalle
