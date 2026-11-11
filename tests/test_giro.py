"""El sitio de cada giro se mide mientras se diseña cada pieza
(F9.1 (barrido), F9.5 (parcial)).

El pan-tilt del banco 1110-0313 pasó cuatro de sus cinco comprobaciones y
falló «se mueve sin chocar». Sus tres piezas estaban dadas por buenas cuando
se movió entero por primera vez, y la corrección se le pidió a la
plataforma, que bajó de 68.4 a 37.7 mm de radio y no podía bajar más: el
soporte, que monta el servo de inclinación, solo había dejado 12.7 mm.

Aquí están esas mismas piezas, con sus rasgos y envolventes tal como
quedaron en la corrida. Las cifras esperadas son cuentas a mano:

- del eje de inclinación al SG90 de la base: 12.2 + 33.6 − 33.1 = 12.7 mm
  (ver `tests/test_conjunto.py`);
- la plataforma coloca el soporte en (−13.55, 5.6, 2.8), así que el eje, que
  en el soporte sale en (13.55, −5.6, 12.2) hacia +x, pasa en su marco por
  (0, 0, 15). Su caja va de y = −28 a 34.6 y de z = 0 a 30: la esquina más
  lejana queda a √(34.6² + 15²) = 37.7 mm del eje. Es la cifra que dio la
  verificación de la corrida.
"""

import json

import pytest

from orchestrator.banco import ZonaLibre, medir_sondas
from orchestrator.build import build_part
from orchestrator.conjunto import articulaciones, correcciones, giros_del_plan, leer_piezas
from orchestrator.medida import defectos_de_giro, sondas_de_giro
from orchestrator.schemas.obra import Obra
from orchestrator.schemas.programa import Programa
from tests.test_conjunto import _brazo_y_poste, _obra, _sg90, _sobre
from tests.test_generators import _freecadcmd
from tests.test_sondas import MATERIAL, PERFIL

BASE = ([], [_sg90((13.6, 8.8, 6.0))], ([0, 0, 0], [50, 30, 21.6]))
SOPORTE = (["base"], [_sobre("base", (-19.4, -15.0, -33.6)),
                      _sg90((-13.55, -11.4, 6.0), [("x", 90), ("z", 90)])],
           ([-18, -18, 0], [16, 18, 20]))
PLATAFORMA = (["soporte"], [_sobre("soporte", (-13.55, 5.6, 2.8))],
              ([2.5, -28, 0], [100, 34.6, 30]))


def _plan(radio_inclinar=25.0, radio_girar=30.0) -> dict:
    return {"titulo": "Pan-tilt", "nodos": [
        {"id": "base", "nombre": "Base", "que_hace": "x", "compra": ["sg90"]},
        {"id": "soporte", "nombre": "Soporte", "que_hace": "x", "compra": ["sg90"],
         "depende_de": ["base"]},
        {"id": "plataforma", "nombre": "Plataforma", "que_hace": "x",
         "depende_de": ["soporte"]},
        {"id": "conjunto", "nombre": "El conjunto", "tipo": "conjunto", "que_hace": "x",
         "depende_de": ["base", "soporte", "plataforma"]}],
        "uniones": [
            {"tipo": "gira", "id": "u2", "gira": "soporte", "sobre": "base",
             "componente": "sg90", "recorrido_grados": 180, "radio_libre_mm": radio_girar},
            {"tipo": "gira", "id": "u3", "gira": "plataforma", "sobre": "soporte",
             "componente": "sg90", "recorrido_grados": 180, "radio_libre_mm": radio_inclinar}]}


def _pan_tilt(tmp_path, plataforma=None, **plan):
    """Base y soporte construidos; la plataforma, solo si se pasa."""
    piezas = {"base": BASE, "soporte": SOPORTE}
    if plataforma is not None:
        piezas["plataforma"] = plataforma
    _obra(tmp_path, piezas)
    (tmp_path / "obra.json").write_text(json.dumps(_plan(**plan)), encoding="utf-8")
    return tmp_path


# --- la pieza que monta el actuador deja el sitio (F9.1 (barrido)) ---------------------------

def test_al_soporte_se_le_dice_que_no_deja_sitio_para_inclinar(tmp_path):
    """Con 25 mm pedidos y 12.7 medidos, el defecto es del soporte, en su
    propio bucle, con las dos cifras y lo que estorba."""
    [defecto] = defectos_de_giro(_pan_tilt(tmp_path), "soporte")
    assert "12.7 mm" in defecto and "25 mm" in defecto
    assert "«Plataforma»" in defecto and "lo comprado que monta «Base»" in defecto
    assert "12.3 mm" in defecto, "y cuánto le falta: 25 − 12.7"


def test_si_el_soporte_deja_el_sitio_que_pide_el_plan_no_hay_defecto(tmp_path):
    assert defectos_de_giro(_pan_tilt(tmp_path, radio_inclinar=12.0), "soporte") == []


