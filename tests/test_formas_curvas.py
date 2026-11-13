"""Formas curvas del kit: F11.1 (curvas) y F11.2 (cáscara), ADR-022.

El kit solo dibujaba cajas, cilindros y polígonos extruidos: el brazo mediano
de la Fase 10 es una pila de ellos. Una carcasa, y más adelante un ala, son
secciones unidas por una superficie y una pared fina. El modelo da las
secciones; la superficie la genera el código.

Cada esperado es una cuenta a mano, escrita en su test.
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


# --- secciones y transición ---------------------------------------------------------------------

def test_la_transicion_entre_dos_circulos_es_un_tronco_de_cono(tmp_path):
    """π·h·(R² + R·r + r²)/3 con R = 20, r = 10 y h = 30: 21 991,15 mm³."""
    r = _construir("""
def construir(kit):
    return kit.transicion([(kit.elipse(40, 40), 0), (kit.elipse(20, 20), 30)])
""", tmp_path)
    assert r.volume_mm3 == pytest.approx(math.pi * 30 * (400 + 200 + 100) / 3, rel=1e-4)
    assert r.bbox_mm == pytest.approx([40, 40, 30], abs=0.01)
    assert r.solids == 1


def test_entre_dos_rectangulos_iguales_sale_la_caja_y_crece_por_el_eje_que_se_diga(tmp_path):
    """30 × 20 × 15 = 9 000. A lo largo de x, la sección va en el plano yz,
    como en `extruir`: lo que mide 30 queda en y, y lo que mide 20, en z."""
    r = _construir("""
def construir(kit):
    s = kit.rectangulo(30, 20)
    return kit.transicion([(s, 0), (s, 15)], eje="x", en=(5, 0, 0))
""", tmp_path)
    assert r.volume_mm3 == pytest.approx(9000, abs=0.01)
    assert r.bbox_mm == pytest.approx([15, 30, 20], abs=0.01)


def test_un_rectangulo_redondeado_pierde_sus_cuatro_esquinas(tmp_path):
    """Cada esquina de radio 5 quita (1 − π/4)·5²: el área es
    30·20 − (4 − π)·25 = 578,54, por 10 de alto."""
    r = _construir("""
def construir(kit):
    s = kit.rectangulo(30, 20, radio=5)
    return kit.transicion([(s, 0), (s, 10)])
""", tmp_path)
    assert r.volume_mm3 == pytest.approx((600 - (4 - math.pi) * 25) * 10, rel=1e-4)


def test_una_elipse_tiene_el_area_de_sus_semiejes(tmp_path):
    """π·a·b con a = 15 y b = 5, por 8 de alto."""
    r = _construir("""
def construir(kit):
    s = kit.elipse(30, 10)
    return kit.transicion([(s, 0), (s, 8)])
""", tmp_path)
    assert r.volume_mm3 == pytest.approx(math.pi * 15 * 5 * 8, rel=1e-4)
    assert r.bbox_mm == pytest.approx([30, 10, 8], abs=0.01)


def test_una_seccion_curva_pasa_por_sus_puntos(tmp_path):
    """Cuatro puntos a 10 mm del centro, en los ejes. La curva cerrada que
    pasa por ellos llega justo a ±10 en cada eje (son sus extremos, por
    simetría), y encierra más que el rombo de esos puntos (200 mm²) y menos
    que el cuadrado que los contiene (400)."""
    r = _construir("""
def construir(kit):
    s = kit.seccion([(10, 0), (0, 10), (-10, 0), (0, -10)], curva=True)
    return kit.transicion([(s, 0), (s, 5)])
""", tmp_path)
    assert r.bbox_mm == pytest.approx([20, 20, 5], abs=0.02)
    assert 200 * 5 < r.volume_mm3 < 400 * 5


def test_una_seccion_de_lados_rectos_es_su_poligono(tmp_path):
    """Un triángulo de base 30 y altura 20: 300 mm², por 6."""
    r = _construir("""
def construir(kit):
    s = kit.seccion([(0, 0), (30, 0), (0, 20)])
    return kit.transicion([(s, 0), (s, 6)])
