"""La carcasa cubre sin tocar: F11.4 (cubre), ADR-022.

Una pieza del plan puede ser la carcasa de lo comprado que monta otra: un
motor con su polea, bajo una tapa. Que quede bien lo decide la persona; lo
que se puede contar es que lo cubre, que no lo toca y que le deja salir el
cable. Sin medirlo, una carcasa que roza el motor o que tapa su clavija pasa
su bucle igual que una buena.

El motor de las pruebas es el NEMA 17 de la biblioteca, de pie sobre una
placa: su cuerpo va de x, y = -21,15 a 21,15 y de z = 5 a 44,5, y su eje
sube hasta 68,5. La carcasa buena deja 1,5 mm a cada lado.
"""

import json
from pathlib import Path

import pytest

from orchestrator.schemas.obra import Obra
from tests.test_generators import _freecadcmd
from tests.test_plan_mecanico import AGUJEROS
from tests.test_revalidar import _lista
from tests.test_sondas import MATERIAL

pytestmark = pytest.mark.skipif(_freecadcmd() is None, reason="sin freecadcmd")

NODOS = [
    {"id": "soporte", "nombre": "Soporte del motor", "que_hace": "lleva el motor de pie",
     "compra": ["nema17"]},
    {"id": "carcasa", "nombre": "Carcasa del motor", "que_hace": "cubre el motor",
     "depende_de": ["soporte"], "cubre": ["nema17"]},
]
UNIONES = [{"tipo": "fija", "id": "u1", "cabeza": "carcasa", "agarra": "soporte",
            "metrica": "M3", "cantidad": 4, "agarre": "rosca"}]

SOPORTE = """
def construir(kit):
    placa = kit.caja(90, 100, 5, en=(-45, -55, 0))
    kit.componente("nema17", en=(0, 0, 44.5), entra_por="+z")
    return placa
"""


def _carcasa(dx=0.0, ventana=True) -> str:
    """Una cáscara de 2 mm que deja 1,5 mm alrededor del motor y de su
    conector (hasta y = -28,15) y sobre su eje (hasta z = 68,5), desplazada
    `dx` en x. Con `ventana`, abierta para la clavija y el cable."""
    return f"""
def construir(kit):
    kit.componente("obra-soporte", en=(0, 0, 0), entra_por="-z")
    seccion = kit.rectangulo(49.3, 56.3, radio=3)
    c = kit.transicion([(seccion, 0), (seccion, 67)], en=({dx}, -3.5, 5))
    c = c.vaciar(2, abierta="-z")
    {'c = c.quitar("ventana_cable", kit.caja(20, 20, 16, en=(-10, -45, 5)))' if ventana else ''}
    return c
"""


@pytest.fixture
def backlog(tmp_path, monkeypatch):
    from orchestrator import obra as O
    (tmp_path / "request.md").write_text("un motor con su carcasa", encoding="utf-8")
    O.guardar(tmp_path, Obra(titulo="Motor con carcasa", nodos=NODOS, uniones=UNIONES),
              por="prueba")
    O.aprobar(tmp_path, por="prueba")
    monkeypatch.setenv("INTELLIPRINT_FICHAS", str(O.carpeta_de_fichas(tmp_path)))
    monkeypatch.delenv("INTELLIPRINT_AJENOS", raising=False)
    monkeypatch.delenv("INTELLIPRINT_UNIONES", raising=False)
    _lista(tmp_path, "soporte", SOPORTE)
    return tmp_path


def _medida(carpeta: Path, codigo: str) -> list[str]:
    from orchestrator.build import build_part
    from orchestrator.medida import defectos_de_carcasa
    from orchestrator.schemas.programa import Programa
    from tests.test_sondas import PERFIL
    parte = carpeta / "nodos" / "carcasa" / "parts" / "carcasa"
    r = build_part(Programa(part="carcasa", codigo=codigo), None, parte, _freecadcmd(),
                   perfil=PERFIL)
    return defectos_de_carcasa(carpeta, "carcasa", r, parte / "carcasa.step", _freecadcmd(),
                               MATERIAL)