def test_a_la_base_no_le_estorba_nada_porque_no_tiene_nada_debajo(tmp_path):
    assert defectos_de_giro(_pan_tilt(tmp_path), "base") == []


def test_el_cilindro_libre_de_cada_actuador_se_sondea_en_la_pieza_que_lo_monta(tmp_path):
    """Lo de debajo se mide con cajas; el cuerpo de la propia pieza, con su
    forma real en FreeCAD: el actuador está dentro de su caja."""
    carpeta = _pan_tilt(tmp_path)
    [del_soporte] = sondas_de_giro(carpeta, "soporte")
    assert del_soporte.punto == pytest.approx([13.55, -5.6, 12.2])
    assert del_soporte.eje == pytest.approx([1, 0, 0]) and del_soporte.radio_mm == 25
    [de_la_base] = sondas_de_giro(carpeta, "base")
    assert de_la_base.punto == pytest.approx([19.4, 15.0, 33.1])
    assert de_la_base.eje == pytest.approx([0, 0, 1]) and de_la_base.radio_mm == 30
    assert sondas_de_giro(carpeta, "plataforma") == []


@pytest.mark.skipif(_freecadcmd() is None, reason="sin freecadcmd")
@pytest.mark.parametrize("y, dentro", [(-2, True), (20, False)])
def test_lo_que_la_pieza_mete_en_el_cilindro_libre_sale_en_mm3(tmp_path, y, dentro):
    """Un taco de 4 × 4 × 4 a 10 mm de la cara de salida. Centrado en el eje
    cabe entero en un cilindro de radio 10: invade 4·4·4 = 64 mm³. A 20 mm
    del eje queda fuera."""
    codigo = f"def construir(kit):\n    return kit.caja(4, 4, 4, en=(10, {y}, -2))\n"
    build_part(Programa(part="p", codigo=codigo), None, tmp_path, _freecadcmd(), perfil=PERFIL)
    sonda = ZonaLibre(tipo="zona_libre", nombre="eje", punto=[0, 0, 0], eje=[1, 0, 0],
                      radio_mm=10)
    [r] = medir_sondas(tmp_path / "p.step", [sonda], _freecadcmd(), MATERIAL)
    assert r.estado == ("no_cumple" if dentro else "cumple"), r.detalle
    if dentro:
        assert "64 mm³" in r.detalle and "10 mm" in r.detalle


# --- la pieza que gira no pasa de su sitio ---------------------------------------------------

def test_a_la_plataforma_se_le_dice_que_se_sale_del_sitio_que_tiene(tmp_path):
    [defecto] = defectos_de_giro(_pan_tilt(tmp_path, PLATAFORMA), "plataforma")
    assert "37.7 mm" in defecto and "25 mm" in defecto and "«Soporte»" in defecto


def test_la_plataforma_que_cabe_en_su_sitio_no_tiene_defecto(tmp_path):
    carpeta = _pan_tilt(tmp_path, PLATAFORMA, radio_inclinar=40.0)
    assert defectos_de_giro(carpeta, "plataforma") == []


def test_lo_que_gira_va_por_delante_de_la_cara_de_salida(tmp_path):
    """El sitio reservado empieza en la cara por donde sale el eje. Una
    plataforma que vuelve 10 mm hacia atrás se mete donde está el servo y la
    pieza que lo sujeta. Radio: √(28² + 15²) = 31.8, dentro de 40."""
    atras = (PLATAFORMA[0], PLATAFORMA[1], ([-10, -28, 0], [60, 20, 30]))
    [defecto] = defectos_de_giro(_pan_tilt(tmp_path, atras, radio_inclinar=40.0), "plataforma")
    assert "10.0 mm por detrás" in defecto


def test_lo_que_gira_tiene_que_llegar_al_eje(tmp_path):
    """Colocada 50 mm más allá, su caja empieza a 2.5 + 63.55 − 13.55 = 52.5
    mm de la cara de salida: no se acopla a nada."""
    lejos = (["soporte"], [_sobre("soporte", (-63.55, 5.6, 2.8))], PLATAFORMA[2])
    [defecto] = defectos_de_giro(_pan_tilt(tmp_path, lejos, radio_inclinar=200.0), "plataforma")
    assert "52.5 mm" in defecto and "no llega" in defecto


def test_lo_que_gira_coloca_la_pieza_sobre_la_que_gira(tmp_path):
    suelta = (["soporte"], [], PLATAFORMA[2])
    [defecto] = defectos_de_giro(_pan_tilt(tmp_path, suelta), "plataforma")
    assert "obra-soporte" in defecto


