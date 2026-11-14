"""Que una pieza se imprime sin soportes se mide en su forma, no en el slicer.

Decidido por el usuario el 2026-11-13: «el slicer no tiene nada que ver con
el diseño; quiero tener el diseño bien antes de andar tocando PrusaSlicer».
El encargo 16 (banco 1114-0023) se quedó en 4 de 5 por «sin soportes»: la
carcasa los pedía apoyada en la cara que fuera, y como el diseño no lamina,
el diseñador no lo supo en sus quince intentos.

Lo que una impresora no puede hacer en el aire está en su perfil: voladizos
de más de `overhang_max_deg` (45°) desde la vertical y puentes de más de
`bridge_max_mm` (10 mm). Una zona que mira hacia abajo vale si ningún punto
suyo queda a más de medio puente (5 mm) de donde la sostiene material que
viene de abajo: un puente de 10 mm apoyado en sus dos lados, o un alero de 5.

Los esperados son cuentas a mano, y al final lo que dijo PrusaSlicer de dos
carcasas de verdad ese mismo día, que es un oráculo que no es este código.
"""

import math
from pathlib import Path

import pytest
import yaml

from orchestrator.build import build_part
from orchestrator.schemas.programa import Programa
from tests.test_generators import _freecadcmd

pytestmark = pytest.mark.skipif(_freecadcmd() is None, reason="sin freecadcmd")

PERFIL = yaml.safe_load(Path("config/printers/ankermake_m5_plamas.yaml").read_text(encoding="utf-8"))
ANGULO, PUENTE = PERFIL["overhang_max_deg"], PERFIL["bridge_max_mm"]


def _stl(codigo: str, carpeta: Path) -> Path:
    build_part(Programa(part="p", codigo=codigo), None, carpeta, _freecadcmd(), perfil=PERFIL)
    return carpeta / "p.stl"


def _vuelan(codigo, carpeta, postura="-z"):
    from orchestrator.voladizos import voladizos
    return voladizos(_stl(codigo, carpeta), postura, ANGULO, PUENTE)


def test_el_perfil_de_la_impresora_dice_45_grados_y_10_mm():
    assert (ANGULO, PUENTE) == (45, 10)


def test_un_cubo_no_vuela_apoyado_en_ninguna_cara(tmp_path):
    from orchestrator.voladizos import POSTURAS, voladizos
    stl = _stl("def construir(kit):\n    return kit.caja(20, 20, 20)\n", tmp_path)
    assert all(voladizos(stl, p, ANGULO, PUENTE) == [] for p in POSTURAS)


MESA = """
def construir(kit):
    return kit.caja(6, 6, 20, en=(17, 17, 0)) + kit.caja(40, 40, 2, en=(0, 0, 20))
"""


def test_una_mesa_de_una_pata_vuela_de_pie_y_no_boca_abajo(tmp_path):
    """El tablero de 40 × 40 sobre un poste de 6 × 6: por debajo quedan al
    aire 40² − 6² = 1 564 mm², y su esquina está a 17·√2 = 24,0 mm del poste."""
    [zona] = _vuelan(MESA, tmp_path / "de_pie")
    assert zona.area_mm2 == pytest.approx(1564, abs=1)
    assert zona.vuela_mm == pytest.approx(17 * math.sqrt(2), abs=0.2)
    assert zona.plana
    assert zona.caja[0] == pytest.approx([0, 0, 20], abs=0.01)
    assert _vuelan(MESA, tmp_path / "boca_abajo", "+z") == []


def _portal(luz):
    return f"""
def construir(kit):
    pilares = kit.caja(10, 10, 20) + kit.caja(10, 10, 20, en=({10 + luz}, 0, 0))
    return pilares + kit.caja({20 + luz}, 10, 5, en=(0, 0, 20))
"""


def test_un_puente_de_10_mm_vale_y_uno_de_30_no(tmp_path):
    """El dintel entre dos pilares: con 10 mm de luz, su centro queda a 5 de
    cada apoyo, justo lo que la impresora tiende. Con 30, a 15."""
    assert _vuelan(_portal(10), tmp_path / "corto") == []
    [zona] = _vuelan(_portal(30), tmp_path / "largo")
    assert zona.vuela_mm == pytest.approx(15, abs=0.2) and zona.plana
    assert zona.area_mm2 == pytest.approx(300, abs=1)


def test_el_portal_largo_se_imprime_tumbado(tmp_path):
    """Con el perfil del portal en la cama (apoyado en su cara -y) no hay
    nada en el aire: es lo que haría una persona. `como_imprimir` la elige."""
    from orchestrator.voladizos import como_imprimir
    postura, zonas = como_imprimir(_stl(_portal(30), tmp_path), ANGULO, PUENTE)
    assert zonas["-z"] != [] and zonas["-y"] == [] and zonas["+y"] == []
    # Boca abajo, con el dintel en la cama, también: es la primera que vale.
    assert postura == "+z"