""", tmp_path)
    assert r.volume_mm3 == pytest.approx(1800, abs=0.01)


def test_con_tres_secciones_la_superficie_es_lisa_y_pasa_por_la_del_medio(tmp_path):
    """Una barriga: Ø20, Ø40 y Ø20 a 0, 20 y 40 de alto. Lisa abulta más que
    dos troncos de cono (2·π·20·(100 + 200 + 400)/3 = 29 321,5) y cabe en el
    cilindro de Ø40 (50 265,5). Con `recta` son justo los dos troncos."""
    programa = """
def construir(kit):
    fino, gordo = kit.elipse(20, 20), kit.elipse(40, 40)
    return kit.transicion([(fino, 0), (gordo, 20), (fino, 40)]%s)
"""
    lisa = _construir(programa % "", tmp_path / "lisa")
    assert lisa.bbox_mm == pytest.approx([40, 40, 40], abs=0.05)
    dos_troncos = 2 * math.pi * 20 * (100 + 200 + 400) / 3
    assert dos_troncos * 1.02 < lisa.volume_mm3 < math.pi * 400 * 40
    recta = _construir(programa % ", recta=True", tmp_path / "recta")
    assert recta.volume_mm3 == pytest.approx(dos_troncos, rel=1e-4)


def test_una_transicion_necesita_dos_secciones_y_alturas_que_suban(tmp_path):
    with pytest.raises(ConstruccionFallida, match="al menos dos"):
        _construir("""
def construir(kit):
    return kit.transicion([(kit.elipse(10, 10), 0)])
""", tmp_path / "una")
    with pytest.raises(ConstruccionFallida, match="de menor a mayor"):
        _construir("""
def construir(kit):
    s = kit.elipse(10, 10)
    return kit.transicion([(s, 10), (s, 0)])
""", tmp_path / "bajan")


# --- barrido ------------------------------------------------------------------------------------

def test_barrer_por_un_camino_recto_es_area_por_largo(tmp_path):
    """10 × 6 a lo largo de 50 mm en x: 3 000 mm³."""
    r = _construir("""
def construir(kit):
    return kit.barrer(kit.rectangulo(10, 6), [(0, 0, 0), (50, 0, 0)])
""", tmp_path)
    assert r.volume_mm3 == pytest.approx(3000, abs=0.01)
    assert sorted(r.bbox_mm) == pytest.approx([6, 10, 50], abs=0.01)


def test_barrer_por_un_arco_cumple_pappus(tmp_path):
    """Un círculo de Ø8 a lo largo de un cuarto de vuelta de radio 50: el
    área por lo que recorre su centro, π·4² · (π·50/2) = 3 947,8 mm³. El
    camino es una curva por nueve puntos del arco, no el arco exacto: se le
    da un 0,5 %."""
    r = _construir("""
def construir(kit):
    camino = [(50 * cos(radians(a)), 0, 50 * sin(radians(a)))
              for a in (0, 11.25, 22.5, 33.75, 45, 56.25, 67.5, 78.75, 90)]
    return kit.barrer(kit.elipse(8, 8), camino, curva=True)
""", tmp_path)
    assert r.volume_mm3 == pytest.approx(math.pi * 16 * math.pi * 25, rel=5e-3)
    assert r.solids == 1


def test_un_barrido_que_dobla_mas_cerrado_que_su_seccion_no_vale(tmp_path):
    """Una horquilla de 12 mm de ancho recorrida por un círculo de Ø24: no
    cabe en su propia curva y la superficie se pisa. Un barrido sano mide
    sección por largo del camino (Pappus); el que no, se rechaza diciendo
    por qué. El mismo camino con un cable de Ø3 sí vale."""
    programa = """
def construir(kit):
    return kit.barrer(kit.elipse(%s, %s), [(0, 0, 0), (20, 0, 0), (20, 0, 12), (0, 0, 12)],
                      curva=True)
