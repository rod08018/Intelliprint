"""El programa del diseñador, validado antes de ejecutarse (F5.18 (kit)).

Con el catálogo cerrado de generadores (ADR-002) no se podía dibujar una
escuadra con nervio, un hexágono ni un chaflán: la escuadra de repisa salió
maciza, 121 g (2026-11-04). El diseñador pasa a escribir una función
`construir(kit)` en Python. La seguridad deja de venir de que el código no
sale de un modelo y pasa a venir de aquí: solo se ejecuta lo que esta lista
blanca deja pasar, y nunca se ve nada fuera del kit.
"""

import pytest

from mech_toolkit.kit.sandbox import ProgramaInvalido, validar

BUENO = """
def construir(kit):
    sep = 60
    ala = kit.caja(28, 14, 120)
    pieza = ala + kit.caja(200, 28, 14)
    for i, z in enumerate([30, 30 + sep]):
        pieza = pieza.taladrar(f"pared_{i + 1}", 4.5, en=(0, 7, z), eje="y")
    return pieza.redondear(2, aristas="verticales")
"""


def test_un_programa_que_solo_usa_el_kit_pasa():
    validar(BUENO)


@pytest.mark.parametrize("trampa, que", [
    ("import os\ndef construir(kit):\n    return kit.caja(1, 1, 1)", "import"),
    ("def construir(kit):\n    from os import system\n    return kit", "import"),
    ("def construir(kit):\n    open('/etc/passwd')\n    return kit", "open"),
    ("def construir(kit):\n    eval('1')\n    return kit", "eval"),
    ("def construir(kit):\n    return kit.__class__", "__class__"),
    ("def construir(kit):\n    return ().__class__.__bases__", "no es del kit"),
    ("def construir(kit):\n    g = (x for x in [1])\n    return g.gi_frame.f_globals", "no es del kit"),
    ("def construir(kit):\n    return kit.caja(1, 1, 1)._forma.exportStep('x')", "no es del kit"),
    ("def construir(kit):\n    return kit.caja(1, 1, 1).exportStep('x')", "exportStep"),
    ("class X:\n    pass\ndef construir(kit):\n    return kit", "class"),
    ("def construir(kit):\n    global x\n    return kit", "global"),
    ("def construir(kit):\n    try:\n        pass\n    except Exception:\n        pass\n    return kit", "try"),
    ("for i in range(3):\n    pass\ndef construir(kit):\n    return kit", "nivel superior"),
])
def test_lo_que_no_es_el_kit_no_pasa(trampa, que):
    with pytest.raises(ProgramaInvalido, match=que):
        validar(trampa)


def test_sin_construir_no_hay_pieza():
    with pytest.raises(ProgramaInvalido, match="construir"):
        validar("def otra(kit):\n    return kit.caja(1, 1, 1)")


def test_el_error_dice_en_que_linea():
    """El motivo vuelve al modelo: sin la línea, no sabe qué corregir."""
    with pytest.raises(ProgramaInvalido, match="línea 3"):
        validar("def construir(kit):\n    a = 1\n    return open('x')")


def test_un_programa_que_no_es_python_dice_por_que():
    with pytest.raises(ProgramaInvalido, match="sintaxis"):
        validar("def construir(kit) return 1")


# --- la limpieza de caras no tumba una operación -----------------------------------------
# Encargo 16, banco 1114-0631: con la escuadra de esa corrida, `removeSplitter`
# (unir las caras coplanarias que deja una booleana) lanzaba «Bnd_Box is void»
# después de una resta válida, y otra vez al hacer crecer su forma para un
# hueco. Tres intentos de la carcasa perdidos por adecentar.

class _FormaQueNoSeDejaLimpiar:
    def removeSplitter(self):
        raise RuntimeError("Bnd_Box is void")


class _FormaLimpia:
    def isNull(self):
        return False

    def isValid(self):
        return True


class _FormaQueSeLimpia:
    def removeSplitter(self):
        return _FormaLimpia()


def test_si_occ_no_puede_unir_las_caras_la_forma_vale_como_esta():
    from mech_toolkit.componentes import limpia
    rota = _FormaQueNoSeDejaLimpiar()
    assert limpia(rota) is rota
    assert isinstance(limpia(_FormaQueSeLimpia()), _FormaLimpia)


def test_ninguna_booleana_del_kit_limpia_sin_red():
    """En el kit, en lo que hace crecer una forma y en los tramos, las caras
    se unen con `limpia`, no con `removeSplitter` a pelo."""
    from pathlib import Path
    raiz = Path("mcp/mech-toolkit/mech_toolkit")
    for ruta in (raiz / "kit" / "__init__.py", raiz / "componentes.py", raiz / "tramos.py"):
        texto = ruta.read_text(encoding="utf-8")
        assert texto.count(".removeSplitter()") == (1 if ruta.name == "componentes.py" else 0), ruta