def _alero(vuelo):
    return f"""
def construir(kit):
    return kit.caja(10, 20, 30) + kit.caja({vuelo}, 20, 3, en=(10, 0, 27))
"""


def test_un_alero_de_4_mm_vale_y_uno_de_8_no(tmp_path):
    """Lo que sale de una pared sin nada debajo se sostiene solo por un lado:
    hasta medio puente, 5 mm."""
    assert _vuelan(_alero(4), tmp_path / "corto") == []
    [zona] = _vuelan(_alero(8), tmp_path / "largo")
    assert zona.vuela_mm == pytest.approx(8, abs=0.2)


def _pared_inclinada(grados):
    """Una pared que se echa hacia fuera `grados` desde la vertical, de 20 de
    alto: su cara de fuera mira hacia abajo."""
    sale = 20 * math.tan(math.radians(grados))
    return f"""
def construir(kit):
    return kit.extruir([(0, 0), (10, 0), ({10 + sale}, 20), (0, 20)], 15, plano="xz")
"""


def test_una_pared_a_44_grados_vale_y_una_a_50_no(tmp_path):
    """El tejado a 44° que le puso DeepSeek a su carcasa está dentro de lo
    que la impresora hace; a 50° ya no, y la cara entera cuenta: mide
    20/cos 50° = 31,1 mm de largo por 15 de ancho."""
    assert _vuelan(_pared_inclinada(44), tmp_path / "a44") == []
    [zona] = _vuelan(_pared_inclinada(50), tmp_path / "a50")
    assert not zona.plana
    assert zona.area_mm2 == pytest.approx(20 / math.cos(math.radians(50)) * 15, abs=1)


def test_un_chaflan_de_45_grados_no_cuenta(tmp_path):
    """Es la forma de quitar un voladizo, y la que se le recomienda."""
    assert _vuelan(_pared_inclinada(45), tmp_path) == []


def test_un_taladro_horizontal_pequeno_vale_y_uno_de_22_no(tmp_path):
    """El techo de un agujero tumbado es un arco que se cierra solo si es
    pequeño: el de un M3 (Ø3,3) sí; el del resalte de un NEMA 17 (Ø22) deja
    en el aire la parte de arriba: de la clave del arco a donde vuelve a
    estar a 45° hay 2·11·sin 22,5° = 8,4 mm."""
    programa = """
def construir(kit):
    return kit.caja(40, 10, 40).taladrar("paso", %s, en=(20, 0, 20), eje="+y")
"""
    assert _vuelan(programa % 3.3, tmp_path / "m3") == []
    [zona] = _vuelan(programa % 22, tmp_path / "resalte")
    assert zona.vuela_mm == pytest.approx(22 * math.sin(math.radians(22.5)), abs=0.4)


# --- contra lo que dijo PrusaSlicer el 2026-11-13 ---------------------------------------------------

CARCASA = """
def construir(kit):
    abajo = kit.rectangulo(50.6, 47.6, radio=3.5)
    arriba = kit.rectangulo(42, 39, radio=8)
    c = kit.transicion([(abajo, 0), (abajo, 48), (arriba, 53)], en=(0, 24.5, 5), recta=True)
    c = c.vaciar(2.0, abierta="-z")
    c = c.quitar("frente", kit.caja(60, 5, 60, en=(-30, 0, 4)))
    c = c.quitar("ventana_cable", kit.caja(20, 14, 40, en=(-10, 33.4, 48)))
    %s
    return c
"""
BRIDAS = """for x0 in (24.3, -36.0):
        c = c + kit.caja(11.7, 3, 53, en=(x0, 5, 5))"""
OREJAS = """for x0, y in ((24.3, 15), (-36.0, 15), (24.3, 33), (-36.0, 33)):
        c = c + kit.caja(11.7, 10, 3, en=(x0, y, 5))"""


def test_la_carcasa_con_bridas_se_imprime_boca_abajo_como_dijo_prusaslicer(tmp_path):
    """La carcasa del encargo 16 hecha a mano: PrusaSlicer la laminó sin
    pedir soportes «apoyada en su cara +z», con el techo en la cama, y los
    pidió como se dibuja. Las bridas van de arriba abajo y nacen en la cama."""
    from orchestrator.voladizos import como_imprimir
    postura, zonas = como_imprimir(_stl(CARCASA % BRIDAS, tmp_path), ANGULO, PUENTE)
    assert postura == "+z"
    assert zonas["-z"] != []        # como se dibuja, el techo plano de 39 mm


def test_la_carcasa_con_orejas_no_se_imprime_sin_soportes_de_ninguna_forma(tmp_path):
    """La primera que hice a mano: PrusaSlicer pidió soportes «apoyada en la
    cara que sea». Boca abajo las orejas, de 11,7 mm, quedan arriba y en el
    aire; como se dibuja, vuela el techo."""
    from orchestrator.voladizos import como_imprimir, defecto_de_soportes
    stl = _stl(CARCASA % OREJAS, tmp_path)
    postura, zonas = como_imprimir(stl, ANGULO, PUENTE)
    assert postura is None and all(zonas.values())
    [d] = defecto_de_soportes(stl, PERFIL)
    assert d.startswith("sin soportes:") and "45°" in d and "10 mm" in d
    # Dice sobre qué cara le falta menos, y qué zonas vuelan, con su sitio.
    assert "Apoyada en su cara" in d and "x de " in d and "vuela" in d