def test_un_backlog_sin_uniones_no_mide_nada_de_esto(tmp_path):
    """Los de antes del 2026-11-10 siguen como estaban."""
    carpeta = _obra(tmp_path, {"base": BASE, "soporte": SOPORTE})
    assert defectos_de_giro(carpeta, "soporte") == []
    assert sondas_de_giro(carpeta, "soporte") == []


# --- solo gira lo que el plan dice (F9.5 (parcial)) -------------------------------------------

def test_solo_gira_lo_que_el_plan_dice_que_gira(tmp_path):
    """Una tapa que el plan atornilla a la base pero que queda a 0.5 mm del
    eje de su servo. Sin plan gira con él, por cercanía; con plan, solo si
    el plan lo dice, y sobre el componente que dice."""
    carpeta = _obra(tmp_path, {
        "base": ([], [_sg90((23.6, 6, 0))], ([0, 0, 0], [70, 34, 18.5])),
        "tapa": (["base"], [_sobre("base", (-29.4, -12.2, -27.6))],
                 ([-28, -17, 0], [28, 17, 31]))})
    piezas = leer_piezas(carpeta, "conjunto")
    assert len(articulaciones(piezas)) == 1
    assert articulaciones(piezas, giros={}) == []
    assert len(articulaciones(piezas, giros={"tapa": ("sg90", "eje")})) == 1
    assert articulaciones(piezas, giros={"tapa": ("608zz", "aro interior")}) == []


def test_los_giros_salen_del_plan_y_un_backlog_de_antes_no_tiene():
    assert giros_del_plan(Obra(**_plan())) == {"soporte": ("sg90", "eje"),
                                               "plataforma": ("sg90", "eje")}
    sin = {k: v for k, v in _plan().items() if k != "uniones"}
    assert giros_del_plan(Obra(**sin)) is None


# --- quién corrige un choque cuando hay plan ---------------------------------------------------

def test_si_falta_sitio_la_correccion_es_para_quien_monta_el_actuador(tmp_path):
    """El choque de la corrida: la plataforma contra el SG90 de la base.
    Sin plan, la corrección va a la plataforma, «la que va después». Con el
    plan pidiendo 25 mm y el soporte dejando 12.7, la culpa es del soporte.
    Y si el soporte hubiera dejado lo pedido (12), sería de la plataforma,
    que se sale."""
    carpeta = _pan_tilt(tmp_path, PLATAFORMA)
    piezas = leer_piezas(carpeta, "conjunto")
    arts = {a.pieza: a for a in articulaciones(piezas)}
    choques = [{"a": "base", "b": "plataforma", "solido_a": "base: montado",
                "solido_b": "plataforma", "angulos": {"plataforma": 0.0, "soporte": 0.0},
                "hueco_mm": -27.9}]
    assert list(correcciones(piezas, arts, choques)) == ["plataforma"]
    con_plan = correcciones(piezas, arts, choques, presupuestos={"plataforma": 25.0})
    assert list(con_plan) == ["soporte"]
    assert "12.7 mm" in con_plan["soporte"] and "25 mm" in con_plan["soporte"]
    assert list(correcciones(piezas, arts, choques,
                             presupuestos={"plataforma": 12.0})) == ["plataforma"]


# --- mover lo construido tras cada pieza (F9.5 (parcial)) --------------------------------------

@pytest.mark.skipif(_freecadcmd() is None, reason="sin freecadcmd")
def test_la_pieza_que_gira_se_mueve_contra_lo_construido_sin_esperar_al_conjunto(tmp_path):
    """El brazo y el poste de `tests/test_conjunto.py`, con una tercera pieza
    del backlog que aún no existe. A mano (allí está la cuenta): chocan a
    80° y a 90°. Se sabe al construir el brazo, sin verificación del
    conjunto ni animación."""
    from orchestrator.conjunto import mover_lo_construido
    carpeta = _brazo_y_poste(tmp_path, x0=-5, y0=30)
    obra = json.loads((carpeta / "obra.json").read_text(encoding="utf-8"))
    obra["nodos"].insert(2, {"id": "remate", "nombre": "Remate", "que_hace": "x",
                             "depende_de": ["brazo"]})
    obra["nodos"][-1]["depende_de"].append("remate")
    (carpeta / "obra.json").write_text(json.dumps(obra), encoding="utf-8")

    v = mover_lo_construido(carpeta, "brazo", _freecadcmd(), min_gap_mm=0.2)
    assert sorted({c["angulos"]["brazo"] for c in v["choques"]}) == [80, 90]
    assert "80°" in v["correccion"] and "Pieza base" in v["correccion"]
    assert not (carpeta / "nodos" / "conjunto").exists()

    (tmp_path / "libre").mkdir()
    libre = _brazo_y_poste(tmp_path / "libre", x0=-5, y0=60)
    assert mover_lo_construido(libre, "brazo", _freecadcmd(), min_gap_mm=0.2) == {
        "choques": [], "correccion": ""}