def test_una_carcasa_con_holgura_y_ventana_para_el_cable_pasa(backlog):
    assert _medida(backlog, _carcasa()) == []


def test_con_la_pared_1_mm_dentro_del_motor_lo_dice_con_su_cifra(backlog):
    """Criterio de F11.4 (cubre). Desplazada 2,5 mm, la pared de -x (2 mm de
    grueso) se mete 1 mm en el cuerpo del motor: 1 × 42,3 × 39,5 = 1 671 mm³."""
    [d] = _medida(backlog, _carcasa(dx=2.5))
    assert "nema17: cuerpo" in d and "choca" in d and "167" in d


def test_si_queda_a_medio_milimetro_pide_el_milimetro(backlog):
    """Desplazada 1 mm: de los 1,5 de holgura quedan 0,5 por el lado de -x.
    No se tocan, pero una pieza impresa no garantiza medio milímetro."""
    [d] = _medida(backlog, _carcasa(dx=1.0))
    assert "0.5 mm" in d and "al menos 1 mm" in d and "nema17" in d


def test_sin_ventana_la_carcasa_tapa_la_clavija_y_el_cable(backlog):
    """La ficha del motor pide libre la clavija y su cable, que salen 15 mm
    por -y. Una cáscara cerrada pasa por en medio."""
    [d] = _medida(backlog, _carcasa(ventana=False))
    assert "clavija y cable" in d and "tapa" in d


def test_una_pared_al_lado_del_motor_no_es_su_carcasa(backlog):
    """Una placa de 4 mm a 9 mm del motor ni lo toca ni lo cubre: el motor
    queda entero fuera de ella."""
    [d] = _medida(backlog, """
def construir(kit):
    kit.componente("obra-soporte", en=(0, 0, 0), entra_por="-z")
    return kit.caja(4, 60, 60, en=(30, -30, 5))
""")
    assert "no cubre" in d and "nema17" in d


def test_una_pieza_que_no_cubre_nada_no_se_mide(backlog):
    from orchestrator.medida import defectos_de_carcasa
    assert defectos_de_carcasa(backlog, "soporte", None, None, _freecadcmd(), MATERIAL) == []


# --- el plan y lo que se le dice al diseñador -------------------------------------------------

def _errores(nodos=NODOS, uniones=UNIONES) -> list[str]:
    from orchestrator.plan import validar_plan
    return validar_plan(Obra(titulo="t", nodos=nodos, uniones=uniones), AGUJEROS)[0]


def test_el_plan_de_una_carcasa_vale_si_cubre_lo_de_una_pieza_a_la_que_se_atornilla():
    assert _errores() == []


def test_no_se_cubre_lo_que_no_lleva_ninguna_pieza_a_la_que_se_une():
    otros = [NODOS[0], {**NODOS[1], "cubre": ["sg90"]}]
    [e] = _errores(otros)
    assert "sg90" in e and "«Carcasa del motor»" in e and "compra" in e


def test_una_carcasa_va_atornillada_a_la_pieza_que_cubre():
    [e] = _errores(uniones=[])
    assert "«Carcasa del motor»" in e and "«Soporte del motor»" in e and "fija" in e


def test_al_disenador_se_le_dice_que_cubre_y_con_cuanta_holgura(backlog):
    from orchestrator import obra as O
    texto = O.peticion_del_nodo(backlog, "carcasa")
    assert "carcasa" in texto and "nema17" in texto and "1 mm" in texto
    assert "obra-soporte" in texto
    # No es una cota suya: la holgura la pone el sistema.
    from orchestrator.traceability import requested_dimensions
    assert requested_dimensions(texto) == []


def test_al_desglosador_se_le_dice_como_se_planea_una_carcasa():
    """Sin esto el plan no puede pedir la medida: `cubre` solo existe si quien
    desglosa sabe que existe, y qué tiene que acompañarlo."""
    texto = Path("config/agents/desglosador.md").read_text(encoding="utf-8")
    assert "`cubre: [" in texto and "unión `fija`" in texto and "carcasa" in texto