"""
    with pytest.raises(ConstruccionFallida, match="dobla más cerrado"):
        _construir(programa % (24, 24), tmp_path / "gordo")
    fino = _construir(programa % (3, 3), tmp_path / "fino")
    assert fino.solids == 1 and 250 < fino.volume_mm3 < 450


def test_el_volumen_de_una_cascara_con_un_cable_barrido_es_el_de_los_dos(tmp_path):
    """La prueba a mano del 2026-11-13. La cáscara pesa lo suyo y el cable lo
    suyo (Ø9 por su largo); unidos, la suma menos lo que el cable pisa de la
    pared, que no llega a 300 mm³. FreeCAD daba la unión por válida y decía
    que medía 19 mm³ más que la cáscara sola: su `Volume` falla ahí, y el
    informe lo contrasta con la malla."""
    cascara = """
def construir(kit):
    base, medio = kit.rectangulo(70, 56, radio=10), kit.rectangulo(62, 50, radio=14)
    c = kit.transicion([(base, 0), (medio, 28), (kit.elipse(44, 34), 46)])
    c = c.vaciar(2, abierta="-z")
"""
    cable = """    cable = kit.barrer(kit.elipse(9, 9), [(30, 0, 12), (40, 0, 12), (48, 0, 6), (56, 0, 6)],
                       curva=True)
"""
    sola = _construir(cascara + "    return c\n", tmp_path / "sola")
    suelto = _construir(cascara + cable + "    return cable\n", tmp_path / "cable")
    juntos = _construir(cascara + cable + "    return c + cable\n", tmp_path / "juntos")
    suma = sola.volume_mm3 + suelto.volume_mm3
    assert suma - 300 < juntos.volume_mm3 < suma
    assert juntos.solids == 1


# --- cáscara ------------------------------------------------------------------------------------

def test_vaciar_una_caja_deja_la_pared_que_se_pide(tmp_path):
    """Un cubo de 40 vaciado a 2 mm y abierto por arriba: lo de fuera menos
    lo de dentro, 40³ − 36·36·38 = 14 752 mm³. Por fuera mide lo mismo."""
    r = _construir("""
def construir(kit):
    return kit.caja(40, 40, 40).vaciar(2, abierta="+z")
""", tmp_path)
    assert r.volume_mm3 == pytest.approx(64000 - 36 * 36 * 38, abs=0.5)
    assert r.bbox_mm == pytest.approx([40, 40, 40], abs=0.01)


def test_la_pared_de_una_cascara_la_mide_la_sonda_de_siempre(tmp_path):
    """La pared mínima que ya se mide en el bucle de cada pieza: con 2 mm
    pedidos, pasa si se exigen 1,9 y no pasa si se exigen 2,5."""
    from orchestrator.banco import ParedMinima, medir_sondas
    _construir("""
def construir(kit):
    return kit.caja(40, 40, 40).vaciar(2, abierta="+z")
""", tmp_path)
    holgada, justa = medir_sondas(tmp_path / "p.step", [
        ParedMinima(tipo="pared_minima", min_mm=1.9),
        ParedMinima(tipo="pared_minima", min_mm=2.5)], _freecadcmd(), {})
    assert holgada.estado == "cumple", holgada.detalle
    assert justa.estado == "no_cumple" and "2.0" in justa.detalle


def test_una_tapa_abombada_es_una_transicion_vaciada(tmp_path):
    """Lo que la fase quiere poder dibujar: una carcasa que pasa de un
    rectángulo redondeado a otro más pequeño, hueca y abierta por debajo.
    Pesa menos que maciza y más que nada, mide por fuera lo mismo, y su
    pared es la pedida."""
    from orchestrator.banco import ParedMinima, medir_sondas
    programa = """
def construir(kit):
    abajo, arriba = kit.rectangulo(60, 40, radio=8), kit.rectangulo(40, 24, radio=8)
    tapa = kit.transicion([(abajo, 0), (arriba, 25)])
    return tapa%s