def test_a_una_pieza_que_se_imprime_bien_no_se_le_dice_nada(tmp_path):
    from orchestrator.voladizos import defecto_de_soportes
    assert defecto_de_soportes(_stl(CARCASA % BRIDAS, tmp_path), PERFIL) == []


# --- en el bucle de la pieza ----------------------------------------------------------------------

def test_solo_se_le_mide_a_la_pieza_que_lo_pide():
    """«Sin soportes» es una condición de la petición, no de todas las
    piezas: una que no lo pide se puede imprimir con ellos. En un backlog la
    petición de cada pieza trae además lo que hace la vecina, que no es
    suyo (`traceability.CONTEXTO`)."""
    from orchestrator.medida import pide_sin_soportes
    from orchestrator.traceability import CONTEXTO
    assert pide_sin_soportes("Carcasa abombada: cubre el motor; se imprime SIN  soportes")
    assert pide_sin_soportes("un gancho que salga sin\nsoportes")
    assert not pide_sin_soportes("un gancho para la mochila")
    de_la_vecina = (f"Carcasa: cubre el motor.\n\n{CONTEXTO}\n\n- Soporte: ficha obra-soporte "
                    "(se imprime sin soportes)")
    assert not pide_sin_soportes(de_la_vecina)


def test_la_medida_entra_en_los_defectos_de_la_pieza(tmp_path):
    """Con el perfil de la impresora, la carcasa de orejas vuelve con su
    «sin soportes:»; sin él (una pieza que no lo pide), no."""
    from types import SimpleNamespace

    from orchestrator.medida import defectos_de_la_pieza
    stl = _stl(CARCASA % OREJAS, tmp_path)
    hecha = SimpleNamespace(rasgos=[], bbox_mm=[72, 43, 53], avisos=[])
    con = defectos_de_la_pieza([], hecha, stl.with_suffix(".step"), _freecadcmd(), {},
                               sin_soportes=PERFIL)
    assert any(d.startswith("sin soportes:") for d in con)
    sin = defectos_de_la_pieza([], hecha, stl.with_suffix(".step"), _freecadcmd(), {})
    assert not any(d.startswith("sin soportes:") for d in sin)


def _con_escalon(alto):
    """Un bloque de 40 × 40 × 10 que apoya solo en una tira de 4 mm: al resto
    de su base se le ha quitado `alto` mm por debajo."""
    return f"""
def construir(kit):
    bloque = kit.caja(40, 40, 10)
    return bloque.quitar("rebaje", kit.caja(36, 40, {alto}, en=(4, 0, 0)))
"""


def test_lo_que_queda_a_menos_de_una_capa_de_la_cama_esta_en_la_cama(tmp_path):
    """Encargo 16 (banco 1114-0023), tercera reanudación: la carcasa apoya en
    su brida, y al dejarle holgura al soporte su base quedó 0,18 mm por
    encima de un borde. La medida dio toda la brida, 1 385 mm², por «en el
    aire a 27 mm de donde se apoya», y al diseñador se le mandó cinco veces
    a arreglar otra postura. Una impresora no distingue 0,18 mm: es menos
    que una capa, y la primera se aplasta contra la cama. Con 1 mm de
    escalón sí hay un techo en el aire, de 36 × 40."""
    assert _vuelan(_con_escalon(0.18), tmp_path / "menos_de_una_capa") == []
    [zona] = _vuelan(_con_escalon(1.0), tmp_path / "un_milimetro")
    assert zona.plana and zona.area_mm2 == pytest.approx(36 * 40, abs=1)


def test_al_disenador_y_al_ingeniero_se_les_dice_al_inicio_como_se_mide():
    """Pedido por el usuario el 2026-11-13: «mejorar las medidas del inicio
    para que no falle». La regla del diseñador decía «nada en voladizo a más
    de `overhang_max_deg`» y nada más: ni que se prueba apoyada en cada cara,
    ni lo de medio puente, ni que lo primero es elegir qué cara va a la cama.
    La carcasa del encargo 16 lo fue descubriendo defecto a defecto."""
    disenador = Path("config/agents/disenador_kit.md").read_text(encoding="utf-8")
    regla = next(l for l in disenador.splitlines() if l.startswith("7. "))
    for dicho in ("qué cara va a la cama", "medio puente", "nace desde la cama",
                  "chaflán de 45°", "menos de una capa"):
        assert dicho in regla, dicho
    ingeniero = Path("config/agents/ingeniero.md").read_text(encoding="utf-8")
    orientacion = next(l for l in ingeniero.splitlines() if l.startswith("3. "))
    assert "qué cara va a la cama" in orientacion and "sin soportes" in orientacion