"""
    maciza = _construir(programa % "", tmp_path / "maciza")
    hueca = _construir(programa % '.vaciar(2, abierta="-z")', tmp_path / "hueca")
    assert hueca.bbox_mm == pytest.approx(maciza.bbox_mm, abs=0.01)
    assert 0.15 * maciza.volume_mm3 < hueca.volume_mm3 < 0.5 * maciza.volume_mm3
    assert hueca.solids == 1
    [pared] = medir_sondas(tmp_path / "hueca" / "p.step",
                           [ParedMinima(tipo="pared_minima", min_mm=1.8)], _freecadcmd(), {})
    assert pared.estado == "cumple", pared.detalle


def test_una_carcasa_lisa_de_tres_secciones_tambien_se_vacia(tmp_path):
    """La prueba a mano de F11.2 (cáscara), el 2026-11-13: un carenado que pasa de un
    rectángulo redondeado a otro y acaba en un óvalo. El vaciado de FreeCAD
    («thickness») no puede con esa superficie lisa y devolvía un error, justo
    en la forma para la que se hizo la fase. Se vacía entonces por secciones:
    la misma transición, más pequeña, restada por dentro. La pared no baja
    de la pedida ni donde la carcasa se inclina."""
    from orchestrator.banco import ParedMinima, medir_sondas
    programa = """
def construir(kit):
    base, medio = kit.rectangulo(70, 56, radio=10), kit.rectangulo(62, 50, radio=14)
    carcasa = kit.transicion([(base, 0), (medio, 28), (kit.elipse(44, 34), 46)])
    return carcasa%s
"""
    maciza = _construir(programa % "", tmp_path / "maciza")
    hueca = _construir(programa % '.vaciar(2, abierta="-z")', tmp_path / "hueca")
    assert hueca.bbox_mm == pytest.approx(maciza.bbox_mm, abs=0.01)
    assert 0.1 * maciza.volume_mm3 < hueca.volume_mm3 < 0.4 * maciza.volume_mm3
    assert hueca.solids == 1
    [pared] = medir_sondas(tmp_path / "hueca" / "p.step",
                           [ParedMinima(tipo="pared_minima", min_mm=1.9)], _freecadcmd(), {})
    assert pared.estado == "cumple", pared.detalle


def test_el_acabado_de_siempre_funciona_sobre_una_carcasa_curva(tmp_path):
    """El diseñador termina todas las piezas con `acabar()`. Sobre la carcasa
    de la prueba a mano (2026-11-13) daba «ninguna arista «base»»: la base se
    buscaba con la caja holgada de FreeCAD, que en una superficie curva
    recortada llega más abajo que la pieza. Tiene que construirse, y seguir
    midiendo por fuera lo mismo."""
    programa = """
def construir(kit):
    base, medio = kit.rectangulo(70, 56, radio=10), kit.rectangulo(62, 50, radio=14)
    carcasa = kit.transicion([(base, 0), (medio, 28), (kit.elipse(44, 34), 46)])
    carcasa = carcasa.vaciar(2, abierta="-z")
    return carcasa%s
"""
    sin = _construir(programa % "", tmp_path / "sin")
    con = _construir(programa % ".acabar()", tmp_path / "con")
    assert con.solids == 1
    assert con.bbox_mm == pytest.approx(sin.bbox_mm, abs=0.05)
    # El chaflán de la base quita algo, y no más de un 5 %.
    assert 0.95 * sin.volume_mm3 < con.volume_mm3 < sin.volume_mm3


def test_una_transicion_solo_se_abre_por_una_de_sus_dos_puntas(tmp_path):
    with pytest.raises(ConstruccionFallida, match="cara plana"):
        _construir("""
def construir(kit):
    carcasa = kit.transicion([(kit.elipse(40, 30), 0), (kit.elipse(60, 40), 20),
                              (kit.elipse(30, 20), 40)])
    return carcasa.vaciar(2, abierta="+x")
""", tmp_path)


def test_vaciar_dice_que_cara_no_encuentra(tmp_path):
    with pytest.raises(ConstruccionFallida, match="cara plana"):
        _construir("""
def construir(kit):
    return kit.esfera(30).vaciar(2, abierta="+z")
""", tmp_path)
